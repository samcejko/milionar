# Milionář Bot - Autonomní Algoritmický Obchodní Systém

Milionář Bot je plně autonomní, umělou inteligencí řízený kvantitativní obchodní systém navržený pro nepřetržitou analýzu trhu a exekuci obchodů. Systém operuje v kontinuální smyčce řízené událostmi (event-driven), kde syntetizuje makroekonomická data, technické indikátory a alternativní datové zdroje (tzv. Alpha signály) k provádění samostatných obchodních operací přes API burzy Alpaca. Systém integruje dynamické řízení rizik, optimalizaci parametrů pomocí strojového učení a vysokofrekvenční zpracování událostí (HFT).

---

## Jádro a Architektura

- **O.T.A.R. Cyklus (Observe -> Think -> Act -> Reflect)**: Systém každých 15 minut analyzuje stav trhu, formuluje hypotézy prostřednictvím LLM modelu, provádí obchody a během víkendu provádí automatickou sebereflexi svých předchozích rozhodnutí za účelem optimalizace.
- **Event-Driven Exekuce (HFT)**: Pro minimalizaci poplatků za API zůstává bot mezi standardními cykly v úsporném režimu. Je však vybaven mechanismem okamžitého probuzení (interrupt): pokud asynchronní proces na pozadí detekuje urgentní tržní událost, exekuční cyklus je spuštěn během několika milisekund pro okamžitou reakci.
- **Spekulativní Režim (Risk-Adjusted Execution)**: Specializovaný protokol pro řízení tolerance k riziku. Pokud je míra spolehlivosti generovaného obchodního signálu suboptimální (např. 40-64 %), systém signál nezahodí. Místo toho provede obchod s přísně omezeným rizikem (maximálně 0.2 % celkového kapitálu), aby zachytil potenciální růst při minimalizaci ztrát.
- **Optimalizace Parametrů (Machine Learning Grid Search)**: Plně automatizovaný noční proces, který provádí backtest posledních 180 dní historických dat. Iteruje skrze stovky kombinací technických indikátorů (SMA, RSI) k nalezení optimálních parametrů, které historicky maximalizují poměr ziskových obchodů (Win Rate).
- **Dynamické Řízení Rizik (Trailing Stop-Loss)**: Automatická správa otevřených pozic využívající metodu High-Water Mark pro dynamické posouvání stop-loss hranice, což zajišťuje ochranu kapitálu a uzamykání zisků při rostoucím trendu.
- **Telemetrie v Reálném Čase**: Integrovaný modul Telegramu pro okamžité notifikace o provedených obchodech a stavu systému.

---

## Technologický Stack

- **Integrace LLM**: API OpenRouter poskytuje přístup k bezplatným open-source modelům (např. nex-agi/nex-n2-pro, openrouter/owl-alpha) pro pokročilou analýzu sentimentu a vyhodnocení rizika.
- **Model Context Protocol (MCP)**: Systém využívá oficiální Python SDK `mcp` (`mcp_client.py`) pro navázání spojení se subprocess serverem `alpaca-mcp-server`. To umožňuje umělé inteligenci bezpečně a nativně manipulovat s portfoliem prostřednictvím specifikace Anthropic MCP.
- **Asynchronní I/O Architektura**: Celý systém, včetně desítek monitorů na pozadí, je napsán plně asynchronně pomocí `asyncio` a `aiohttp`. Vlákna nejsou blokována čekáním na síťovou odezvu, což umožňuje běh masivního množství procesů současně s minimálním zatížením CPU (bez problému běží i na Raspberry Pi 400).
- **Vektorová Analýza Trhu**: Implementace knihoven `pandas` a `pandas-ta` pro vysoce výkonné a exaktní výpočty desítek technických indikátorů.
- **Zpracování Přirozeného Jazyka (NLP)**: Využití knihovny `youtube-transcript-api` k dolování textu z videí tuzemských analytiků a asynchronní parsování zpráv přes `duckduckgo_search`.

---

## Sběr Dat a Generování Signálů

Systém agreguje alternativní data prostřednictvím nezávislých, asynchronních Python procesů (Monitorů), které běží na pozadí. Tyto procesy se dělí podle latence a zdroje dat:

### Vysokofrekvenční (HFT) Monitory
Operují nepřetržitě s minimálními intervaly a v případě nutnosti spouští okamžitý Event-Driven exekuční cyklus.
- **`worker_hack_alerts.py` (30s interval)**: Monitoruje hlavní kryptoměnové RSS kanály pro detekci kybernetických útoků a zranitelností chytrých kontraktů. Generuje okamžité signály k prodeji (SHORT).
- **`worker_crypto_whales.py` (60s interval)**: Sleduje významné transakce na blockchainu, včetně nasazení institucionálního kapitálu (např. masivní tisk USDT) nebo přesunů aktiv na burzy.
- **`worker_geopolitics.py` (5m interval)**: Analyzuje globální tiskové agentury (Reuters, BBC) a hledá klíčová slova naznačující geopolitickou eskalaci za účelem defenzivní rotace portfolia.

### Monitory Alternativních Dat
Využívají veřejná datová rozhraní k měření tržního sentimentu a chování drobných (retail) investorů.
- **`worker_wsb_sentiment.py`**: Analyzuje JSON data ze specifických finančních fór (např. r/wallstreetbets) k měření retailového momenta a objemových anomálií.
- **`worker_app_store_fomo.py`**: Monitoruje americký App Store žebříček přes RSS. Náhlý vzestup retailových obchodních aplikací slouží jako kontrariánský indikátor tržního vrcholu.
- **`worker_github_activity.py`**: Dotazuje veřejná GitHub API na frekvenci vývojářských změn (commits) u hlavních open-source blockchain repozitářů k predikci nadcházejících síťových aktualizací.
- **`worker_wikipedia_fear.py`**: Využívá Wikimedia Pageviews API ke sledování objemu vyhledávání klíčových slov spojených s makroekonomickým stresem (např. "Recese", "Bankrot") jakožto předstihový indikátor tržní paniky.
- **`worker_weather_commodities.py`**: Agreguje satelitní data o počasí (Open-Meteo) k detekci extrémních klimatických podmínek v klíčových zemědělských oblastech, což umožňuje prediktivní obchody s komoditními ETF.

