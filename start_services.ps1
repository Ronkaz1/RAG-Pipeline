# Start Qdrant and Ollama before running any of the Python scripts

$qdrantExe = "$PSScriptRoot\qdrant\qdrant.exe"
$ollamaExe = "C:\Users\peteb\AppData\Local\Programs\Ollama\ollama.exe"

# Start Qdrant
$qdrantRunning = $false
try { Invoke-RestMethod "http://localhost:6333/" -TimeoutSec 2 | Out-Null; $qdrantRunning = $true } catch {}
if (-not $qdrantRunning) {
    Write-Host "Starting Qdrant..."
    Start-Process -FilePath $qdrantExe -WorkingDirectory (Split-Path $qdrantExe) -WindowStyle Hidden
    Start-Sleep -Seconds 3
} else {
    Write-Host "Qdrant already running."
}

# Start Ollama
$ollamaRunning = $false
try { Invoke-RestMethod "http://localhost:11434/" -TimeoutSec 2 | Out-Null; $ollamaRunning = $true } catch {}
if (-not $ollamaRunning) {
    Write-Host "Starting Ollama..."
    Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
} else {
    Write-Host "Ollama already running."
}

# Confirm both are up
try { $q = Invoke-RestMethod "http://localhost:6333/"; Write-Host "Qdrant $($q.version) ready on :6333" } catch { Write-Host "ERROR: Qdrant not responding" }
try { Invoke-RestMethod "http://localhost:11434/" | Out-Null; Write-Host "Ollama ready on :11434" } catch { Write-Host "ERROR: Ollama not responding" }
