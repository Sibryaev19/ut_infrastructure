import requests
import threading
import http.server
import socketserver
import socket
import logging
import subprocess
import json
import time
from typing import Any, Callable, Optional, List, Dict, Tuple


def setup_logger(log_to_file: bool = False, log_file: str = 'app.log', level: int = logging.INFO) -> logging.Logger:
    """Настройка логгера. 

    Args:
        log_to_file (bool, optional): Писать логи в файл, иначе в консоль. Defaults to False.
        log_file (str, optional): Имя файла для логов. Defaults to 'app.log'.
        level (int, optional): Уровень логирования. Defaults to logging.INFO.

    Returns:
        logging.Logger: Настроенный объект логгера.
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


class Podnet:
    def __init__(self, logger=None) -> None:
        """Инициализация P2P сетевого слоя."""
        self.logger = logger or setup_logger()
        self.server = None
        self.server_thread = None
        self.peers = {}
        self.my_ip = self._get_ip()
        self._lock = threading.Lock()
        self.func = None
        self.port = None

    def _get_ip(self) -> str:
        """Определяет реальный IP-адрес контейнера в локальной сети."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            s.close()

    def get_ip(self) -> str:
        """Возвращает IP-адрес текущего контейнера.
        Returns:
            str: IP-адрес.
        """
        return self.my_ip

    def create_server(self, port: int) -> int:
        """Запуск HTTP-сервера для приёма запросов от других контейнеров.
        Args:
            port (int): Порт для запуска сервера.
        Returns:
            int: Порт, на котором запущен сервер.
        Raises:
            Exception: Если не удалось запустить сервер на указанном порту.
        """
        podnet_obj = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    raw = self.rfile.read(length)
                    data = json.loads(raw)
                    
                    if podnet_obj.func:
                        try:
                            result = podnet_obj.func(data)
                            response_data = {"status": "ok", "data": result}
                        except Exception as e:
                            response_data = {"status": "error", "error": str(e)}
                    else:
                        response_data = {"status": "error", "error": "No handler set"}
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(response_data).encode())
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())

            def log_message(self, *args):
                pass

        try:
            self.server = socketserver.TCPServer(("0.0.0.0", port), Handler)
            self.server.allow_reuse_address = True
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            self.port = port
            self.logger.info(f"✅ Сервер на порту {port}")
            return port
        except OSError as e:
            raise Exception(f"Не удалось запустить Podnet на порту {port}: {e}")

            
    def set_func(self, func: Callable[[Dict[str, Any]], Any]) -> None:
        """Устанавливает функцию-обработчик для входящих запросов.
        Args:
            func (Callable[[Dict[str, Any]], Any]): Функция, принимающая JSON-данные.
        """
        self.func = func

        
    def connect(self, name: str, ip: str, port: int) -> None:
        """Регистрирует пир (другой контейнер) для отправки запросов.

        Args:
            name (str): Имя пира.
            ip (str): IP-адрес пира.
            port (int): Порт пира.
        """
        with self._lock:
            self.peers[name] = (ip, port)

            
    def send(self, name: str, request: Dict[str, Any], retries: int = 1, timeout: int = 5) -> Optional[Dict[str, Any]]:
        """Отправка HTTP-запроса контейнеру-пиру.

        Args:
            name (str): Имя пира.
            request (Dict[str, Any]): Словарь с данными запроса.
            retries (int, optional): Количество попыток. Defaults to 1.
            timeout (int, optional): Таймаут запроса в секундах. Defaults to 5.

        Returns:
            Optional[Dict[str, Any]]: Ответ от пира или None, если запрос не удался.
        """
        with self._lock:
            if name not in self.peers:
                self.logger.error(f"❌ Пир '{name}' не найден")
                return None
            ip, port = self.peers[name]
        
        for attempt in range(retries):
            try:
                resp = requests.post(
                    f"http://{ip}:{port}", 
                    json=request, 
                    timeout=timeout
                )
                if resp.status_code == 200:
                    return resp.json()
                else:
                    self.logger.warning(f"⚠️ Статус {resp.status_code} от '{name}'")
                    return None
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(0.5 * (attempt + 1))
                else:
                    self.logger.warning(f"'{name}' (http://{ip}:{port}) не отвечает")
        return None

    
    def get_used_ports(self) -> List[int]:
        """Возвращает отсортированный список занятых TCP-портов.

        Returns:
            List[int]: Список занятых портов.
        """
        try:
            result = subprocess.run(
                ["ss", "-tln"], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            
            ports = set()
            for line in result.stdout.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 4:
                    local_addr = parts[3]
                    port_str = local_addr.rsplit(":", 1)[-1]
                    
                    if port_str.isdigit():
                        ports.add(int(port_str))
                        
            return sorted(list(ports))
        
        except Exception as e:
            self.logger.warning(f"⚠️ Не удалось получить список портов через ss: {e}")
            # Фоллбэк: если ss нет, пробуем прочитать /proc/net/tcp (низкоуровневый способ)
            return self._get_ports_from_proc()

        
    def _get_ports_from_proc(self) -> List[int]:
        """Аварийный способ получения портов через чтение /proc/net/tcp."""
        ports = set()
        try:
            with open('/proc/net/tcp', 'r') as f:
                for line in f.readlines()[1:]:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        local_addr_hex = parts[1]
                        port_hex = local_addr_hex.split(':')[1]
                        ports.add(int(port_hex, 16))
        except:
            pass
        return sorted(list(ports))

        
    def find_free_port(self, start_port: int = 9000, max_attempts: int = 100) -> int:
        """Находит первый свободный порт, начиная с start_port.

        Args:
            start_port (int, optional): Начальный порт для поиска. Defaults to 9000.
            max_attempts (int, optional): Максимальное количество попыток. Defaults to 100.

        Returns:
            int: Свободный порт.

        Raises:
            Exception: Если свободный порт не найден в заданном диапазоне.
        """
        for port in range(start_port, start_port + max_attempts):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    # Пытаемся занять порт. Если получилось — он 100% свободен.
                    s.bind(("0.0.0.0", port))
                    # Сокет закрывается автоматически (благодаря with), 
                    # но порт остается свободным для нашего HTTP-сервера.
                    return port
                except OSError:
                    # Порт занят (или нет прав), пробуем следующий
                    continue
        raise Exception(f"Не удалось найти свободный порт в диапазоне {start_port}-{start_port + max_attempts}")

            
    def kill(self) -> None:
        """Останавливает HTTP-сервер и завершает фоновый поток."""
        if self.server:
            try:
                shutdown_thread = threading.Thread(target=self.server.shutdown)
                shutdown_thread.start()
                shutdown_thread.join(timeout=5)
                self.server.server_close()
                self.server = None
                self.server_thread = None
                self.logger.info(f"🛑 Podnet port={self.port} остановлен")
            except Exception as e:
                self.logger.error(f"⚠️ Ошибка остановки: {e}")
