@echo off
setlocal
cd /d "%~dp0"
python -X utf8 feelens.py build
set "FEELENS_RESULT=%ERRORLEVEL%"
pause
exit /b %FEELENS_RESULT%
