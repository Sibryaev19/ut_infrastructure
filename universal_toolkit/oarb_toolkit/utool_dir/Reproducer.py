import subprocess
from pathlib import Path
from typing import List, Optional
import sqlfluff, ruff
import os
import re
import pexpect

class CodeLinter:
    def __init__(self, rc_py='pylintrc'):
        self.rc_py = rc_py
    
    def _run(self, filepath, rcfile, disable=None):
        cmd = ['pylint', filepath, f'--rcfile={rcfile}']
        if disable:
            cmd.append(f'--disable={",".join(disable)}')
        return subprocess.run(cmd, capture_output=True, text=True)
    
    def _find(self, path, ext, exclude=None):
        path = Path(path)
        if path.is_file() and path.suffix == ext:
            return [str(path)]
        exclude = exclude or []
        return [str(f) for f in path.rglob(f'*{ext}') 
                if not any(x in f.name for x in exclude)]
    
    def check_py(self, path, disable=None, exclude=None):
        files = self._find(path, '.py', exclude or ['checkpoint'])
        for f in files:
            result = self._run(f, self.rc_py, disable)
            print(f"{'✅' if result.returncode==0 else '❌'} {f}")
            if result.returncode != 0:
                print(result.stdout)
    
    def check_sql(self, path, dialect):
        files = self._find(path, '.sql', ['checkpoint'])
        for f in files:
            result = subprocess.run(['sqlfluff', 'lint', f, f'--dialect={dialect}'], 
                                    capture_output=True, text=True)
            print(f"{'✅' if result.returncode==0 else '❌'} {f}")
            if result.returncode != 0:
                print(result.stdout)

    def fix_sql(self, path, dialect):
        """Авто-исправление SQL файла"""
        result = subprocess.run(['sqlfluff', 'fix', path, f'--dialect={dialect}'], 
                                capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)

    def fix_py(self, path):
        """Автоматически исправляет Python файл через ruff"""

        # Форматирование
        result_format = subprocess.run(['ruff', 'format', path], capture_output=True, text=True)

        # Исправление ошибок
        result_fix = subprocess.run(['ruff', 'check', '--fix', '--unsafe-fixes', path], 
                                    capture_output=True, text=True)

        # Вывод результатов
        if result_format.stdout:
            print(result_format.stdout)
        if result_fix.stdout:
            print(result_fix.stdout)
