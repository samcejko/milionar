#!/bin/bash

# Exit on error
set -e

echo "========================================="
echo " Milionar Trading Bot - Auto Setup & Run"
echo "========================================="

# Change to script directory
cd "$(dirname "$0")"

# 1. Check/Create venv
if [ ! -d "venv" ]; then
    echo "[*] Vytvářím virtuální prostředí (venv)..."
    python3 -m venv venv
else
    echo "[*] Virtuální prostředí nalezeno."
fi

# 2. Activate venv
echo "[*] Aktivuji venv..."
source venv/bin/activate

# 3. Install/Update dependencies
echo "[*] Instaluji/aktualizuji závislosti z requirements.txt..."
pip install --upgrade pip > /dev/null 2>&1
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt > /dev/null 2>&1
else
    echo "[!] requirements.txt nenalezeno, přeskočeno."
fi
echo "[*] Závislosti jsou aktuální."

# 4. Start main bot
echo "[*] Spouštím hlavního bota (python main.py)..."
echo "Pro ukončení bota i všech workerů na pozadí stiskni Ctrl+C."
echo "-----------------------------------------"

python main.py
