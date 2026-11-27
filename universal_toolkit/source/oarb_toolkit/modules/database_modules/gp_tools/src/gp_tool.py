import os
import io
import polars as pl
import pandas as pd
import pyarrow.parquet as pq
from tqdm import tqdm


POLARS_TO_GP_MAP = {
    pl.Int8: "SMALLINT",
    pl.Int16: "SMALLINT",
    pl.Int32: "INTEGER",
    pl.Int64: "BIGINT",
    pl.UInt8: "SMALLINT",
    pl.UInt16: "INTEGER",
    pl.UInt32: "BIGINT",
    pl.UInt64: "BIGINT", 
    pl.Float32: "REAL",
    pl.Float64: "DOUBLE PRECISION",
    pl.Boolean: "BOOLEAN",
    pl.Utf8: "TEXT",
    pl.Date: "DATE",
    pl.Datetime: "TIMESTAMP",
    pl.Time: "TIME",
    pl.Binary: "BYTEA",
}

class GPTool:
    POLARS_TO_PG = POLARS_TO_GP_MAP
    
    def __init__(self, gp_conn):
        self._gp_conn = gp_conn

    def parquet_dir_to_greenplum(
        self, 
        directory: str,
        t_name: str,
        distributed_by: str = "RANDOMLY", 
        batch_size: int = 300000
    ):
        """
        Создает таблицу в GP на основе схемы Parquet-файлов и загружает в нее данные 
        потоковым чтением батчей. Неизвестные типы данных приводятся к строке (TEXT).
        """
        schema_name, table_name = t_name.split(".")
        files = [f for f in os.listdir(directory) if f.endswith('.parquet')]
        if not files:
            print(f"В директории {directory} нет parquet файлов.")
            return

        full_name = f'"{schema_name}"."{table_name}"'
        self._gp_conn._ensure_connection()

        # --- 1. Подсчет строк для прогресс-бара ---
        total_rows = 0
        for file in files:
            try:
                total_rows += pq.ParquetFile(os.path.join(directory, file)).metadata.num_rows
            except Exception:
                pass

        # --- 2. Чтение схемы и подготовка DDL и каста ---
        first_file = os.path.join(directory, files[0])
        polars_schema = pl.scan_parquet(first_file).collect_schema()
        
        cols_ddl = []
        cast_exprs = [] # Список выражений для Polars, чтобы скастить неизвестные колонки
        
        for col_name, pl_type in polars_schema.items():
            if pl_type in self.POLARS_TO_PG:
                pg_type = self.POLARS_TO_PG[pl_type]
                cast_exprs.append(pl.col(col_name)) # Тип известен, каст не нужен
            else:
                pg_type = "TEXT"
                # Принудительно кастим неизвестный тип в строку на уровне Polars
                cast_exprs.append(pl.col(col_name).cast(pl.Utf8))
            
            cols_ddl.append(f'"{col_name}" {pg_type}')
        
        cols_str = ", ".join(cols_ddl)
        
        # Логика DISTRIBUTED BY
        if distributed_by and distributed_by.upper() == "RANDOMLY":
            dist_clause = "DISTRIBUTED RANDOMLY"
        elif distributed_by:
            dist_clause = f'DISTRIBUTED BY ("{distributed_by}")'
        else:
            dist_clause = "DISTRIBUTED RANDOMLY"
            
        # Удаляем таблицу, если она есть, и создаем новую
        self._gp_conn.sql(f"DROP TABLE IF EXISTS {full_name}")
        ddl = f"CREATE TABLE {full_name} ({cols_str}) {dist_clause}"
        self._gp_conn.sql(ddl)
        print(f"Таблица {full_name} создана. Начинаю загрузку {total_rows} строк...")
# --- 3. Потоковая загрузка данных ---
        self._gp_conn.conn.rollback()
        try:
            with self._gp_conn.conn.cursor() as cur:
                copy_sql = f"COPY {full_name} FROM STDIN WITH (FORMAT CSV, NULL '', HEADER FALSE)"
                pbar = tqdm(total=total_rows, desc="Загрузка в GP", unit="rows")
                
                for file in files:
                    parquet_file = pq.ParquetFile(os.path.join(directory, file))
                    for batch in parquet_file.iter_batches(batch_size=batch_size):
                        # Конвертируем PyArrow батч в Polars, применяем каст unknown -> Utf8
                        df_polars = pl.from_arrow(batch)
                        if cast_exprs:
                            df_polars = df_polars.with_columns(cast_exprs)
                            
                        # Только потом в Pandas
                        df = df_polars.to_pandas()
                        
                        buffer = io.StringIO()
                        df.to_csv(buffer, index=False, header=False, na_rep='')
                        buffer.seek(0)
                        
                        if hasattr(cur, 'copy_expert'):
                            cur.copy_expert(copy_sql, buffer)
                        else:
                            with cur.copy(copy_sql) as cp:
                                cp.write(buffer.getvalue())
                                
                        pbar.update(len(df))
                        
                pbar.close()
                self._gp_conn.conn.commit()
                
            print(f"Успешно загружено {total_rows} строк в {full_name}.")

        except Exception as e:
            self._gp_conn.conn.rollback()
            print(f"Ошибка при загрузке: {e}")
            raise
    
    def insert_dataframe(self, df: pd.DataFrame, table_name: str):
        """
        Быстрая загрузка Pandas DataFrame в таблицу Greenplum через COPY.
        Таблица должна быть уже создана.
        """
        if table_name.split('.') > 1:
            schema_name, t_name = table_name.split('.')
            full_name = f'{schema_name}."{table_name}"'
        else:
            full_name = table_name
        buffer = io.StringIO()
        
        # Сохраняем df в CSV прямо в оперативной памяти
        df.to_csv(buffer, index=False, header=False, na_rep='')
        buffer.seek(0)
        
        self._gp_conn._ensure_connection()
        self._gp_conn.conn.rollback()
        
        try:
            with self._gp_conn.conn.cursor() as cur:
                # Поддержка и psycopg2, и psycopg3
                if hasattr(cur, 'copy_expert'):
                    cur.copy_expert(f"COPY {full_name} FROM STDIN WITH (FORMAT CSV, NULL '')", buffer)
                else:
                    with cur.copy(f"COPY {full_name} FROM STDIN WITH (FORMAT CSV, NULL '')") as cp:
                        cp.write(buffer.getvalue())
            self._gp_conn.conn.commit()
            print(f"Успешно загружено {len(df)} строк в {full_name}")
        except Exception as e:
            self._gp_conn.conn.rollback()
            print(f"Ошибка при загрузке данных: {e}")
             
    def find_schemas_catalog(self, partial_name: str):
        """Ищет схемы в pg_namespace по частичному совпадению (все схемы в БД)."""
        q = f"""
            SELECT nspname AS schema_name
            FROM pg_catalog.pg_namespace
            WHERE nspname ILIKE '%{partial_name}%'
            ORDER BY nspname;
        """
        df = self._gp_conn.sql(q)
        return df["schema_name"].values.tolist() if df is not None and len(df) > 0 else []