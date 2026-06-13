@echo off
cd /d D:\Code\AI
echo Starting RAG ingester (D:\RAG -> Qdrant)...
echo.
"C:\Users\peteb\AppData\Local\Programs\Python\Python312\python.exe" rag_ingester.py
pause
