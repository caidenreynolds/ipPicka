@echo off
setlocal
cd /d "%~dp0"
if not "%OS%"=="Windows_NT" (
    echo Run this script on Windows 10 or 11.
    exit /b 1
)
if exist ".venv-build\Scripts\python.exe" goto ready
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 -m venv .venv-build
if errorlevel 1 goto failed
goto ready
:use_python
where python >nul 2>nul
if errorlevel 1 (
    echo Install Python 3 with Tcl/Tk from https://www.python.org/downloads/windows/ first.
    goto failed
)
python -m venv .venv-build
if errorlevel 1 goto failed
:ready
".venv-build\Scripts\python.exe" -c "import tkinter"
if errorlevel 1 goto failed
".venv-build\Scripts\python.exe" -m pip --disable-pip-version-check install "PyInstaller>=6.20,<7"
if errorlevel 1 goto failed
".venv-build\Scripts\python.exe" -m unittest -v
if errorlevel 1 goto failed
".venv-build\Scripts\python.exe" -m PyInstaller --clean --noconfirm ipPicka.spec
if errorlevel 1 goto failed
echo.
echo Built: %CD%\dist\ipPicka.exe
echo The executable requests administrator privileges when launched.
pause
exit /b 0
:failed
echo.
echo Build failed. Review the error above. Close any running ipPicka before rebuilding.
pause
exit /b 1
