@echo off
cd /d D:\Code\AI
set OLLAMA_NUM_PARALLEL=5
echo Starting document summarizer (5 workers)...
echo.
"C:\Users\peteb\AppData\Local\Programs\Ollama\ollama.exe" serve >nul 2>&1
"C:\Users\peteb\AppData\Local\Programs\Python\Python312\python.exe" summarizer.py
pause
