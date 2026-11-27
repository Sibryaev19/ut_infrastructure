import os
import warnings
import polars as pl
from trino.dbapi import connect
from trino.auth import KerberosAuthentication

# Подавляем предупреждения о небезопасном SSL (verify=False)
warnings.filterwarnings('ignore')

class TrinoConnector:
    """
    Класс для работы с Trino через Kerberos аутентификацию.
    Рассчитан на работу в автоматическом режиме (без ручного ввода пароля).
    """
    
    # Маппинг строковых типов Trino в типы Polars
    # В Trino cur.description[1] возвращает строку, например 'varchar', 'bigint', 'timestamp(3)'
    TRINO_TO_POLARS = {
        "boolean": pl.Boolean,
        "tinyint": pl.Int8,
        "smallint": pl.Int16,
        "integer": pl.Int32,
        "bigint": pl.Int64,
        "real": pl.Float32,
        "double": pl.Float64,
        "decimal": pl.Float64,  # В Polars есть Decimal, но Float64 безопаснее для вычислений
        "varchar": pl.Utf8,
        "char": pl.Utf8,
        "string": pl.Utf8,
        "date": pl.Date,
        "time": pl.Time,
        "timestamp": pl.Datetime,
        # Для сложных типов (array, map, row) используем Object
        "array": pl.Object,
        "map": pl.Object,
        "row": pl.Object,
    }


    def __init__(self, krb_cache_path: str = None, 
                 krb_config_path: str = "/etc/krb5.conf"):
        """
        Инициализация подключения.
        :param krb_cache_path: Путь к файлу кэша Kerberos. 
                              Если None, берется из системной переменной KRB5CCNAME 
                              или вычисляется по умолчанию (/tmp/krb5cc_<UID>).
        :param krb_config_path: Путь к конфигу krb5.conf
        """
        # Определяем, где лежит базовый тикет (тот самый, что сделал глобальный kinit)
        if krb_cache_path is None:
            current_cache = os.environ.get('KRB5CCNAME')
            if current_cache:
                # Если система/JupyterHub сама определила путь, используем его
                krb_cache_path = current_cache.replace('FILE:', '')
            else:
                # Если пути нет, эмулируем стандартное поведение Linux (как показал тест)
                uid = os.getuid()
                krb_cache_path = f"/tmp/krb5cc_{uid}"
        
        # Указываем библиотеке использовать этот базовый файл
        os.environ['KRB5CCNAME'] = f"FILE:{krb_cache_path}"
        
        self.host = "trino.cloud.df.sbrf.ru"
        self.port = 443
        self.user = os.environ.get('JUPYTERHUB_USER', 'default_user')
        self.realm = "DF.SBRF.RU"  
        
        self.auth = KerberosAuthentication(
            service_name="trino",
            config=krb_config_path,
            principal=f"{self.user}@{self.realm}"
        )
        self._conn = None

    def _get_connection(self):
        """Ленивое создание подключения. Если тикет мертв, упадет здесь с KerberosError."""
        if self._conn is None:
            self._conn = connect(
                host=self.host,
                port=self.port,
                user=self.user,
                http_scheme="https",
                verify=False,
                auth=self.auth
            )
        return self._conn

    def _get_polars_schema(self, description):
        """Формирует схему Polars на основе метаданных курсора Trino."""
        schema = {}
        for desc in description:
            col_name = desc[0]
            # В Trino тип возвращается строкой, например 'varchar(255)' или 'timestamp(3) with time zone'
            # Берем первое слово до скобки или пробела
            type_str = str(desc[1]).split('(')[0].split(' ')[0].lower()
            schema[col_name] = self.TRINO_TO_POLARS.get(type_str, pl.Utf8) # По умолчанию строка
        return schema

    def execute(self, query: str):
        """
        Выполнение DDL/DML запросов (CREATE, INSERT, DROP, MERGE).
        Не возвращает данных.
        """
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(query)
        # В Trino автокоммит для DDL работает неявно, 
        # но для DML иногда требуется явный commit, если включены транзакции.
        # В стандартном DBAPI Trino execute() сразу отправляет запрос.
        print("Запрос выполнен успешно.")
    
    def sql(self, query: str, to_pandas: bool = False):
        """
        Выполнение SELECT запроса.
        Возвращает Polars DataFrame (или Pandas, если to_pandas=True).
        ВНИМАНИЕ: Тащит все данные в оперативную память Jupyter. 
        Используй только для небольших выборок.
        """
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(query)
        
        if cur.description is None:
            return None
            
        polars_schema = self._get_polars_schema(cur.description)
        rows = cur.fetchall()
        
        df = pl.DataFrame(rows, schema=polars_schema, orient="row")
        return df.to_pandas() if to_pandas else df

    def to_parquet(self, query: str, directory: str, batch_size: int = 100000):
        """
        Выгрузка больших данных в Parquet файлы по батчам.
        :param query: SQL запрос
        :param directory: Путь для сохранения (локальный '/path/' или HDFS 'hdfs://...')
        :param batch_size: Размер порции данных, выгружаемой из Trino за раз
        """
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute(query)
        
        if cur.description is None:
            print("Запрос не вернул данных.")
            return

        polars_schema = self._get_polars_schema(cur.description)
        batch_num = 0
        
        while True:
            rows = cur.fetchmany(batch_size)
            if not rows:
                break
                
            # Создаем DataFrame с строгой схемой
            df = pl.DataFrame(rows, schema=polars_schema, orient="row")
            
            # Polars с поддержкой pyarrow/fsspec умеет писать напрямую на HDFS
            file_path = f"{directory}/part-{batch_num:05d}.parquet"
            df.write_parquet(file_path)
            
            print(f"Записан батч {batch_num} -> {file_path} (строк: {len(rows)})")
            batch_num += 1
            
        print(f"Выгрузка завершена. Всего батчей: {batch_num}.")

    def close(self):
        """Закрытие HTTP-сессии"""
        if self._conn:
            self._conn.close()
            self._conn = None

    # Поддержка конструкции with TrinoConnector() as trino:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()