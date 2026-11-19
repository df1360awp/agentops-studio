@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [AgentOps] Launching the local AI Operations Studio...
where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)
%PY% -c "import fastapi, uvicorn, multipart" >nul 2>nul
if errorlevel 1 (
  echo Dependencies missing. Installing once via pip...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 (echo Dependencies could not be installed. Check network or pip. & pause & exit /b 1)
)
start "" http://127.0.0.1:8765
%PY% -m uvicorn app.main:app --host 127.0.0.1 --port 8765
pause
