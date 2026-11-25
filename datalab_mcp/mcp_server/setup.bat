@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem setup.bat - find Python >= 3.10 and run setup\setup.py with it.
rem All install logic (venv, pip, agent config) lives in setup\setup.py.
rem Set SETUP_NOPAUSE=1 to skip the final pause (for automation).

set "ROOT=%~dp0"
set "CAND=%TEMP%\datalab_python_%RANDOM%%RANDOM%.txt"
type nul > "%CAND%" 2>nul

echo == datalab_mcp setup: searching Python ^>= 3.10 ==

call :try_python "%PYTHON%"

for /f "delims=" %%P in ('where python 2^>nul') do call :try_python "%%P"

for /f "delims=" %%L in ('py -0p 2^>nul') do call :try_py_line "%%L"

call :registry_candidates
call :dir_candidates

set "BEST_VER=03009"
set "BEST="
for /f "usebackq tokens=1,* delims=|" %%A in ("%CAND%") do (
  if %%A GEQ 03010 if %%A GTR !BEST_VER! (
    set "BEST_VER=%%A"
    set "BEST=%%B"
  )
)
del "%CAND%" >nul 2>&1

if not defined BEST goto :no_python

echo [+] python: "%BEST%"
echo.
"%BEST%" "%ROOT%setup\setup.py" %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (echo setup finished) else (echo setup failed, exit code %RC%)
goto :finish

:no_python
echo [ERROR] Python 3.10 or newer was not found.
echo         Install Python 3.10+ or set PYTHON to a full path of python.exe.
set "RC=2"

:finish
if not "%SETUP_NOPAUSE%"=="1" pause
exit /b %RC%

rem ---------------------------------------------------------------- candidates

:try_python
rem Validate a candidate and remember "N|resolved path" when it is 3.x.
set "P=%~1"
if "%P%"=="" exit /b
if not exist "%P%" exit /b
"%P%" -c "import sys;v=sys.version_info;print(f'{v[0]*1000+v[1]:05d}|{sys.executable}')" >> "%CAND%" 2>nul
exit /b

:try_py_line
rem Line from "py -0p": take "-V:3.12" and ask the launcher itself, so paths
rem with spaces are resolved by py.exe and do not need parsing here.
set "L=%~1"
if "%L%"=="" exit /b
for /f "usebackq tokens=1" %%V in ('%L%') do set "TAG=%%V"
set "VER=%TAG:-V:=%"
if "%VER%"=="" exit /b
py -%VER% -c "import sys;v=sys.version_info;print(f'{v[0]*1000+v[1]:05d}|{sys.executable}')" >> "%CAND%" 2>nul
exit /b

:registry_candidates
for %%K in ("HKLM\SOFTWARE\Python\PythonCore" "HKCU\SOFTWARE\Python\PythonCore") do (
  for /f "tokens=2,*" %%A in ('reg query %%K /s /v ExecutablePath 2^>nul ^| findstr /i "ExecutablePath"') do call :try_python "%%B"
)
exit /b

:dir_candidates
rem %ProgramFiles(x86)% must be copied first: the parentheses break a for block.
set "PF86=%ProgramFiles(x86)%"
for %%B in ("%ProgramFiles%" "%PF86%" "%LOCALAPPDATA%\Programs") do (
  if exist "%%~fB" (
    for /d %%D in ("%%~fB\Python3*") do call :try_python "%%~fD\python.exe"
  )
)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do call :try_python "%%~fD\python.exe"
for /d %%D in ("C:\Python3*") do call :try_python "%%~fD\python.exe"
exit /b
