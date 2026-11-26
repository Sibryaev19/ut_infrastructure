"""Модуль для организации распределённых задач"""

import time
import os
import sys
import shutil
import json
import random
import inspect
import subprocess
import dill
import fsspec
import logging
import importlib

import requests
import threading
import http.server
import socketserver
import socket
from typing import Any, Callable, Optional, List, Dict, Tuple

from .podnet import Podnet

user_id = None
try:
    user_id = "id_" + os.environ.get('JUPYTERHUB_USER').split("_")[0]
except Exception:
    pass


def setup_logger(log_to_file: bool = False, log_file: str = 'app.log', level: int = logging.INFO) -> logging.Logger:
    """Настройка логгера. 

    Args:
        log_to_file: Писать логи в файл, иначе в консоль.
        log_file: Имя файла для логов.
        level: Уровень логирования.

    Returns:
        Настроенный объект логгера.
    """
    logger = logging.getLogger('my_module')
    logger.setLevel(level)
    logger.handlers.clear()
    
    if log_to_file:
        handler = logging.FileHandler(log_file, encoding='utf-8')
    else:
        handler = logging.StreamHandler()
    
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


class myLogger:
    """Обертка для логгера."""
    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or setup_logger()
        
    def change_logger(self, new_logger: logging.Logger) -> None:
        """Изменяет текущий логгер."""
        self._logger = new_logger
    
    def change_logger_file(self, logger_file: str) -> None:
        """Перенаправляет логирование в файл."""
        if logger_file.find('.') == -1:
            logger_file = f"{logger_file}.log"
        self._logger = setup_logger(log_to_file=True, log_file=logger_file)
    
    def debug(self, message: str) -> None:
        self._logger.debug(message)
        
    def info(self, message: str) -> None:
        self._logger.info(message)
        
    def warning(self, message: str) -> None:
        self._logger.warning(message)
        
    def error(self, message: str) -> None:
        self._logger.error(message)
        

logger = myLogger(setup_logger())


global_config = {
    "local_path": "/home/datalab/nfs/utool_dir",
    "hdfs_path": "/user/team/team_sva_oarb/pvb/sibryaev/utool_dir",
    "user_id": user_id or "user"
}


fs_arnsdpsbx = fsspec.filesystem(
    'hdfs',
    host='arnsdpsbx',
    kerberos=True,
    use_https=False
)


def get_full_path(path: str) -> str:
    """Преобразует относительный путь в полный файловый URL.
    
    Args:
        path: Исходный путь.
    
    Returns:
        Полный путь в формате 'file://...' или оригинальный, если передан URL.
    """
    if len(path.split(':')) > 1:
        return path
    return 'file://' + os.path.abspath(path)

def write_dill(func: Callable, path: str) -> None:
    """Запись функции в файл."""
    full_path = get_full_path(path)[len('file://'):]
    if len(full_path) < 6 or full_path[-5:] != '.dill':
        full_path += '.dill'
    with open(full_path, 'wb') as f:
        dill.dump(func, f)

def read_dill(path: str) -> Optional[Callable]:
    """Чтение функции из файла."""
    full_path = get_full_path(path)[len('file://'):]
    try:
        with open(full_path, 'rb') as f:
            return dill.load(f)
    except Exception as e:
        logger.error(f"Ошибка чтения dill {full_path}: {e}")
        return None 


