#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -c "import fastapi,uvicorn,multipart" 2>/dev/null || python3 -m pip install -r requirements.txt
printf 'Open http://127.0.0.1:8765\n'
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765
