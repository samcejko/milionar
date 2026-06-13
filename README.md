# 🚀 Milionář Bot

> **Note:** This project was 100% *vibecoded*.

Milionář Bot je plně autonomní, AI-řízený obchodní systém (hedge-fund in a box). Funguje v nekonečné smyčce, kde analyzuje trh, vyhledává skryté příležitosti (Alpha signály), konzultuje je s LLM modelem a samostatně provádí obchody na burze Alpaca. Nyní vybaven **Machine Learning Optimalizátorem** a **Bleskovou Event-Driven Exekucí** s 0-vteřinovou latencí.

---

## 🌟 Hlavní funkce & Architektura

- **O.T.A.R. Cyklus (Observe -> Think -> Act -> Reflect)**: Bot každých 15 minut projde trh, zamyslí se, nakoupí/prodá a o víkendu provádí sebereflexi svých chyb.
- **Blesková Exekuce (Event-Driven Wake-up)**: Bot umí šetřit API kredity tím, že po provedení obchodů "spí". Pokud ale na internetu vyskočí urgentní HFT signál (např. Hack), bot se probudí v řádu milisekund a provede záchranný obchod dřív než retail.
- **YOLO Mód (Degen Mode)**: Speciální toleranční režim. Pokud si AI model není 100% jistý (má sebevědomí např. jen 50 %), ale cítí příležitost, vloží do obchodu stopové množství kapitálu (0.2 %) jako sázku na jistotu, namísto úplného zablokování obchodu.
- **Machine Learning Optimalizace (Grid Search)**: Každou noc si bot sám stahuje 180denní historii vybraných aktiv a testuje stovky kombinací indikátorů (SMA, RSI), aby pro každou konkrétní minci zjistil přesná čísla, která mají nejvyšší *Win Rate*.
- **Trailing Stop-Loss**: Dynamické uzamykání zisků. Jakmile akcie roste, stop-loss se posouvá nahoru za ní.
- **Telegram Notifikace**: Všechny YOLO nákupy a obchody ti rovnou cinknou na mobil.

---

## 🕵️‍♂️ Armáda Alpha Workerů

Mozek bota je krmen 14 nezávislými datovými špiony (Alpha Workery), kteří běží na pozadí a hledají ten nejlepší informační náskok na internetu:

### ⚡ Vysokofrekvenční (HFT) Workeři
Běží neustále a dokáží probudit bota z úsporného režimu během zlomku vteřiny.
- **`worker_hack_alerts.py` (30 vteřin)**: Skenuje RSS feedy na slova jako *hack, exploit, stolen*. Pokud je zasažen protokol, bot okamžitě posílá SHORT.
- **`worker_crypto_whales.py` (60 vteřin)**: Sleduje mintování miliard USDT nebo masivní přesuny Bitcoinů z burz na studené peněženky.
- **`worker_geopolitics.py` (5 minut)**: Prochází světové Reuters/BBC zpravodajství. Pokud najde klíčová válečná slova (rakety, invaze), ihned dumpuje akcie a shortuje.

### 🧠 Datoví a Makro Workeři (Veřejná data zdarma)
Nepotřebují žádné placené API klíče, těží ze sofistikovaných děr do veřejných systémů.
- **`worker_wsb_sentiment.py`**: Analyzuje JSON výstup z Redditu `r/wallstreetbets`. Zjišťuje počet raketek (🚀) a rodící se meme-stock mánie (GameStop 2.0).
- **`worker_app_store_fomo.py`**: Prohledává americký App Store RSS. Pokud se Coinbase prodere do Top 10 free aplikací, ohlašuje masivní FOMO zástupů hloupých retail investorů.
- **`worker_github_activity.py`**: Přes public GitHub API kontroluje Commity open-source projektů (Solana, Ethereum). Nárůst kódu signalizuje obří updaty a potenciální pumpu.
- **`worker_wikipedia_fear.py`**: Měří přes Wikimedia API, kolik milionů lidí na Wikipedii naráz hledá slova "Recese" a "Bankrot". Pokud křivka vyletí, lidé panikaří.
- **`worker_weather_commodities.py`**: Tahá data ze satelitů přes Open-Meteo. Při mrazech nebo vedrech nad 35°C v Brazílii ihned indikuje nákup kávy a cukru (pokles úrody).

