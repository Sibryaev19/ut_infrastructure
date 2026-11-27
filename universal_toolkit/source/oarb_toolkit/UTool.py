"""
    Версия 3.1
"""

import pyspark
from pyspark.sql import SparkSession
from pyspark import SparkConf
from pyspark.sql.types import *

import polars as pl
import pandas as pd
import numpy as np
import time
import os
import sys
import shutil
import json
import random
import inspect
import subprocess
import importlib
import pickle
import zipfile
import argparse
import base64
import dill
import fsspec

from datetime import datetime

from functools import reduce
from pyspark.sql import DataFrame
from IPython.display import HTML,display

from pyspark.sql.utils import AnalysisException
from pyspark.sql.functions import col as spark_col
from pyspark.sql.types import StringType

import requests
import threading
import http.server
import socketserver
import socket

import psycopg
from concurrent.futures import ThreadPoolExecutor, as_completed

from utool_dir.distributed_task import DistTask, Podnet

# =================================================== Настройки ====================================================================#
HDFS_PATH = "/user/.../utool_dir"
LOCAL_PATH = "/home/datalab/nfs/utool_dir"
MY_LOGIN = os.environ.get('JUPYTERHUB_USER').split("_")[0]
# MY_LOGIN = 'pyspark_3_8'
MY_ID = f"id_{MY_LOGIN}" 

fs_arnsdpsbx = fsspec.filesystem(
    'hdfs',
    host='arnsdpsbx',
    kerberos=True,
    use_https=False
)
fs_hdfsgw = fsspec.filesystem(
    'hdfs',
    host='hdfsgw',
    kerberos=True,
    use_https=False
)