class Queue:
    """Класс для управления очередью задач и файловыми блокировками."""
    def __init__(self, local_path: Optional[str] = None, hdfs_path: Optional[str] = None) -> None:
        """Инициализация очереди."""
        global global_config
        self._isConnect = False
        self._user_name = None
        self._global_mode = False
        self._queue_name = None
        self._loader_mode = False
        self.podnet = None

        self._tool_dir_path = (global_config.get("local_path") if local_path is None else local_path) + '/loads'
        self._hdfs_tool_load_dir_path = (global_config.get("hdfs_path") if hdfs_path is None else hdfs_path) + '/loads'
        self._local_dir_name = None
        self._global_dir_name = None

        self._lock_waiting_time = 20

    def get_queue_name(self) -> Optional[str]:
        """Получение имени очереди."""
        return self._queue_name

    def _set_queue(self, partitions: List[Any]) -> None:
        """Инициализация файловой структуры и сохранение начального состояния очереди."""
        try:
            if not self._loader_mode:
                shutil.rmtree(self._local_dir_name)
        except Exception:
            pass
        os.makedirs(self._local_dir_name, exist_ok=True)
        with open(self._local_dir_name + '/lock.busy', 'w'):
            pass
        
        self._save_queue({
            "workers": {},
            "last_partitions": partitions if len(partitions) > 0 else None,
            "end_partitions": None,
            "in_process": {},
            "last_modify": int(time.time()),
            "last_user": self._user_name,
            "last_workers_check": 0
        })

    def _save_queue(self, data: Dict[str, Any]) -> None:
        """Сохранение состояния очереди в json-файл и синхронизация с HDFS."""
        os.makedirs(os.path.dirname(self._local_dir_name), exist_ok=True)
        with open(self._local_dir_name + f'/{self._queue_name}.json', 'w', encoding='utf-8') as params_file:
            json.dump(data, params_file, ensure_ascii=False, indent=4)

        if self._global_mode:
            try:
                os.remove(self._local_dir_name + '/' + 'lock.free')
            except Exception:
                pass
            fs_arnsdpsbx.put(self._local_dir_name, self._hdfs_tool_load_dir_path + '/', recursive=True)
        self._rename_file('lock.busy', 'lock.free')

    def _get_queue(self) -> Dict[str, Any]:
        """Чтение текущего состояния очереди из json-файла."""
        file_name = f'/{self._queue_name}.json'
        if self._global_mode:
            fs_arnsdpsbx.get(self._global_dir_name, self._tool_dir_path + '/', recursive=True)
        with open(self._local_dir_name + file_name, "r", encoding="utf-8") as params_file:
            return json.load(params_file)

    def _delete_file(self, file_name: str) -> bool:
        """Удаление файла из локальной директории и/или HDFS."""
        try:
            if self._global_mode:
                try:
                    os.remove(self._local_dir_name + "/" + file_name)
                except Exception:
                    pass
                fs_arnsdpsbx.rm(self._global_dir_name + "/" + file_name)
            else:
                os.remove(self._local_dir_name + "/" + file_name)
            return True
        except Exception as e:
            return False
    
    def _rename_file(self, old_name: str, new_name: str) -> bool:
        """Переименование файла в локальной директории или HDFS."""
        try:
            if self._global_mode:
                fs_arnsdpsbx.mv(self._global_dir_name + "/" + old_name, self._global_dir_name + "/" + new_name)
            else:
                os.rename(self._local_dir_name + "/" + old_name, self._local_dir_name + "/" + new_name)
            return True
        except Exception as e:
            return False

    def _create_lock(self) -> None:
        """Создание блокировки очереди (lock.busy)."""
        count = 0
        while not self._rename_file('lock.free', 'lock.busy'):
            count += 1
            if count == 5:
                last_lock_time, last_user = self._get_last_lock_time()
                if self._user_name == last_user or int(time.time()) - last_lock_time > self._lock_waiting_time:
                    if self._user_name != last_user:
                        self.error(last_user)
                    self._free_lock()
                count = 0
            time.sleep(1)

    def _create_file(self, file_name: str) -> None:
        """Создание пустого файла."""
        if self._global_mode:
            fs_arnsdpsbx.touch(self._global_dir_name + '/' + file_name, recursive=True)
        else:
            with open(self._local_dir_name + '/' + file_name, 'w'):
                pass

    def _get_last_lock_time(self) -> Tuple[int, str]:
        """Получение времени последнего изменения и имени пользователя."""
        data = self._get_queue()
        return data["last_modify"], data["last_user"]

    def _free_lock(self) -> None:
        """Принудительное снятие блокировки очереди."""
        try:
            self._delete_file('lock.busy')
        except Exception:
            pass
        try:
            self._create_file('lock.free')
        except Exception:
            pass

    def _check_queue_name(self, load_name: str) -> bool:
        """Проверка существования очереди по имени."""
        if self._global_mode:
            try:
                return fs_arnsdpsbx.exists(self._hdfs_tool_load_dir_path + '/' + load_name)
            except Exception:
                return self._check_queue_name(load_name)
        else:
            return os.path.exists(self._tool_dir_path + '/' + load_name)

    def error(self, user_name: Optional[str] = None) -> None:
        """Выставление статуса об ошибке в случае падения задачи."""
        if user_name is None:
            user_name = self._user_name
        self._create_file(f'/err_{user_name}')
        
    def _end_load(self) -> int:
        """Сброс состояния класса и остановка сервера Podnet."""
        logger.info("Завершение работы!")
        self._isConnect = False
        self._user_name = None
        self._global_mode = False
        self._queue_name = None
        self._local_dir_name = None
        self._global_dir_name = None
        self._loader_mode = False

        if self.podnet is not None:
            self.podnet.kill()
        self.podnet = None
        return 0
    
    def _move_from_in_progress(self, data: Dict[str, Any], worker: str, is_last_error: bool = False) -> None:
        """Перемещение задач из in_process в end_partitions или обратно в last_partitions."""
        if data["in_process"].get(worker, None) is not None:
            last_partitions = data["in_process"].pop(worker, None)
            correct_list = "last_partitions" if is_last_error else "end_partitions"
            if data[correct_list] is None:
                data[correct_list] = last_partitions
            else:
                data[correct_list] += last_partitions
    
    def _clear_deads(self, data: Dict[str, Any], deads: List[str]) -> None:
        """Очистка данных от 'упавших' воркеров."""
        for dead_worker in deads:
            data['workers'].pop(dead_worker, None)
            self._move_from_in_progress(data, dead_worker, True)

    def _data_analysis(self, data: Dict[str, Any], is_last_error: bool) -> Dict[str, Any]:
        """Анализ состояния очереди: проверка воркеров, обновление статусов и обработка ошибок."""
        if int(time.time()) - data["last_workers_check"] > 20 or self.podnet is None or data["last_partitions"] is None:
            deads = self._network(data['workers'])
            self._clear_deads(data, deads)
            data["last_workers_check"] = int(time.time())
        
        if data["in_process"] is None:
            data["in_process"] = {}
        else:
            self._move_from_in_progress(data, self._user_name, is_last_error)

        for name in os.listdir(self._local_dir_name):
            try:
                if name[:4] in ('err_', 'yes_'):
                    proc_name = name[4:]
                    self._move_from_in_progress(data, proc_name, name[:4] == 'err_')
                    proc_partitions = data["in_process"].get(proc_name, None)
                    self._delete_file(name)
            except Exception:
                continue
        return data
    
    
    def _network(self, workers: Dict[str, List[Any]]) -> List[str]:
        """P2P проверка активности воркеров и регистрация собственного сервера."""
        if self.podnet is None:
            self.podnet = Podnet(logger)
            def podnet_function(data: Dict[str, Any]) -> Any:
                if data['action'] == 'test':
                    try:
                        return self._isConnect
                    except Exception as e:
                        return False
                else:
                    logger.error("Что-то не так с проверкой соединения!")
            self.podnet.set_func(podnet_function)
            port = self.podnet.find_free_port()
            self.podnet.create_server(port)
            workers[self._user_name] = [self.podnet.get_ip(), port]
            
        dead_workers = []
        for key in workers.keys():
            if key != self._user_name:
                ip, port = workers[key][0], workers[key][1]
                if ip == self.podnet.my_ip and port == self.podnet.port:
                    dead_workers.append(key)
                    continue
                try:
                    self.podnet.connect(key, ip, port)
                    response = self.podnet.send(key, {'user': self._user_name, 'action': 'test'}, timeout=2)
                    if response["status"] != "ok" or not response["data"]:
                        dead_workers.append(key)
                except Exception as e:
                    dead_workers.append(key)
        return dead_workers
    
    def get_next(self, count: int = 1, is_last_error: bool = False) -> Optional[List[Any]]:
        """Получение следующей партии элементов из очереди."""
        if not self._isConnect:
            logger.error("Загрузка не создана!")
            raise Exception("Загрузка не создана!")
        self._create_lock()
        data = self._get_queue()
        new_data = self._data_analysis(data, is_last_error)

        new_partitions = None
        if new_data["last_partitions"] is not None:
            if count >= len(new_data["last_partitions"]):
                new_partitions = new_data["last_partitions"]
                new_data["last_partitions"] = None
            else:
                new_partitions = new_data["last_partitions"][:count]
                new_data["last_partitions"] = new_data["last_partitions"][count:]
            new_data["in_process"][self._user_name] = new_partitions
        else:
            new_data["workers"].pop(self._user_name, None)

        new_time = int(time.time())
        new_data["last_modify"] = new_time
        new_data["last_user"] = self._user_name
        self._save_queue(new_data)
        if new_partitions is None and not self._loader_mode:
            self._end_load()
        return new_partitions

    def new_queue(self, partitions: List[Any], global_mode: bool = False,
                  queue_name: str = f'new_queue{str(random.random())[3:]}', loader_mode: bool = False) -> None:
        """Создание новой очереди."""
        self._global_mode = global_mode
        self._loader_mode = loader_mode
        if type(global_mode) != type(True):
            raise Exception(f"Global_mode должен иметь тип Boolean, но получил на входе {type(global_mode)}!")

        if not self._loader_mode and global_mode and self._check_queue_name(queue_name):
            logger.warning(f"Перезапись существующей загрузки'{queue_name}'!")

        self._queue_name = queue_name
        self._local_dir_name = f"{self._tool_dir_path}/{self._queue_name}"
        self._global_dir_name = f"{self._hdfs_tool_load_dir_path}/{self._queue_name}"

        self._set_queue(partitions)
        self._user_name = f"{global_config.get('user_id', 'user')}_{str(random.random())[2:5]}"
        self._isConnect = True

    def connect(self, queue_name: str, global_mode: bool = False, loader_mode: bool = False) -> bool:
        """Подключение к существующей очереди."""
        self._global_mode = global_mode
        if type(global_mode) != type(True):
            raise Exception(f"Global_mode должен иметь тип Boolean, но получил на входе {type(global_mode)}!")
        if global_mode and not self._check_queue_name(queue_name):
            logger.error(f"Загрузки '{queue_name}' не существует!")
            return False
        self._loader_mode = loader_mode
        self._queue_name = queue_name
        self._local_dir_name = f"{self._tool_dir_path}/{self._queue_name}"
        self._global_dir_name = f"{self._hdfs_tool_load_dir_path}/{self._queue_name}"

        if global_mode:
            os.makedirs(os.path.dirname(self._local_dir_name), exist_ok=True)
            
        self._user_name = f"{global_config.get('user_id', 'user')}_{str(random.random())[2:5]}"
        self._isConnect = True
        return True


