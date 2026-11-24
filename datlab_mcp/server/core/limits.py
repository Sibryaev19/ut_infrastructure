"""Числовые лимиты и общие константы сервера.

Все значения собраны здесь, чтобы поведение тулов менялось в одном месте,
а `workspace_info` отдавал агенту те же цифры, по которым реально работает сервер.
"""

# read_file
READ_DEFAULT_LINES = 2000
READ_MAX_LINES = 2000
READ_MAX_BYTES = 64 * 1024          # сколько байт отдаём в одном ответе
MAX_LINE_CHARS = 2000              # строка длиннее — обрезаем с маркером
TOTAL_SCAN_BYTES = 32 * 1024 * 1024  # до этого размера досчитываем total_lines

# write_file / edit_file
WRITE_MAX_BYTES = 1 * 1024 * 1024
EDIT_MAX_BYTES = 10 * 1024 * 1024

# list_dir
LIST_MAX_ENTRIES = 200

# glob / grep
SEARCH_MAX_RESULTS = 100
SEARCH_MAX_LINE_CHARS = 2048
SEARCH_MAX_FILES = 20000            # предохранитель от обхода гигантских деревьев
SEARCH_MAX_FILE_BYTES = 5 * 1024 * 1024  # файлы крупнее grep не читает

# bash
BASH_DEFAULT_TIMEOUT_MS = 120_000
BASH_MAX_TIMEOUT_MS = 600_000
BASH_MIN_TIMEOUT_MS = 1_000
BASH_MAX_INLINE_CHARS = 30_000      # столько выводим агенту, остальное — в spill-файл
BASH_CAPTURE_MAX_BYTES = 2 * 1024 * 1024  # сколько держим в памяти до спилла

# Общее
BINARY_SNIFF_BYTES = 8192           # сколько байт смотрим на NUL
IGNORED_DIRS = frozenset({
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env",
    "node_modules", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".ipynb_checkpoints", ".tox", ".idea", ".vscode",
})

# Каталоги, в которых лежат временные файлы атомарной записи
TMP_PREFIX = ".datalab-tmp-"
