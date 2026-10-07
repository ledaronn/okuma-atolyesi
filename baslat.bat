@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Once kur.bat dosyasini calistirin.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" app.py %*
if errorlevel 1 pause