### 🏛️ Institucionální Workeři
- **`worker_insider_trading.py`**: Sleduje nákupy CEOs a ředitelů vlastních firem (SEC Form 4).
- **`worker_pelosi_tracker.py`**: Kopíruje akcie, které do týdne před schválením vládních zákonů koupí američtí kongresmani (Nancy Pelosi).
- **`worker_value_titans.py`**: Sleduje americký report 13F pro pohyby Warrena Buffetta, Bena Felixe a Howarda Markse.
- **`worker_macro_gurus.py`**: Makroekonomický medvědí výhled podle dat od Michaela Burryho.
- **`worker_inverse_cathie.py`**: Založeno na Shortování ETF od Cathie Wood.
- **`worker_youtube_crypto.py`**: Agregace sentimentu z videí tuzemských guru (např. Jiří Přibyl) pomocí stahování YouTube titulků.

---

## 📁 Architektura Kódu

### `main.py`
Hlavní mozek. Spouští Dashboard, spouští asynchronně Alpha Workery na pozadí, a spravuje Event-Driven Wake-up cyklus (spí, dokud Alpha nezazvoní, nebo neuběhne 15 minut).

### `brain/` (Mozek a AI logika)
- `thinker.py` - Komunikuje s OpenRouter LLM. Uplatňuje **YOLO Risk Logic**.
- `prompts.py` - Nastavení chování umělé inteligence, váhy signálů.
- `backtest.py` - Modul schopný kvantitativního backtestu historie na povel LLM (ověření matematické pravděpodobnosti win rate).
- `technical.py` - Výpočty indikátorů (čte data od ML optimalizátoru z `optimal_params.json` namísto natvrdo nastavených čísel).
- `mcp_client.py` - Přímé propojení pro provádění složitých toolů skrz Alpaca MCP server.

### `trader/` (Obchodování a Riziko)
- `executor.py` - Posílá signály na burzu Alpaca, spravuje Trailing Stop Loss a obranu proti slippage.
- `risk.py` - Zhodnocuje "Confidence Score" od AI (např. Conf > 65% = plná pozice, 40-64% = YOLO pozice 0.2%).
- `state.py` - Databáze vrcholů cen (High-Water Marks) pro plovoucí uzamykání zisků.

### `alpha_workers/` (Datoví horníci)
Samostatné Python skripty běžící na pozadí popsané výše.

---

## 🛠️ Instalace a Spuštění

### 1. Požadavky
- **Python 3.10+** (Lze spustit klidně na Raspberry Pi 400).
- K účtu [Alpaca](https://alpaca.markets), [OpenRouter](https://openrouter.ai), a (volitelně) [Telegram](https://telegram.org/).

### 2. Konfigurace (`.env` soubor)
```env
ALPACA_API_KEY=tvuj_alpaca_klic
ALPACA_SECRET_KEY=tvuj_alpaca_secret
ALPACA_API_URL=https://paper-api.alpaca.markets
ALPACA_DATA_URL=https://data.alpaca.markets
OPENROUTER_API_KEY=tvuj_openrouter_klic
TELEGRAM_BOT_TOKEN=tvuj_telegram_token
TELEGRAM_CHAT_ID=tvoje_chat_id
ENABLE_YOLO_MODE=true
```

### 3. Spuštění
Bot vytvoří virtuální prostředí a jede sám. Pro ukončení včetně workerů stiskni `Ctrl+C`.

**Pro Linux / Mac (Raspberry Pi):**
```bash
chmod +x start.sh
./start.sh
```

**Pro Windows:**
```powershell
.\start.ps1
```
