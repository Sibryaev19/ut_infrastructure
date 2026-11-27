import os
import shutil
import polars as pl
import pandas as pd
import psycopg

OID_TO_POLARS_DICT = {
        # Базовые типы
        16: pl.Boolean,      # bool
        17: pl.Binary,       # bytea
        18: pl.Utf8,         # char
        19: pl.Utf8,         # name (идентификаторы)
        20: pl.Int64,        # int8
        21: pl.Int16,        # int2
        23: pl.Int32,        # int4
        25: pl.Utf8,         # text
        114: pl.Utf8,        # json
        700: pl.Float32,     # float4
        701: pl.Float64,     # float8
        1042: pl.Utf8,       # bpchar
        1043: pl.Utf8,       # varchar
        1082: pl.Date,       # date
        1083: pl.Time,       # time
        1114: pl.Datetime,   # timestamp
        1184: pl.Datetime,   # timestamptz
        1700: pl.Float64,    # numeric
        2950: pl.Utf8,       # uuid
        
        # Дополнительные типы
        142: pl.Utf8,        # xml
        790: pl.Float64,     # money
        829: pl.Utf8,        # macaddr
        869: pl.Utf8,        # inet
        650: pl.Utf8,        # cidr
        774: pl.Utf8,        # macaddr8
        1186: pl.Duration,   # interval
        1560: pl.Binary,     # bit
        1562: pl.Binary,     # varbit
        3802: pl.Utf8,       # jsonb
        
        # Системные типы (часто встречаются в запросах к каталогам)
        24: pl.Utf8,         # regproc
        2202: pl.Utf8,       # regprocedure
        2203: pl.Utf8,       # regoper
        2204: pl.Utf8,       # regoperator
        2205: pl.Utf8,       # regclass
        2206: pl.Utf8,       # regtype
        3734: pl.Utf8,       # regconfig
        3769: pl.Utf8,       # regdictionary
        
        # Массивы (важно для аналитики)
        1000: pl.List(pl.Boolean),   # bool[]
        1001: pl.List(pl.Binary),    # bytea[]
        1005: pl.List(pl.Int16),     # int2[]
        1007: pl.List(pl.Int32),     # int4[]
        1009: pl.List(pl.Utf8),      # text[]
        1014: pl.List(pl.Utf8),      # bpchar[]
        1015: pl.List(pl.Utf8),      # varchar[]
        1021: pl.List(pl.Float32),   # float4[]
        1022: pl.List(pl.Float64),   # float8[]
        1028: pl.List(pl.Int32),     # oid[]
        1115: pl.List(pl.Datetime),  # timestamp[]
        1185: pl.List(pl.Datetime),  # timestamptz[]
        1231: pl.List(pl.Float64),  # numeric[]
        2951: pl.List(pl.Utf8),     # uuid[]
        1182: pl.List(pl.Date),      # date[]
        1183: pl.List(pl.Time),      # time[]
        3807: pl.List(pl.Utf8),      # jsonb[]
        143: pl.List(pl.Utf8),      # xml[]
        1187: pl.List(pl.Duration),  # interval[]
    }

