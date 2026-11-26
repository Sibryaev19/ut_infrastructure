Инструкция к модулю distributed_task

Модуль предназначен для распределённой обработки очереди данных.


требуемые зависимости:
dill fsspec requests


В модуле есть настраиваемые параметры (не обязательно менять). По умолчанию:
LOCAL_PATH = "/home/datalab/nfs/utool_dir"                       - локальная дирректория
HDFS_PATH = "/user/team/team_sva_oarb/pvb/sibryaev/utool_dir"    - дирректория на hdfs
logger_file = None                                               - файл с логированием (по умолчанию логирование в консоль)

## Быстрый старт:

#### Делаем импорт модуля
```python
from distributed_task import DistTask

# Необязательные параметры
local_path=None  # локальный путь очереди
hdfs_path=None  # путь очереди на hdfs
logger_file=None  # файл с логированием. По умолчанию логи выводятся в консоль

loader = DistTask(local_path, hdfs_path, logger_file) 
# если не задавать параметры, то loader = DistTask()
```

#### Задаём очередь данных:
```python
partitions = [...] # список данных для очереди. Простейший пример - list(range(100)). 
# Могут быть партициями таблицы, текстами для LLM или другими элементами, которые нужно обработать в очереди
```

#### Задаём единую функцию обработки
Создаём функцию обработки данных. Обязана содержать 1 или 2 входных параметра. Название функции или параметров могут быть любыми.
Требование к функции: должна оперировать только локальными переменными! Если нужна библиотека, то нужно импортировать прям в теле функции!

Первый параметр (parts) - представляет из себя список элементов из очереди. 
На каждой итерации из очереди берётся часть данных и передаётся в качестве первого входного параметра (parts).
Второй параметр context является необязательным. Является словарём. 
Нужен, когда требуется передать в функцию параметры извне. Например, экземпляр spark, своё название таблицы, датафрейм и любые другие переменные.
```python
"""Минимальный пример"""
def proc_func(parts: List(...), context: Dict(...) = None):
    print(parts)

"""Пример использования"""
def proc_func(parts, context):
    import os
    spark = context["spark"]
    table_name = context["table_name"]
    os.mkdir("dir_name")
    
    df = spark.table(table_name).select(["col1", "col2"]).where(f"partition_col in ({', '.join(parts)})")
    df.write.mode("overwrite").parquet(f"{os.path.abspath("dir_name")}/file_name_{parts[0]}_{parts[-1]}")
```

#### Создание загрузки
Создаём загрузку. Делается один раз одним человеком. Далее достаточно подключаться к этой существующей загрузке.
```python
global_mode = True  # Общедоступная (True) или локальная (False)
load_name = "my_load_1234"  # Название загрузки для подключения
loader.new_load(partitions, proc_func, global_mode=global_mode, load_name=load_name)
```

#### Подключаемся к существующей загрузке
Если перед этим была создана загрузка (new_load) то вызывать connect не обязательно
```python
global_mode = True  # Общедоступная (True) или локальная (False)
load_name = "my_load_1234"  # Название загрузки для подключения
loader.connect(global_mode=global_mode, load_name=load_name)
```

#### Задание контекста (если присутствует)
Делается после new_load или connect
```python
context = {"spark": spark, ...}
loader.set_context(context)
```

#### Запуск
```python
num = 1  # 2,3,... - число элементов, которые функция будет обрабатывать за один раз (длина parts).
loader.start(num)
```

#### Просмотр состояния загрузки
Json-файл с промежуточными результатами обработки можно найти по пути:
1) LOCAL_PATH/loads/load_name/load_name.json (актуальное состояние при global_mode=False. При global_mode=True результат обновляется каждый раз при завершении обработки очередной порции данных).
2) HDFS_PATH/loads/load_name/load_name.json (актуальное состояние при global_mode=True).

В json-файле есть следующие поля:
1) workers (словарь) - Реестр участников. Хранит IP и порт каждого подключившегося воркера. Используется классом Podnet для P2P-проверок (heartbeat), чтобы понимать, кто из коллег «в сети», а кто «упал».
2) last_partitions (Список или null). Очередь свободных задач.
3) end_partitions (Список или null). Список обработанных задач.
4) in_process (словарь). Задачи, которые сейчас в работе. Ключ - имя воркера. Значение - взятые воркером задачи.
5) last_modify - время последного изменения файла.
6) last_user - имя пользователя, который последним изменил файл.
7) last_workers_check - время последней сетевой проверки воркеров.

#### Полный пример для создания загрузки:
```python
from distributed_task import DistTask
loader = DistTask()

partitions = list(range(100))
def func(parts, context):
    import time
    delay = context["delay"]
    spark = context["spark"]
    
    for part in parts:
        print(part)
    time.time(delay)

loader.new_load(partitions, func, load_name="my_load_2", global_mode=True)

spark = ...
context = {"spark": spark, "delay": 3}
loader.set_context(context)

loader.start(2)
```

#### Полный пример для подключения к загрузке:
```python
from distributed_task import DistTask
loader = DistTask()

loader.connect(load_name="my_load_2", global_mode=True)

spark = ...
context = {"spark": spark, "delay": 3}
loader.set_context(context)

loader.start(1)
```

## Важные моменты

* Модуль спроектирован под Datalab AI!
* В первую очередь модуль оринетирован на jupyter notebook
* Если в процессе обработки возникнет ошибка, то взятые данные уйдут в конец очереди last_partititons
* 5 ошибок подряд приводят к остановке работы (требуется переподключение через connect)
* Совместная работа контейнеров на разных версиях python может приводить к ошибке при чтении серриализированной функции. Для этого при подключении можно прописать собственную версию функции, указав как входной параметр: loader.connect(load_name="...", global_mode=True, function=my_func)
* При создании выгрузки можно задать сообщение, которое будет выводиться пользователю при подключении к выгрузке: loader.new_load(..., message="сообщение")
* При создании или подключении выводится текущее имя пользователя, которое будет использоваться в json-файле
* При старте работы будет открываться порт, который не стоит закрывать вручную
* Для прерывания работы рекомендуется один раз нажать на квадрат в ячейке jupyterhub (прерывание выполнения) и подождать. Модуль сам завершит задачу.
