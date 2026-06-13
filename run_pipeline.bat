@echo off
cd /d D:\Code\AI
set OLLAMA_NUM_PARALLEL=5
echo Starting RAG Pipeline (summarizer + ingester)...
echo.
"C:\Users\peteb\AppData\Local\Programs\Python\Python312\python.exe" pipeline.py
pause