class GPConnector:
    # Расширенный маппинг OID типов PostgreSQL/Greenplum в типы Polars
    OID_TO_POLARS = OID_TO_POLARS_DICT

    def __init__(self, host="host", dbname="dbname", port=5432, login=None):
        """
        Инициализация соединения. Соединение живет всё время работы объекта.
        """
        user = login or os.environ.get('JUPYTERHUB_USER', os.environ.get('JLAB_USER')).split("_")[0]
        self._conninfo = f"host={host} port={port} dbname={dbname} user={user} gssencmode=prefer"
        self.conn = None
    
    def connect(self):
        self.conn = psycopg.connect(self._conninfo)
        self.conn.autocommit = False

    def _ensure_connection(self):
        """Проверка активного соединения перед выполнением запроса."""
        if self.conn is None or self.conn.closed:
            self.connect()

    def _get_polars_schema(self, description):
        """Формирует словарь {имя_колонки: тип_polars} на основе ответа курсора."""
        schema = {}
        for desc in description:
            col_name = desc[0]
            oid = desc[1]
            
            # Если тип не найден в словаре, по умолчанию используем Utf8 (строку)
            # Это гарантирует, что скрипт не упадёт на экзотических типах
            polars_type = self.OID_TO_POLARS.get(oid, pl.Utf8)
            schema[col_name] = polars_type
            
        return schema
    
    def _prepare_rows_for_polars(self, rows, schema_types):
        """
        Принудительно приводит к строке (str) все значения, 
        которые Polars ожидает как Utf8, но которые пришли из БД 
        как объекты (списки, словари, кастомные типы psycopg).
        """
        # Находим индексы колонок, тип которых в Polars определен как Utf8
        str_indices = [i for i, ptype in enumerate(schema_types) if ptype == pl.Utf8]
        if not str_indices:
            return rows
        
        processed_rows = []
        for row in rows:
            # row - это tuple, конвертируем в list для возможности изменения
            new_row = list(row)
            for i in str_indices:
                val = new_row[i]
                # Если значение не None и уже не строка - превращаем в строку
                if val is not None and not isinstance(val, str):
                    new_row[i] = str(val)
            processed_rows.append(tuple(new_row))
        return processed_rows

    def sql(self, query: str):
        """
        Аналог spark.sql("..."). 
        Выполняет запрос и возвращает Pandas DataFrame.
        Подходит для небольших объемов данных, DDL и DML команд.
        """
        self._ensure_connection()
        self.conn.rollback()
        
        with self.conn.cursor() as cur:
            cur.execute(query)
            
            # Если у запроса нет возвращаемых данных (например, CREATE, DROP, INSERT)
            if cur.description is None:
                self.conn.commit()
                return None
            
            # Получаем строгую схему из GP
            polars_schema = self._get_polars_schema(cur.description)
            rows = cur.fetchall()
            
            # Обязательно коммитим транзакцию
            self.conn.commit()
            
            # Принудительно кастим неизвестные объекты в строки перед передачей в Polars
            schema_types = list(polars_schema.values())
            rows = self._prepare_rows_for_polars(rows, schema_types)
            
            # Создаем Polars DataFrame с явной схемой и конвертируем в Pandas
            df = pl.DataFrame(rows, schema=polars_schema, orient="row")
            return df.to_pandas()
        
    def run_maintenance(self, query: str):
        """
        Выполняет команды обслуживания (VACUUM, REINDEX) вне транзакционного блока.
        """
        self._ensure_connection()
        # Сохраняем текущее состояние autocommit
        old_autocommit = self.conn.autocommit
        try:
            # Обязательно включаем autocommit для VACUUM
            self.conn.autocommit = True
            with self.conn.cursor() as cur:
                cur.execute(query)
        finally:
            # Возвращаем исходное состояние транзакции
            self.conn.autocommit = old_autocommit

    def to_parquet(self, query: str, directory: str, batch_size: int = 300000, schema: dict = None):
        self._ensure_connection()
        try:
            shutil.rmtree(directory)
        except Exception:
            pass
        os.makedirs(directory, exist_ok=True)
        self.conn.rollback()
        
        with self.conn.cursor(name="heavy_cursor") as cur:
            cur.itersize = batch_size
            cur.execute(query)
            batch_num = 0
            polars_schema = None
            schema_types = None
            
            while True:
                rows = cur.fetchmany(batch_size)
                if not rows:
                    break
                
                # Получаем схему из GP на первом батче (или используем переданную)
                if batch_num == 0:
                    polars_schema = schema if schema else self._get_polars_schema(cur.description)
                    schema_types = list(polars_schema.values())
                
                # Принудительно кастим неизвестные объекты в строки
                rows = self._prepare_rows_for_polars(rows, schema_types)
                
                # Передаём готовую схему
                df = pl.DataFrame(rows, schema=polars_schema, orient="row")
                file_path = os.path.join(directory, f"part-{batch_num:05d}.parquet")
                df.write_parquet(file_path)
                batch_num += 1
                
            self.conn.commit()
    def to_parquet2(self, query: str, directory: str, num_partitions: int = 4, batch_size: int = 300000):
        """
        Заранее считает значение на диске в GP, а уже потом выгружает его (полезно для тяжёлых запросов).
        Параллельная запись убрана, так как узкое место - сеть с сервером.
        """
        self._ensure_connection()
        try:
            shutil.rmtree(directory)
        except Exception:
            pass
        os.makedirs(directory, exist_ok=True)
        
        # Гарантируем, что предыдущая транзакция закрыта
        self.conn.rollback()
        
        # 1. Включаем Autocommit (обязательно для WITH HOLD в psycopg)
        self.conn.autocommit = True
        cursor_name = "hold_result_cursor"
        
        try:
            with self.conn.cursor() as cur:
                cur.execute(f"DECLARE {cursor_name} CURSOR WITH HOLD FOR {query}")
            
            batch_num = 0
            polars_schema = None
            schema_types = None

            # 2. Выгрузка из созданного курсора
            with self.conn.cursor(name=cursor_name) as cur:
                cur.itersize = batch_size
                while True:
                    rows = cur.fetchmany(batch_size)
                    if not rows:
                        break

                    if batch_num == 0:
                        polars_schema = self._get_polars_schema(cur.description)
                        schema_types = list(polars_schema.values())

                    # Принудительно кастим неизвестные объекты в строки
                    rows = self._prepare_rows_for_polars(rows, schema_types)

                    # Создаем датафрейм со строгой схемой и пишем на диск
                    df = pl.DataFrame(rows, schema=polars_schema, orient="row")
                    
                    # Логика именования файлов сохранена
                    partition_idx = batch_num % num_partitions
                    file_path = os.path.join(directory, f"part-p{partition_idx:02d}-b{batch_num:05d}.parquet")
                    df.write_parquet(file_path)
                    batch_num += 1

            # 3. Очистка курсора на стороне БД
            with self.conn.cursor() as cur:
                cur.execute(f"CLOSE {cursor_name}")
            
        except BaseException as e:
            try:
                with self.conn.cursor() as cur:
                    cur.execute(f"CLOSE {cursor_name}")
            except Exception:
                pass
            raise e
        finally:
            # Возвращаем стандартный режим транзакций в любом случае
            self.conn.autocommit = False

    def close(self):
        """Закрытие соединения"""
        if self.conn and not self.conn.closed:
            self.conn.rollback()
            self.conn.close()