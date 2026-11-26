import os
import threading
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import uvicorn
from tqdm import tqdm
from urllib.parse import quote
import socket
import time

class DataCaster:
    """
    Инструмент для быстрой потоковой передачи больших файлов между двумя машинами в локальной сети.
    """
    def __init__(self):
        self.manifests = {}       # Хранилище доступных загрузок {load_name: {"files": [...]}}
        self.server = None        # Экземпляр uvicorn.Server
        self.server_thread = None # Поток для сервера
        self.base_url = None      # URL для клиента (http://IP:PORT)

    # ==========================================
    # МЕТОДЫ КЛИЕНТА А (РАЗДАЮЩИЙ)
    # ==========================================

    def create_proxy(self, port: int):
        """Запускает HTTP-сервер в фоновом потоке."""
        if self.server is not None:
            print("⚠️ Сервер уже запущен.")
            return

        app = FastAPI()
        caster_instance = self

        @app.get("/ping")
        def ping():
            return {"status": "ok"}

        @app.get("/loads")
        def get_loads():
            return list(caster_instance.manifests.keys())

        @app.get("/manifest/{load_name}")
        def get_manifest(load_name: str):
            if load_name not in caster_instance.manifests:
                raise HTTPException(status_code=404, detail="Load not found")
            return caster_instance.manifests[load_name]

        @app.get("/download/{load_name}/{file_index:int}")
        def download_file(load_name: str, file_index: int):
            if load_name not in caster_instance.manifests:
                raise HTTPException(status_code=404, detail="Load not found")
            
            manifest = caster_instance.manifests[load_name]
            if file_index < 0 or file_index >= len(manifest["files"]):
                raise HTTPException(status_code=404, detail="File index out of range")
                
            file_info = manifest["files"][file_index]
            abs_path = file_info["abs_path"]
            
            if not os.path.exists(abs_path):
                raise HTTPException(status_code=404, detail="File not found on disk")

            print(f"📤 [Сервер А] Клиент начал скачивание: {file_info['rel_path']} ({file_info['size'] / (1024**2):.2f} МБ)")
            # Формируем правильный Content-Disposition с поддержкой кириллицы
            filename_encoded = quote(os.path.basename(abs_path))
            headers = {
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}"
            }
            
            # FileResponse автоматически поддерживает Range-запросы (докачку),
            # не грузит оперативную память и корректно выставляет Content-Length.
            return FileResponse(
                path=abs_path,
                media_type="application/octet-stream",
                headers=headers
            )
        
                # --- НОВЫЙ ЭНДПОИНТ ---
        @app.post("/complete/{load_name}/{file_index:int}")
        def complete_download(load_name: str, file_index: int):
            if load_name in caster_instance.manifests and 0 <= file_index < len(caster_instance.manifests[load_name]["files"]):
                file_info = caster_instance.manifests[load_name]["files"][file_index]
                print(f"✅ [Сервер А] Клиент успешно скачал: {file_info['rel_path']}")
            return {"status": "ok"}

        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="error")
        self.server = uvicorn.Server(config)
        self.server_thread = threading.Thread(target=self.server.run, daemon=True)
        self.server_thread.start()
        
        # Определение локального IP-адреса
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
            
        print(f"🌐 Адрес для подключения: {ip}:{port}")

    def set_load(self, load_name: str, paths: list):
        """Регистрирует список файлов/папок под указанным именем."""
        files = []
        for path in paths:
            if os.path.isdir(path):
                dir_name = os.path.basename(os.path.normpath(path))
                for root, _, files_in_dir in os.walk(path):
                    for fname in files_in_dir:
                        abs_p = os.path.join(root, fname)
                        rel_p = os.path.join(dir_name, os.path.relpath(abs_p, path))
                        files.append({
                            "abs_path": abs_p,
                            "rel_path": rel_p,
                            "size": os.path.getsize(abs_p)
                        })
            elif os.path.isfile(path):
                fname = os.path.basename(path)
                files.append({
                    "abs_path": path,
                    "rel_path": fname,
                    "size": os.path.getsize(path)
                })
            else:
                print(f"❌ Путь '{path}' не найден или недоступен. Пропущен.")
                
        self.manifests[load_name] = {"files": files}
        print(f"✅ Загрузка '{load_name}' добавлена. Файлов: {len(files)}")
        
    def stop(self):
        """Останавливает HTTP-сервер."""
        if self.server:
            self.server.should_exit = True
            if self.server_thread:
                self.server_thread.join(timeout=5)
            self.server = None
            self.server_thread = None
            print("🛑 Сервер остановлен.")
        else:
            print("ℹ️ Сервер не был запущен.")

    # ==========================================
    # МЕТОДЫ КЛИЕНТА Б (СКАЧИВАЮЩИЙ)
    # ==========================================

    def connect(self, address: str):
        """Подключается к серверу (address = 'IP:PORT')."""
        self.base_url = f"http://{address}"
        try:
            resp = requests.get(f"{self.base_url}/ping", timeout=5)
            if resp.status_code == 200:
                print("✅ Успешное подключение к серверу!")
            else:
                self.base_url = None
                raise ConnectionError(f"Неверный ответ сервера: {resp.status_code}")
        except Exception as e:
            self.base_url = None
            raise ConnectionError(f"❌ Не удалось подключиться: {e}")

    def check_loads(self):
        """Возвращает список доступных загрузок."""
        if not self.base_url:
            raise Exception("Сначала вызовите метод connect()")
        resp = requests.get(f"{self.base_url}/loads")
        resp.raise_for_status()
        return resp.json()

    def download(self, load_name: str, local_dir: str, max_retries: int = 1):
        """Скачивает выбранную загрузку в указанную локальную директорию с поддержкой докачки."""
        if not self.base_url:
            raise Exception("Сначала вызовите метод connect()")

        # 1. Получаем манифест
        resp = requests.get(f"{self.base_url}/manifest/{load_name}")
        if resp.status_code == 404:
            print(f"❌ Загрузка '{load_name}' не найдена на сервере.")
            return
        resp.raise_for_status()
        
        manifest = resp.json()
        files = manifest["files"]
        
        os.makedirs(local_dir, exist_ok=True)

        # 2. Поочередно скачиваем файлы
        for index, file_info in enumerate(files):
            rel_path = file_info["rel_path"]
            total_size = file_info["size"]
            dest_path = os.path.join(local_dir, rel_path)
            
            # Создаем вложенные папки
            dest_dir = os.path.dirname(dest_path)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)
            
            url = f"{self.base_url}/download/{load_name}/{index}"
            
            # Проверяем, не скачан ли файл уже полностью
            if os.path.exists(dest_path) and os.path.getsize(dest_path) == total_size:
                print(f"✅ Файл уже полностью скачан ранее: {rel_path}")
                continue

            attempt = 0
            success = False
            
            while attempt < max_retries:
                attempt += 1
                
                # Проверяем, сколько байт уже скачано
                resume_pos = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
                headers = {}
                
                if resume_pos > 0:
                    headers["Range"] = f"bytes={resume_pos}-"
                    print(f"⏩ [Попытка {attempt}] Докачка файла {rel_path} с позиции {resume_pos / (1024**2):.2f} МБ (из {total_size / (1024**2):.2f} МБ)...")
                else:
                    print(f"\n📥 [Попытка {attempt}] Скачивание {rel_path} ({total_size / (1024**2):.2f} МБ) с нуля...")
                
                try:
                    with requests.get(url, stream=True, headers=headers, timeout=60) as r:
                        # 416 означает, что запрошенный диапазон превышает размер файла 
                        # (файл уже скачан полностью)
                        if r.status_code == 416:
                            print(f"✅ Файл уже полностью скачан: {rel_path}")
                            success = True
                            break
                        
                        r.raise_for_status()
                        
                        # Если сервер вернул 206 Partial Content — мы докачиваем.
                        # Если сервер проигнорировал Range и вернул 200 OK — начинаем сначала.
                        if r.status_code == 200 and resume_pos > 0:
                            print("⚠️ Сервер не поддерживает докачку, начинаем с нуля...")
                            resume_pos = 0
                            
                        mode = "ab" if resume_pos > 0 and r.status_code == 206 else "wb"
                        
                        with open(dest_path, mode) as f:
                            with tqdm(total=total_size, initial=resume_pos, unit='B', unit_scale=True, desc=os.path.basename(rel_path)) as pbar:
                                for chunk in r.iter_content(chunk_size=1024*1024):
                                    if chunk: # filter out keep-alive new chunks
                                        f.write(chunk)
                                        pbar.update(len(chunk))
                                        
                    # Проверяем, совпадает ли размер после завершения стрима
                    final_size = os.path.getsize(dest_path)
                    if final_size == total_size:
                        print(f"✅ Завершено: {rel_path}")
                        success = True
                        try:
                            complete_url = f"{self.base_url}/complete/{load_name}/{index}"
                            requests.post(complete_url, timeout=5)
                        except Exception:
                            pass # Если сервер не ответит на пост-запрос, не страшно. Файл уже скачан.
                        break
                    else:
                        print(f"⚠️ Размер не совпадает ({final_size} != {total_size}). Попытка повторить...")
                        
                except Exception as e:
                    # Ловим любую ошибку Requests (включая ChunkedEncodingError)
                    if isinstance(e, requests.exceptions.RequestException):
                        print(f"\n⚠️ Ошибка соединения при скачивании {rel_path}.")
                        if attempt == max_retries:
                            print("🛑 Сервер не отвечает. Превышено количество попыток. Скачивание прервано.")
                            break
                    else:
                        # Если это какая-то другая ошибка (не сетевая), пробрасываем дальше
                        raise e
                    
            if not success:
                print(f"❌ Не удалось скачать файл {rel_path} после {max_retries} попыток.")
                
        print("\n🎉 Процесс скачивания завершен!")