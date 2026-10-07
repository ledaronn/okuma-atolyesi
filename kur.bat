@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto nopy
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 goto nopy
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Kurulum tamam. baslat.bat dosyasini acabilirsiniz.
pause
exit /b 0
:nopy
echo Python 3.11 veya daha yeni bir surum gerekli. Python'u kurup yeniden deneyin.
pause
exit /b 1
:failed
echo Kurulum tamamlanamadi. Yukaridaki hata mesajini inceleyin.
pause
exit /b 1
