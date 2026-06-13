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

:: Start Ollama if not running or hung
set OLLAMA_NUM_PARALLEL=5
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find "ollama.exe" >nul
if not errorlevel 1 (
    curl -s --max-time 4 http://localhost:11434/ >nul 2>&1
    if errorlevel 1 (
        echo Ollama is hung. Restarting it...
        taskkill /F /IM ollama.exe >nul 2>&1
        taskkill /F /IM "ollama app.exe" >nul 2>&1
        timeout /t 2 /nobreak >nul
        start "" /B "C:\Users\peteb\AppData\Local\Programs\Ollama\ollama.exe" serve
        timeout /t 4 /nobreak >nul
    ) else (
        echo Ollama already running.
    )
) else (
    echo Starting Ollama...
    start "" /B "C:\Users\peteb\AppData\Local\Programs\Ollama\ollama.exe" serve
    timeout /t 4 /nobreak >nul
)

:: Confirm both are up
echo.
curl -s http://localhost:6333/ >nul 2>&1
if errorlevel 1 (echo Qdrant: FAILED to start) else (echo Qdrant: OK ^(localhost:6333^))
curl -s --max-time 4 http://localhost:11434/ >nul 2>&1
if errorlevel 1 (echo Ollama: FAILED to start) else (echo Ollama: OK ^(localhost:11434^))

echo.
pause
