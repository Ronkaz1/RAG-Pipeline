@echo off
cd /d D:\Code\AI

echo Starting services...

:: Start Qdrant if not running
curl -s http://localhost:6333/ >nul 2>&1
if errorlevel 1 (
    echo Starting Qdrant...
    start "" /B "D:\Code\AI\qdrant\qdrant.exe"
    timeout /t 3 /nobreak >nul
) else (
    echo Qdrant already running.
)

:: Start Ollama if not running
curl -s http://localhost:11434/ >nul 2>&1
if errorlevel 1 (
    echo Starting Ollama...
    start "" /B "C:\Users\peteb\AppData\Local\Programs\Ollama\ollama.exe" serve
    timeout /t 4 /nobreak >nul
) else (
    echo Ollama already running.
)

echo.
echo Starting Document Ingester...
echo.
"C:\Users\peteb\AppData\Local\Programs\Python\Python312\python.exe" ingester.py

pause
