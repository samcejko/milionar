# 🚀 Milionář Bot

> **Note:** This project was 100% *vibecoded*. 

Milionář Bot je plně autonomní, AI-řízený obchodní systém (hedge-fund in a box). Bot funguje v nekonečné smyčce, kde analyzuje trh, vyhledává skryté příležitosti (Alpha signály), konzultuje je s LLM modelem a samostatně provádí obchody na burze Alpaca. 

## 🌟 Hlavní funkce
- **O.T.A.R. Cyklus (Observe -> Think -> Act -> Reflect)**: Bot každých 15 minut projde trh, zamyslí se, nakoupí/prodá a o víkendu provádí sebereflexi svých chyb.
- **Multi-Agent Architektura**: Hlavní "Analytik" hledá obchody, ale "Risk Officer" ho může vetovat, pokud obchod nedává smysl z makroekonomického hlediska.
- **Alpha Workers**: Nezávislé procesy na pozadí pátrají po skrytých datech (Insider nákupy ředitelů, výsledkové sezóny, Reddit sentiment) a posílají varování hlavnímu botovi.
- **Multi-timeframe TA**: Automatický výpočet Weekly trendů (Macro), Daily trendů (SMA-20, RSI-14) a 15minutového vstupu (VWAP).
- **Trailing Stop-Loss**: Dynamické uzamykání zisků. Jakmile akcie roste, stop-loss se posouvá nahoru za ní.
- **Krásný Terminálový Dashboard**: Zobrazení portfolia, aktivních pozic a logů v reálném čase.
- **Telegram Notifikace**: Všechny nákupy a prodeje ti rovnou cinknou na mobil.

## 📁 Struktura Projektu

### `main.py`
Hlavní smyčka bota. Řídí celý proces, spouští Dashboard a volá jednotlivé moduly v přesném pořadí (Observe -> Think -> Act).

### `brain/` (Mozek a AI logika)
- `thinker.py` - Komunikuje s OpenRouter API (LLM) a extrahuje JSON rozhodnutí. Obsahuje i defenzivního "Risk Officera".
- `prompts.py` - Hlavní příkazy a pravidla chování pro AI. Definuje JSON schéma výstupu a váhu jednotlivých ukazatelů.
- `mcp_client.py` - Propojení s Alpaca MCP serverem.
- `technical.py` - Výpočty indikátorů (SMA, RSI, VWAP) přes `pandas-ta`.
- `reflection.py` - Víkendová automatická analýza chyb a generování nových ponaučení.
- `worker_manager.py` - Asynchronně řídí všechny Alpha Workery na pozadí.

### `trader/` (Obchodování a Riziko)
- `executor.py` - Komunikuje s burzou Alpaca. Odesílá trailing stop objednávky a má zabudovanou odolnost proti výpadkům sítě.
- `risk.py` - Upravuje velikost pozice (Position Sizing) podle celkového rizika.
- `state.py` - Udržuje High-Water Marks (dosavadní cenová maxima) pro Trailing stopy.

### `market/` (Zprávy a Data)
- `data.py` - Stahuje historická OHLCV data pro technickou analýzu.
- `news.py` - Hledá čerstvé zprávy kombinováním DuckDuckGo a Alpaca/Benzinga News.

### `alpha_workers/` (Datoví horníci)
Sbírka desítek nezávislých skriptů, které na pozadí pátrají po signálech (např. `worker_insider_trading.py`, `worker_earnings_calendar.py`). Jsou plně autonomní a posílají informace hlavnímu mozku.

### `memory/`
Složka pro ukládání historie obchodů (`trades.jsonl`), ponaučení z víkendu (`lessons.md`) a sledovaných aktiv (`watchlist.json`).

### `ui/`
- `dashboard.py` - Stará se o barevný `Rich` výpis do terminálu.

## 🛠️ Instalace a Spuštění

### 1. Požadavky
- **Python 3.10+**
- Založený účet na [Alpaca](https://alpaca.markets) (Paper Trading pro simulaci)
- Založený účet na [OpenRouter](https://openrouter.ai)
- (Volitelné) Telegram Bot Token pro notifikace na mobil

### 2. Konfigurace (`.env` soubor)
V kořenové složce projektu vytvoř soubor `.env` a doplň své klíče:
```env
ALPACA_API_KEY=tvuj_alpaca_klic
ALPACA_SECRET_KEY=tvuj_alpaca_secret
ALPACA_API_URL=https://paper-api.alpaca.markets
ALPACA_DATA_URL=https://data.alpaca.markets

OPENROUTER_API_KEY=tvuj_openrouter_klic

TELEGRAM_BOT_TOKEN=tvuj_telegram_token
TELEGRAM_CHAT_ID=tvoje_chat_id
```

### 3. Spuštění
Bot má automatické spouštěče, které si samy vytvoří virtuální prostředí a nainstalují potřebné knihovny.

**Pro Windows (PowerShell):**
```powershell
.\start.ps1
```

**Pro Linux / Mac:**
```bash
chmod +x start.sh
./start.sh
```

Bot okamžitě po zapnutí zahájí "Auto-discovery" proces, vybere si první náhodná aktiva k průzkumu, stáhne jejich technickou analýzu, pročte zprávy a začne bezpečně obchodovat!
