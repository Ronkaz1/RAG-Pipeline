@echo off
cd /d D:\Code\AI
echo Starting Query Worker v2 (RAG + document loading)...
echo.

:loop
"C:\Users\peteb\AppData\Local\Programs\Python\Python312\python.exe" query_worker_v2.py
echo.
echo Worker exited. Checking Ollama...

tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find "ollama.exe" >nul
if not errorlevel 1 (
    curl -s --max-time 4 http://localhost:11434/ >nul 2>&1
    if errorlevel 1 (
        echo Ollama hung. Restarting...
        taskkill /F /IM ollama.exe >nul 2>&1
        timeout /t 2 /nobreak >nul
        start "" /B "C:\Users\peteb\AppData\Local\Programs\Ollama\ollama.exe" serve
        timeout /t 5 /nobreak >nul
    )
)

echo Restarting worker in 3s...
timeout /t 3 /nobreak >nul
goto loop