class DistTask:
    """Главный класс для управления распределенными задачами."""
    def __init__(self, local_path: Optional[str] = None, hdfs_path: Optional[str] = None, logger_file: Optional[str] = None) -> None:
        """Инициализация распределенной задачи."""
        global logger, global_config
        if logger_file is not None:
            logger.change_logger_file(logger_file)
        self._queue = Queue(local_path, hdfs_path)

        self._load_name = None
        self._isConnect = False
        self._global_mode = False

        self._tool_dir_path = (global_config.get("local_path") if local_path is None else local_path) + '/loads'
        self._hdfs_tool_load_dir_path = (global_config.get("hdfs_path") if hdfs_path is None else hdfs_path) + '/loads'
        self._local_dir_name = None
        self._global_dir_name = None

        self._function = None
        self._context = None
        
    def reload_class(self, local_path: Optional[str] = None, hdfs_path: Optional[str] = None, logger_file: Optional[str] = None) -> "DistTask":
        """Перезагрузка модуля и создание нового экземпляра класса."""
        module = sys.modules[__name__]
        importlib.reload(module)
        return module.DistTask(local_path, hdfs_path, logger_file)
    
    def set_context(self, context: Dict[str, Any]) -> None:
        """Передача локальных аргументов (контекста) для функции."""
        self._context = context

    def _set_loading(self, partitions: List[Any], function: Callable) -> None:
        """Подготовка директории, сериализация функции и создание очереди."""
        try:
            shutil.rmtree(self._local_dir_name)
        except Exception:
            pass
        os.makedirs(self._local_dir_name, exist_ok=True)
        write_dill(function, self._local_dir_name + '/function.dill')
        self._queue.new_queue(partitions, self._global_mode, self._load_name, loader_mode=True)

    def _end_load(self) -> None:
        """Сброс состояния и завершение задачи."""
        self._local_dir_name = None
        self._global_dir_name = None
        self._function = None
        self._context = None
        self._load_name = None
        self._isConnect = False
        self._global_mode = False

        self._queue._end_load()

    def new_load(self, partitions: List[Any], function: Callable, global_mode: bool = False,
                 load_name: str = f'new_load{str(random.random())[3:]}', context: Optional[Dict[str, Any]] = None, message: Optional[str] = None) -> None:
        """Создание новой распределённой загрузки."""
        self._queue._global_mode = self._global_mode = global_mode
        if not isinstance(global_mode, bool):
            raise Exception(f"Global_mode должен иметь тип Boolean, но получил на входе {type(global_mode)}!")

        number_of_params = len(inspect.signature(function).parameters)
        if number_of_params not in (1, 2):
            raise Exception(
                f"функция должна принимать 1 или 2 аргумента (список партиций и контекст (опционально)), но принимает {number_of_params}!")

        if global_mode and self._queue._check_queue_name(load_name):
            logger.warning(f"Перезапись существующей загрузки'{load_name}'!")

        self._load_name = load_name
        self._local_dir_name = f"{self._tool_dir_path}/{self._load_name}"
        self._global_dir_name = f"{self._hdfs_tool_load_dir_path}/{self._load_name}"

        def message_function() -> Tuple[Callable, Optional[str]]:
            return function, message

        self._set_loading(partitions, message_function)
        self._function = function
        self._context = context
        self._isConnect = True

    def connect(self, load_name: str, context: Optional[Dict[str, Any]] = None, global_mode: bool = False, function: Optional[Callable] = None) -> Optional[bool]:
        """Подключение к существующей распределённой загрузке."""
        self._global_mode = global_mode
        if type(global_mode) != type(True):
            raise Exception(f"Global_mode должен иметь тип Boolean, но получил на входе {type(global_mode)}!")

        if function is not None:
            number_of_params = len(inspect.signature(function).parameters)
            if number_of_params not in (1, 2):
                raise Exception(
                    f"функция должна принимать 1 или 2 аргумента (список партиций и контекст (опционально)), но принимает {number_of_params}!")

        self._load_name = load_name
        self._local_dir_name = f"{self._tool_dir_path}/{self._load_name}"
        self._global_dir_name = f"{self._hdfs_tool_load_dir_path}/{self._load_name}"

        if not self._queue.connect(load_name, global_mode, loader_mode=True):
            return None

        if global_mode:
            os.makedirs(os.path.dirname(self._local_dir_name), exist_ok=True)
            fs_arnsdpsbx.get(self._global_dir_name, self._tool_dir_path + '/', recursive=True)

        try:
            loaded_func = read_dill(self._local_dir_name + '/function.dill')
            if loaded_func is None:
                raise ValueError("read_dill вернул None")
            self._function, message = loaded_func()
        except Exception as e:
            logger.error(f"Не удалось прочитать функцию: {e}")
            raise Exception("Не удалось прочитать функцию")
            
        self._context = context
        if function is not None:
            self._function = function
        if message is not None:
            print(message)

        self._isConnect = True

    def start(self, count_part: int = 1) -> Optional[int]:
        """Начало обработки данных."""
        logger.info(f"user_name = {self._queue._user_name}")
        count_err = 0
        last_err = False
        if not self._isConnect:
            raise Exception(f"Загрузка не создана!")
        while count_err != 5:
            try:
                parts = self._queue.get_next(count_part, last_err)
                if parts is None:
                    self._end_load()
                    return None
                self._function(parts) if len(inspect.signature(self._function).parameters) == 1 else self._function(parts, self._context)
                logger.info(f"{parts} is over!!!")
                count_err = 0
                last_err = False
            except KeyboardInterrupt:
                self._queue.error()
                self._end_load()
                return -1
            except Exception as e:
                self._queue.error()
                last_err = True
                logger.error(f"Ошибка: {e}")
                count_err += 1
        self._end_load()
