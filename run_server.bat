@echo off
echo =======================================================
echo   YouTube Automation Tool - Server Launcher
echo =======================================================
echo.
echo Starting the Flask Server...
echo.

:: Try 'py' launcher first (Windows Python Launcher)
where py >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Using Python Launcher (py)...
    py main.py
    goto end
)

:: Try running with global python
where python >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Using system Python...
    python main.py
    goto end
)

:: Try running with absolute path to Python 3.9
if exist "C:\Users\irfan laptop\AppData\Local\Programs\Python\Python39\python.exe" (
    echo [INFO] Using custom Python 3.9 from AppData...
    "C:\Users\irfan laptop\AppData\Local\Programs\Python\Python39\python.exe" main.py
    goto end
)

:: Try Python312 in C:\
if exist "C:\Python312\python.exe" (
    echo [INFO] Using Python 3.12 from C:\Python312...
    "C:\Python312\python.exe" main.py
    goto end
)

echo [ERROR] Python was not found on your system!
echo Please make sure Python is installed and added to your system PATH.
echo.

:end
pause