### Institucionální a Makroekonomické Sledování
- **`worker_insider_trading.py`**: Sleduje transakce členů představenstev a generálních ředitelů (SEC Form 4).
- **`worker_pelosi_tracker.py`**: Monitoruje zveřejnění obchodních transakcí členů amerického Kongresu.
- **`worker_value_titans.py`**: Analyzuje zprávy 13F významných institucionálních investorů (např. Warren Buffett, Howard Marks).
- **`worker_macro_gurus.py`**: Sleduje varování a makroekonomické predikce od analytiků (např. Michael Burry).
- **`worker_inverse_cathie.py`**: Generuje obchodní signály na základě shortování specifických inovačních ETF.
- **`worker_youtube_crypto.py`**: Zpracovává videotranskripce od vybraných lokálních finančních analytiků s využitím automatické extrakce sentimentu.

### Další Agregátory Dat
- **`worker_earnings_calendar.py`**: Upozorňuje na blížící se ohlašování hospodářských výsledků přes Yahoo Finance.
- **`worker_macro_intel.py`**: Monitoruje klíčová oznámení (úrokové sazby FEDu, zprávy o inflaci CPI).
- **`worker_tech_intel.py`**: Vyhledává úniky informací (leaks) v dodavatelských řetězcích polovodičů a zprávy o trhu s RAM.
- **`worker_corporate_flights.py`**: Analyzuje zprávy o letech soukromých tryskáčů generálních ředitelů jako indikátor blížících se fúzí a akvizic (M&A).
- **`worker_jim_cramer.py`**: Identifikuje televizní doporučení Jima Cramera za účelem vybudování inverzní pozice.
- **`worker_token_unlocks.py`**: Sleduje kalendář odemykání kryptoměnových tokenů, které zpravidla vedou k převisu nabídky a poklesu cen.
- **`worker_liquidation_heatmaps.py`**: Agreguje zóny likvidací retailových obchodníků obchodujících na páku.
- **`worker_luxury_sentiment.py`**: Měří prodeje luxusního zboží jako indikátor likvidity vyšší třídy.
- **`worker_miner_tracking.py`**: Analyzuje peněženky těžařů Bitcoinu k identifikaci potenciálních kapitulací.
- **`worker_vix_structure.py`**: Monitoruje strukturu indexu volatility VIX pro predikci hlubokých korekcí na trzích.

---

## Struktura Adresářů

### `main.py`
Hlavní orchestrátor systému. Inicializuje terminálový dashboard, spouští asynchronní procesy na pozadí a řídí exekuční cyklus (Event-Driven).

### `brain/` (Logika a Integrace AI)
- `thinker.py` - Komunikuje s API jazykového modelu (OpenRouter). Vyhodnocuje obchodní signály a vynucuje pravidla risk managementu.
- `prompts.py` - Systémové instrukce a definice výstupních JSON formátů pro LLM.
- `backtest.py` - Modul pro kvantitativní zpětné testování vyvolaný jazykovým modelem pro ověření matematické pravděpodobnosti úspěchu.
- `technical.py` - Výpočty technické analýzy na více časových rámcích s využitím optimalizovaných parametrů z ML modulu.
- `mcp_client.py` - Rozhraní pro komunikaci se serverem Alpaca Model Context Protocol (MCP).

### `trader/` (Exekuce a Řízení Rizik)
- `executor.py` - Stará se o odesílání pokynů na burzu Alpaca, spravuje zpoždění (slippage) a aktualizuje posuvné stop-loss příkazy.
- `risk.py` - Dynamicky upravuje velikost pozice (Position Sizing) na základě expozice portfolia a míry jistoty jazykového modelu.
- `state.py` - Trvalé úložiště pro sledování maximálních cen aktiv (High-Water Marks).

### `alpha_workers/` (Sběr Dat)
Adresář obsahující všechny asynchronní Python skripty odpovědné za generování obchodních signálů.

---

## Instalace a Nasazení

### 1. Požadavky
- **Python 3.10+** (Plně kompatibilní s OS Linux a hardwarem Raspberry Pi).
- Aktivní účty u platforem [Alpaca](https://alpaca.markets) (pro testování doporučeno Paper Trading), [OpenRouter](https://openrouter.ai) a [Telegram](https://telegram.org/).

### 2. Konfigurace Prostředí (`.env`)
Vytvořte soubor `.env` v kořenovém adresáři:
```env
ALPACA_API_KEY=vas_alpaca_klic
ALPACA_SECRET_KEY=vas_alpaca_secret
ALPACA_API_URL=https://paper-api.alpaca.markets
ALPACA_DATA_URL=https://data.alpaca.markets
OPENROUTER_API_KEY=vas_openrouter_klic
TELEGRAM_BOT_TOKEN=vas_telegram_token
TELEGRAM_CHAT_ID=vase_chat_id
ENABLE_YOLO_MODE=true
```

### 3. Spuštění
Systém obsahuje automatizované inicializační skripty, které vytvoří virtuální prostředí a nainstalují potřebné knihovny. Pro bezpečné ukončení procesu (včetně všech běžících monitorů) použijte klávesovou zkratku `Ctrl+C`.

**Linux / macOS (Raspberry Pi):**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
```powershell
.\start.ps1
```
