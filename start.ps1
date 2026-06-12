Write-Host "========================================="
Write-Host " Milionar Trading Bot - Auto Setup & Run"
Write-Host "========================================="

# Set execution policy for current process to allow running scripts
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force

# Change to script directory
Set-Location -Path $PSScriptRoot

# 1. Check/Create venv
if (-not (Test-Path "venv")) {
    Write-Host "[*] Vytvářím virtuální prostředí (venv)..."
    python -m venv venv
} else {
    Write-Host "[*] Virtuální prostředí nalezeno."
}

# 2. Activate venv
Write-Host "[*] Aktivuji venv..."
& ".\venv\Scripts\Activate.ps1"

# 3. Install/Update dependencies
Write-Host "[*] Instaluji/aktualizuji závislosti z requirements.txt..."
python -m pip install --upgrade pip | Out-Null
if (Test-Path "requirements.txt") {
    pip install -r requirements.txt | Out-Null
} else {
    Write-Host "[!] requirements.txt nenalezeno, přeskočeno."
}
Write-Host "[*] Závislosti jsou aktuální."

# 4. Start main bot
Write-Host "[*] Spouštím hlavního bota (python main.py)..."
Write-Host "Pro ukončení bota i všech workerů na pozadí stiskni Ctrl+C."
Write-Host "-----------------------------------------"

python main.py
