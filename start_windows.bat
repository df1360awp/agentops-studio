@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [AgentOps] Opening local model settings...
echo [AgentOps] Paste your Qwen API Key in the browser.
powershell -NoProfile -Command "try { $r=Invoke-RestMethod 'http://127.0.0.1:8766/api/health' -TimeoutSec 2; if($r.ok){exit 0}else{exit 1} } catch {exit 1}"
if not errorlevel 1 (
    start "" "http://127.0.0.1:8766/?view=modelsettings"
    exit /b 0
)
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python"))
%PY% -c "import fastapi, uvicorn, multipart" >nul 2>nul
if errorlevel 1 (
  echo Dependencies missing. Installing once via pip...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 (echo Dependencies could not be installed. Check network or pip. & pause & exit /b 1)
)
start "" "http://127.0.0.1:8766/?view=modelsettings"
%PY% -m uvicorn app.main:app --host 127.0.0.1 --port 8766
pause