class UTool_NS:
    def __init__(self):
        display(HTML("<style>.ansi-yellow-bg { background-color: #af541e !important; }</style>"))
        display(HTML("<style>.jp-OutputArea-output pre {white-space: pre !important; }</style>"))
        display(HTML("<style>.container { width:100% !important; }</style>"))
        display(HTML("<style>.output_result { max-width:100% !important; }</style>"))
        display(HTML("""
            <style>
            .cm-lsp-diagnostic {all: unset}
            .cm-lsp-diagnostic-Warning {all: unset}
            </style>
        """))
        
    #================================================== Внутренние команды =========================================================#
    def get_loader(self):
        return DistTask()
    
    def get_gp_connector(self, host="gp_dns_pkap1123_audit_da.gp.df.sbrf.ru", dbname="capgp3", port=5432):
        from utool_dir.gp_connector import GPConnector
        gp_connector = GPConnector(host, dbname, port)
        return gp_connector
    
    def get_podnet(self):
        return Podnet()
    
    def get_fs(self):
        return {"arnsdpsbx": fs_arnsdpsbx, "hdfsgw": fs_hdfsgw}
        
    def reload_tool(self):
        # возвращает экземпляр обновлённого tool. Если нужно что-то быстро исправить в модуле
        module = sys.modules[__name__]
        importlib.reload(module)
        return module.UTool_NS()
    
    #================================================== Работа с файлами ===========================================================#
    def get_size(self, path):
        result = subprocess.run(
            ['du', '-sb', path],
            capture_output=True, text=True, check=True
        )
        size_bytes = int(result.stdout.split()[0])
        return round(size_bytes / (1024**3), 4)
    
    def rm_dir(self, path):
        try:
            shutil.rmtree(path)
            return True
        except Exception as e:
            return False

    def rm_file(self, path):
        try:
            os.remove(path)
            return True
        except Exception as e:
            return False

    def rm_path(self, path):
        is_delete = False
        is_delete = is_delete or self.rm_dir(path)
        is_delete = is_delete or self.rm_file(path)
    
        if not is_delete:
            print(f"Путь не найден {path}")
        return is_delete

    def full_path(self, path):
        if len(path.split(':')) > 1:
            return path
        return 'file://' + os.path.abspath(path)
    
    def read_dir(self, dir_name):
        try:
            return os.listdir(dir_name)
        except FileNotFoundError:
            print(f"Дирректория {dir_name} не найдена")
        except PermissionError:
            print(f"Доступ к {dir_name} запрещён")
        except Exception as e:
            print(e)
        return []
    
    def write_pickle(self, func, path):
        """Сохраняет функцию в файл"""
        full_path = self.full_path(path)[len('file://'):]
        if len(full_path) < 5 or full_path[-4:] != '.pkl':
            full_path += '.pkl'
        with open(full_path, 'wb') as f:
            pickle.dump(func, f)

    def read_pickle(self, path):
        """Загружает функцию из файла"""
        full_path = self.full_path(path)[len('file://'):]
        try:
            with open(full_path, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Ошибка чтения pickle {full_path}: {e}")
            return None
    
    def write_dill(self, func, path):
        full_path = self.full_path(path)[len('file://'):]
        if len(full_path) < 6 or full_path[-5:] != '.dill':
            full_path += '.dill'
        with open(full_path, 'wb') as f:
            dill.dump(func, f)

    def read_dill(self, path):
        full_path = self.full_path(path)[len('file://'):]
        try:
            with open(full_path, 'rb') as f:
                return dill.load(f)
        except Exception as e:
            print(f"Ошибка чтения dill {full_path}: {e}")
            return None 
    
        
    def write_json(self, data, path):
        full_path = self.full_path(path)[len('file://'):]
        if len(full_path) < 6 or full_path[-5:] != '.json':
            full_path += '.json'
        with open(full_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def read_json(self, path):
        full_path = self.full_path(path)[len('file://'):]
        with open(full_path, "r", encoding="utf-8") as f:
            return json.load(f)
        
    def func_info(self, func):
        """Возвращает словарь с информацией об аргументах"""
        sig = inspect.signature(func)
        for name, param in sig.parameters.items():
            default = param.default if param.default != param.empty else None
            required = param.default == param.empty and param.kind not in (param.VAR_POSITIONAL, param.VAR_KEYWORD)
            print(f"{name}: {"Обязателен" if required else default}")
        

class UTool(UTool_NS):
    def __init__(self, spark=None):
        self.spark = spark if spark is not None else self.create_spark()

        display(HTML("<style>.ansi-yellow-bg { background-color: #af541e !important; }</style>"))
        display(HTML("<style>.jp-OutputArea-output pre {white-space: pre !important; }</style>"))
        display(HTML("<style>.container { width:100% !important; }</style>"))
        display(HTML("<style>.output_result { max-width:100% !important; }</style>"))
        display(HTML("""
            <style>
            .cm-lsp-diagnostic {all: unset}
            .cm-lsp-diagnostic-Warning {all: unset}
            </style>
        """))
        
    def get_spark(self):
        return self.spark
    
    def reload_tool(self):
        # возвращает экземпляр обновлённого tool. Если нужно что-то быстро исправить в модуле
        module = sys.modules[__name__]
        importlib.reload(module)
        return module.UTool(self.spark)
    
    def create_spark(self):
        conf = SparkConf() \
            .setAll([
                ("spark.ui.enabled", "true"),
                ("spark.ui.bindAddress", "127.0.0.1"),
                ("spark.ui.port", "4040"),
                ("spark.driver.host", "127.0.0.1"),
                ("spark.driver.bindAddress", "127.0.0.1"),
                ("spark.driver.memory", "16g"),
                ("spark.executor.instances", "4"),
                ("spark.executor.cores", "4"),
                ("spark.kubernetes.executor.limit.cores", "4"),
                ("spark.kubernetes.executor.request.cores", "1800m"),
                ("spark.executor.memory", "16g"),
                ("spark.executor.memoryOverhead", "800m"),
                ("spark.dynamicAllocation.enabled", "true"),
                ("spark.dynamicAllocation.shuffleTracking.enabled", "true"),
                ("spark.sql.parquet.compression.codec", "snappy"),
                ("spark.sql.execution.arrow.pyspark.enabled", "true"),
                ("spark.sql.hive.metastorePartitionPruningFallbackOnException", "true"),
                ("spark.sql.catalogImplementation", "hive"),
                ("spark.port.maxRetries", "100"),
                ("spark.master", "local[*]")
            ])

        spark = SparkSession \
            .builder \
            .config(conf=conf) \
            .enableHiveSupport() \
            .getOrCreate()
        spark.sparkContext.setLogLevel("ERROR")
        spark.conf.set("spark.sql.parquet.int96RebaseModeInRead", "LEGACY")
        spark.conf.set("spark.sql.parquet.int96RebaseModeInWrite", "LEGACY")
        spark.conf.set("spark.sql.parquet.datetimeRebaseModeInRead", "LEGACY")
        spark.conf.set("spark.sql.parquet.datetimeRebaseModeInWrite", "LEGACY")
        spark.conf.set("hive.exec.dynamic.partition", "true")
        spark.conf.set("hive.exec.dynamic.partition.mode", "nonstrict")
        spark.conf.set("spark.sql.source.partitionOverwriteMode", "dynamic")
        spark.conf.set("spark.sql.adaptive.enabled", "true")
        spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", "true")
        spark.conf.set("spark.sql.adaptive.advisoryPartitionSizeInBytes", "131072000")
        
        def sql_gp(query):
            gp_src_options = {
                "url": "jdbc:postgresql://gp_dns_pkap1123_audit_da.gp.df.sbrf.ru:5432/capgp3",
                "query": query,
                "user": str(MY_LOGIN),
            }

            # Create temporary Spark's table from Greenplum query result.
            df = spark.read \
                .format("jdbc") \
                .options(**gp_src_options) \
                .load()
            return df
        spark.sql_gp = sql_gp
        
        return spark

    #================================================== Работа с таблицами и репликами =============================================#
    def columns(self, table_name, show=False, pattern=lambda field:f"{field},\n"):
        try:
            cols = self.spark.table(table_name).columns
            if show:
                for col in cols:
                    print(pattern(col), end='')
            else:
                return cols
        except Exception as e:
            raise Exception(f"Таблица не найдена!\n{e}")
    
    def partitions(self, table_name, in_dict=True, warning=True):
        _ = self.columns(table_name)
        try:
            part = self.spark.sql(f'show partitions {table_name}').toPandas().partition
            columns = [col.split('=')[0] for col in part.str.split('/')[0]]
            df = part.str.split('/', expand=True)
            df.columns = columns
            res_dict = {}
            for col in columns:
                df[col] = df[col].apply(lambda x: x.split('=')[1])
                if in_dict:
                    res_dict[col] = np.array(df[col].drop_duplicates().tolist())
            return list(res_dict.keys()), (res_dict if in_dict else df)
        except AnalysisException as e:
            if warning:
                print(f"Партиции для таблицы {table_name} не найдены!")
            return None
        except Exception as e:    
            raise Exception(f"Что-то не так: {e}")
            
    
    def tables(self, schema_name):
        try:
            some = self.spark.sql(f"show tables in {schema_name}").filter(f"namespace = '{schema_name.lower()}'")
            tables = some.toPandas()['tableName'].tolist()
            return tables
        except Exception as e:
            print(f"Реплика {schema_name} не найдена!\n{e}")
            return []
    
    def replica_full_load(self, schema_name, result_file_name, sample_count=1000, source_file=None, tables=None, cut=None):
        replica_tables = self.tables(schema_name)
        if tables is not None:
            tables = [t.lower() for t in tables]
            for t in tables:
                if t not in replica_tables:
                    raise Exception(f"Таблицы {t} нет в {schema_name}")
        else:
            tables = replica_tables
        if len(tables) == 0:
            print(f"Таблиц нет в реплике {schema_name}!")
            return None
        source_data = None
        if source_file is not None:
            source_data = {}
            data = self.read_csv(source_file, delimiter=';').toPandas()[['Системное имя таблицы', 'Системное имя атрибута', 'Наименование атрибута']].values.tolist()
            for row in data:
                if row[0].lower() not in source_data.keys():
                    source_data[row[0].lower()] = {row[1].lower(): row[2]}
                else:
                    source_data[row[0].lower()][row[1].lower()] = row[2]
        schema = schema_name
        schema_info = []
        gap = {
                "table_name": ' ',
                "column_comment": ' ',
                "data_type": ' ',
                "column_name": ' ',
                "value": ' ',
                "is_partition": ' ',
                "sample_if_partition": ' '
              }
        df_array = []
        for i1, table in enumerate(tables):
            try:
                df = None
                names, values = None, None
                res = None
                try:
                    res = self.partitions(f'{schema}.{table}', in_dict=True, warning=False)
                except Exception:
                    pass
                if res is not None:
                    names, values = res
                    where_query = f"cast({names[0]} as string) = \'{values[names[0]][-1]}\'"
                    for name in names[1:]:
                        where_query += f" and cast({name} as string) = \'{values[name][-1]}\'"
                    
                    df = self.spark.sql(f"select * from {schema}.{table} where {where_query}")
                    df = self.take(df, sample_count)
                else:
                    # df = self.take(self.spark.sql(f"select * from {schema}.{table}"), sample_count)
                    df = self.read_dir_parquet(self.get_table_hdfs_path(f"{schema}.{table}"))
                    if df is None:
                        df_array.append([])
                        print(f"{table} empty [{i1+1}/{len(tables)}]")
                        continue
                    df = self.take(df, sample_count)
                
                if df.first() is None:
                    df_array.append([])
                    print(f"{table} empty [{i1+1}/{len(tables)}]")
                    continue
                df_array.append(df)
                first_value = df.take(1000)[-1].asDict()
                description_df = self.spark.sql(f""" describe formatted {schema}.{table}""")
                description = description_df.toPandas().values[:len(df.columns)]
                
                for fields in description:
                    is_partition = True if (names is not None and fields[0] in names) else False
                    sample_if_partition = ''
                    if is_partition:
                        sample_if_partition = values[fields[0]][::-1]
                        sample_if_partition = sample_if_partition[:min(10, len(sample_if_partition))].__str__()
                    
                    schema_info.append({
                        "table_name": table,
                        "column_comment": str(fields[2]) if source_data is None else source_data[table].get(str(fields[0]), str(fields[2])),
                        "data_type": str(fields[1]),
                        "column_name": str(fields[0]),
                        "value": str(first_value.get(fields[0])) if first_value is not None else '',
                        "is_partition": '1' if is_partition else '0',
                        "sample_if_partition": sample_if_partition
                    })
                schema_info.append(gap)
                print(f"{table} over [{i1+1}/{len(tables)}]")
            except Exception as e:
                print(f"Error processing table {table}: {e}")
                raise e
        if len(df_array) == 0:
            print("Всё очень плохо!")
            return None
        
        columns_order = ["table_name",
                "column_comment",
                "data_type",
                "column_name",
                "value",
                "is_partition",
                "sample_if_partition"]
        result_df = self.spark.createDataFrame(pd.DataFrame(schema_info, columns=columns_order))
        
        df_array = [result_df] + df_array
        tables = ['All_Tables'] + tables
        if cut is not None:
            tables = [t.split(cut)[-1] for t in tables]
        self.write_excel_sheets(df_array, result_file_name, tables)
        print(f"Done!")
    
    def columns_description(self, table_name):
        description_df = self.spark.sql(f""" describe formatted {table_name}""")
        return self.column_as_list(description_df, 'comment')[:len(self.spark.table(table_name).columns)]

    def get_table_hdfs_path(self, table_name):
        cols = self.spark.sql(f"describe formatted {table_name}").toPandas().values.tolist()
        for col in cols:
            if col[0] == 'Location':
                return col[1]
        
    def write_partition(self, df, table_name, partitions):
        view_name = 'fast_view'
        df.createOrReplaceTempView(view_name)
        if type(partitions) == type({}):
            query = f"""
                insert overwrite table {table_name} partition({', '.join([f"{key}='{val}'" for key, val in partitions.items()])})
                select {', '.join([col for col in df.columns if col not in list(partitions.keys())])}
                from {view_name}
            """
        else:
            print('partition должен быть словарём!')
            return None
        self.spark.sql(query)
        
    def write_table_sandbox(self, df, table_name, partitions=None):
        if len(table_name.split('.')) == 1:
            table_name = f"arnsdpsbx_t_team_sva_oarb.{table_name}"
        writer = df.write.mode('overwrite')
        writer = writer.partitionBy(tuple(partitions)) if partitions is not None else writer
        writer.saveAsTable(table_name)
        print(f"{table_name} записана")
        
    def find_table_sandbox(self, substring):
        df = self.spark.sql(f"""
            show tables in arnsdpsbx_t_team_sva_oarb like '*{substring}*'
        """)
        table_list = df.toPandas()["tableName"].values.tolist()
        return [f"arnsdpsbx_t_team_sva_oarb.{t}" for t in table_list]
    
    def delete_table_sandbox(self, table_name):
        try:
            hdfs_path = self.get_table_hdfs_path(table_name)
        except Exception as e:
            print(f"Таблицы {table_name} не найдена: {e}")
            return False
        self.spark.sql(f"drop table {table_name}")
        try:
            # вдруг, не удалилось
            fs_arnsdpsbx.rm(hdfs_path, recursive=True)
        except Exception:
            pass
        return True
    
    #================================================== Работа промежуточными результатами =========================================#
    def take(self, df, n_sample):
        return self.spark.createDataFrame(df.take(n_sample), schema=df.schema)
    
    def show(self, df, n_sample=None):
        if type(df) == type("string"):
            df = self.spark.table(df)
        if n_sample is None or n_sample < 0:
            df.show(truncate=0, vertical=False)
        self.take(df, n_sample).show(n_sample,0,False)
        
    def write_read(self, df, path, is_delete=False, view_name=None):
        self.write_parquet(df, path)
        df = self.read_parquet(path, view_name=view_name)
        if is_delete:
            df.cache()
            df.count()
            self.rm_path(path)
        return df
    
    def get_view_list():
        self.spark.sql("show tables").filter("isTemporary = true").show()
    
    def drop_temp_view(self, view_name):
        self.spark.sql(f"drop table {view_name}")
        
    def union_df_arr(self, df_arr, distinct=True):
        combined_df = reduce(DataFrame.union, df_arr)
        if distinct:
            combined_df = combined_df.dropDuplicates()
        return combined_df
    
    def read_dir_csv(self, dir_name, distinct=False):
        result = self.read_csv(f"{dir_name}/**/*.csv")
        if distinct:
            return self.write_read(result.distinct(), f'{LOCAL_PATH}/fast_save', is_delete=True)
        return result
    
    def read_dir_parquet(self, dir_name, distinct=False, view_name=None):
        full_path = self.full_path(dir_name)
        try:
            df = self.spark.read \
              .option('recursiveFileLookup', 'true') \
              .parquet(full_path)
            if view_name is not None:
                self.create_temp_view(df, view_name)
                
            if distinct:
                return self.write_read(df.distinct(), f'{LOCAL_PATH}/fast_save', is_delete=True)
            return df
        except Exception as e:
            print(f"Ошибка чтения parquet {full_path}: {e}")
            return None
    
    def convert_to_string(self, df):
        arr = []
        for column in df.columns:
            try:
                arr.append(spark_col(f"{column}").cast(StringType()).alias(f"{column}"))
            except Exception as e:
                arr.append(spark_col(f"`{column}`").cast(StringType()).alias(f"`{column}`"))
        return df.select(*arr)
    
    def opt(self, sdf):
        return sdf.repartition(1).hint('broadcast')
    
    def cancel(self):
        self.spark.sparkContext._jsc.sc().cancelAllJobs()
        
    def clear_cache(self):
        self.spark.catalog.clearCache()
        
    #================================================== Работа с файлами ===========================================================#

    def create_temp_view(self, df, view_name):
        df.createOrReplaceTempView(view_name)
    
    def read_csv(self, path, view_name=None, delimiter=None):
        full_path = self.full_path(path)
        try:
            if delimiter is None:
                df = self.spark.read \
                  .option("header", "true") \
                  .option("inferSchema", "false") \
                  .csv(full_path)
            else:
                df = self.spark.read \
                  .option("header", "true") \
                  .option('delimiter', delimiter) \
                  .option("inferSchema", "false") \
                  .csv(full_path)
            if view_name is not None:
                self.create_temp_view(df, view_name)
            return df
        except Exception as e:
            print(f"Ошибка чтения CSV {full_path}: {e}")
            return None

    def write_csv(self, df, path):
        full_path = self.full_path(path)
        try:
            df.write \
              .option("header", "true") \
              .mode("overwrite") \
              .csv(full_path)
            return True
        except Exception as e:
            raise Exception(f"Ошибка записи в csv {full_path}: {e}")
    
    def write_parquet(self, df, path, partitions=None):
        full_path = self.full_path(path)
        try:
            writer = df.write.mode("overwrite")
            writer = writer.partitionBy(tuple(partitions)) if partitions is not None else writer
            writer.parquet(full_path)
            return True
        except Exception as e:
            raise Exception(f"Ошибка записи в parquet {full_path}: {e}")
    
    def read_parquet(self, path, view_name=None):
        full_path = self.full_path(path)
        try:
            df = self.spark.read \
              .option('mergeSchema', 'true') \
              .parquet(full_path)
            if view_name is not None:
                self.create_temp_view(df, view_name)
            return df
        except Exception as e:
            print(f"Ошибка чтения parquet {full_path}: {e}")
            return None
        
    #================================================== Работа с excel =============================================================#
    def get_excel_sheet_names(self, path):
        path = path if len(path) > 5 and path[-5:] == '.xlsx' else f'{path}.xlsx'
        full_path = self.full_path(path)
        with pd.ExcelFile(full_path) as xl:
            return xl.sheet_names
    
    def clear_null(self, df):
        view_name = "temp_view"
        self.create_temp_view(df, view_name)
        
        columns = df.columns
        query = "select "
        for col in columns[:-1]:
            query += f"case when cast(`{col}` as string) in ('None', 'nan', 'null', ' ') or `{col}` is null then '' else cast(`{col}` as string) end as `{col}`,\n"
        col = columns[-1]
        query += f"case when `{col}` in ('None', 'nan', 'null', ' ') or `{col}` is null then '' else `{col}` end as `{col}`\n"
        query += f"from {view_name}"
        
        clear_df = self.spark.sql(query)
        return clear_df
    
    def read_excel(self, path, sheet_name='Sheet1', view_name=None):
        path = path if len(path) > 5 and path[-5:] == '.xlsx' else f'{path}.xlsx'
        full_path = self.full_path(path)
        sheets = self.get_excel_sheet_names(full_path)
        if len(sheets) == 1:
            sheet_name = sheets[0]
        elif sheet_name not in sheets:
            raise Exception(f"Лист {sheet_name} не найден! Есть следующие: {sheets}")
            
        df = pd.read_excel(full_path, sheet_name=sheet_name)
        df_str = df.astype(str).replace({"nan": None})
        df = self.spark.createDataFrame(df.astype(str))
        if view_name is not None:
            df.createOrReplaceTempView(view_name)
        return df
    
    def write_excel(self, df, file_name, sheet_name='Sheet1', clear=True):
        file_path = file_name if len(file_name) > 5 and file_name[-5:] == '.xlsx' else f'{file_name}.xlsx'
        
        df_clear = df
        df_clear = self.clear_null(df_clear) if clear else df_clear
        df_clear.toPandas().astype(str).to_excel(file_path, sheet_name=sheet_name, index=False)
    
    def write_excel_sheets(self, df_arr, file_name, sheet_arr=None):
        if file_name[-5:] != '.xlsx':
            file_name += '.xlsx'
        if sheet_arr is not None:
            assert len(df_arr) == len(sheet_arr)
        else:
            assert len(df_arr) > 0
            sheet_arr = [f"Sheet{i+1}" for i in range(len(df_arr))]
        
        with pd.ExcelWriter(file_name) as writer:
            for i, df in enumerate(df_arr):
                if df == []:
                    continue
                sheet_name = sheet_arr[i] if len(sheet_arr[i]) < 32 else sheet_arr[i][:31]
                df = self.convert_to_string(df)
                df.toPandas().astype(str).to_excel(writer, sheet_name=sheet_name, index=False)


