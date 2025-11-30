@echo off
cd /d %~dp0backend
echo Starting TabSensei Backend Server...
echo.
echo Make sure Ollama is running on http://localhost:11434
echo.
python -m uvicorn agent_server:app --host 0.0.0.0 --port 8000 --reload
pause

