@echo off
setlocal
cd /d "%~dp0"
echo NEAR FeeLens - borrador local. No conecta billeteras ni consulta RPC.
echo Abre http://127.0.0.1:8767 en tu navegador despues del mensaje de inicio.
echo Ctrl+C detiene el servidor. Esta ventana debe permanecer abierta.
python -u -X utf8 feelens.py serve --port 8767
set "FEELENS_RESULT=%ERRORLEVEL%"
pause
exit /b %FEELENS_RESULT%
