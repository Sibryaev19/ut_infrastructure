import os
import zipfile
import argparse
from datetime import datetime
import base64
import sys


class TransferConverter:
    def __init__(self, add_extension='.txt', remove_extension='.txt'):
        self.add_extension = add_extension
        self.remove_extension = remove_extension

    def create_zip_with_renamed_files(self, source_dir, output_zip=None, preserve_structure=True):
        """
        Создает ZIP-архив с файлами, у которых изменены расширения.
        В архиве будет папка с переименованными файлами.

        Args:
            source_dir: Исходная папка
            output_zip: Путь к выходному ZIP-архиву (None - создаст автоматически)
            preserve_structure: Сохранять ли структуру папок внутри архива
        """
        source_dir = os.path.abspath(source_dir)
        if not os.path.exists(source_dir):
            raise FileNotFoundError(f"Папка не найдена: {source_dir}")

        # Генерируем имя архива, если не указано
        if output_zip is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dir_name = os.path.basename(source_dir)
            parent_dir = os.path.dirname(source_dir)
            output_zip = os.path.join(parent_dir, f"{dir_name}_renamed_{timestamp}.zip")

        print(f"Исходная папка: {source_dir}")
        print(f"Создание архива: {output_zip}")
        print(f"Добавляемое расширение: {self.add_extension}")

        file_count = 0
        folder_name = os.path.basename(source_dir)

        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(source_dir):
                for filename in files:
                    file_path = os.path.join(root, filename)

                    # Определяем относительный путь от исходной директории
                    rel_path = os.path.relpath(root, source_dir)

                    # Формируем путь внутри архива с сохранением структуры
                    if preserve_structure and rel_path != '.':
                        # Внутри папки архива сохраняем оригинальную структуру
                        arcname = os.path.join(folder_name, rel_path, filename + self.add_extension)
                    else:
                        # Только папка архива, без внутренней структуры
                        arcname = os.path.join(folder_name, filename + self.add_extension)

                    # Добавляем файл в архив
                    zipf.write(file_path, arcname)
                    file_count += 1

                    if file_count % 100 == 0:
                        print(f"Обработано файлов: {file_count}")

        print(f"\nГотово! Обработано файлов: {file_count}")
        print(f"Архив сохранен: {output_zip}")
        return output_zip

    def extract_and_restore_names(self, zip_path, extract_to=os.getcwd()):
        """
        Извлекает архив и восстанавливает оригинальные имена файлов.
        """
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"Архив не найден: {zip_path}")

        os.makedirs(extract_to, exist_ok=True)

        print(f"Извлечение архива: {zip_path}")
        print(f"Папка назначения: {extract_to}")

        # Извлекаем файлы
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            zipf.extractall(extract_to)

        # Восстанавливаем имена файлов
        restored_count = 0
        for root, dirs, files in os.walk(extract_to):
            for filename in files:
                if filename.endswith(self.remove_extension):
                    old_path = os.path.join(root, filename)
                    new_filename = filename[:-len(self.remove_extension)]
                    new_path = os.path.join(root, new_filename)

                    # Проверяем, нет ли конфликта имен
                    if os.path.exists(new_path):
                        # Добавляем суффикс, если файл уже существует
                        base, ext = os.path.splitext(new_filename)
                        counter = 1
                        while os.path.exists(new_path):
                            new_filename = f"{base}_{counter}{ext}"
                            new_path = os.path.join(root, new_filename)
                            counter += 1

                    os.rename(old_path, new_path)
                    restored_count += 1

        print(f"Восстановлено файлов: {restored_count}")
        print(f"Файлы извлечены в: {extract_to}")
        return extract_to
    
    def bin_file_to_base64(self, file_name):
        binary_file = file_name
        output_file = binary_file + '.b64'

        if not os.path.exists(binary_file):
            print(f"Файл {binary_file} не найден!")
            sys.exit(1)

        print(f"Кодирую {binary_file} в base64...")

        with open(binary_file, 'rb') as f:
            binary_data = f.read()

        b64_data = base64.b64encode(binary_data).decode('utf-8')

        with open(output_file, 'w') as f:
            f.write(b64_data)

        print(f"Готово: {output_file}")
        print(f"Размер: {len(b64_data)} символов")
    
    def base64_to_bin_file(self, file_name):
        b64_file = file_name
        binary_file = b64_file.replace('.b64', '')

        if not os.path.exists(b64_file):
            print(f"Файл {b64_file} не найден!")
            sys.exit(1)

        print(f"Декодирую {b64_file}...")

        with open(b64_file, 'r') as f:
            b64_data = f.read().strip()

        binary_data = base64.b64decode(b64_data)

        with open(binary_file, 'wb') as f:
            f.write(binary_data)

        os.chmod(binary_file, 0o755)  # +x права

        print(f"Готово: {binary_file}")
        print("Проверьте: file app-linux")
