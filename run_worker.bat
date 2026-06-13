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
:restart
echo [%date% %time%] Starting Query Worker...
echo.
"C:\Users\peteb\AppData\Local\Programs\Python\Python312\python.exe" query_worker.py
set WORKER_EXIT=%errorlevel%

echo.
echo [%date% %time%] Worker stopped (exit code: %WORKER_EXIT%). Checking services...

:: Check if Ollama is hung (process exists but not responding)
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find "ollama.exe" >nul
if not errorlevel 1 (
    curl -s --max-time 4 http://localhost:11434/ >nul 2>&1
    if errorlevel 1 (
        echo [%date% %time%] Ollama is hung. Restarting it...
        taskkill /F /IM ollama.exe >nul 2>&1
        timeout /t 2 /nobreak >nul
        start "" /B "C:\Users\peteb\AppData\Local\Programs\Ollama\ollama.exe" serve
        timeout /t 4 /nobreak >nul
        echo [%date% %time%] Ollama restarted.
    ) else (
        echo [%date% %time%] Ollama is responsive.
    )
) else (
    echo [%date% %time%] Ollama not running. Starting it...
    start "" /B "C:\Users\peteb\AppData\Local\Programs\Ollama\ollama.exe" serve
    timeout /t 4 /nobreak >nul
)

echo [%date% %time%] Restarting worker in 5 seconds... Close this window or Ctrl+C to stop.
timeout /t 5 /nobreak >nul
goto restart
