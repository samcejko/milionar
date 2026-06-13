"""
Alpha Worker Manager

Zodpovídá za asynchronní spouštění nezávislých workerů ve složce alpha_workers/.
Nahrazuje nutnost používat externí Linux Cron.
Běží v hlavní asyncio smyčce a reaguje korektně na její zrušení (Graceful Shutdown).
"""

import asyncio
import os
import sys
import logging
from typing import Dict, List

log = logging.getLogger("milionar.workers")

class AlphaWorkerManager:
    def __init__(self):
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.workers_dir = os.path.join(self.root_dir, "alpha_workers")
        self.tasks: List[asyncio.Task] = []
        
        # Mapa workerů a jejich frekvence v sekundách
        # Zohledníme reálnou potřebu. Např. VIX se může měnit každou chvíli (1 hodina),
        # Pelosi nebo Insider Trading stačí 1x za 12 hodin.
        # Pro jistotu nezahlcujeme API (většina je scraping z DDGS).
        self.worker_schedule: Dict[str, int] = {
            "worker_funding_rate.py": 3600,       # 1 hodina
            "worker_gamma_squeeze.py": 14400,     # 4 hodiny
            "worker_liquidation_heatmaps.py": 3600, # 1 hodina
            "worker_luxury_sentiment.py": 86400,  # 24 hodin
            "worker_miner_tracking.py": 14400,    # 4 hodiny
            "worker_pairs_trading.py": 3600,      # 1 hodina
            "worker_pdf_metadata.py": 43200,      # 12 hodin
            "worker_pelosi_tracker.py": 43200,    # 12 hodin
            "worker_regional_news.py": 14400,     # 4 hodiny
            "worker_search_trends.py": 43200,     # 12 hodin
            "worker_token_unlocks.py": 43200,     # 12 hodin
            "worker_vix_structure.py": 3600,      # 1 hodina
            "worker_wayback_git.py": 43200,       # 12 hodin
            "worker_insider_trading.py": 21600,   # 6 hodin (OpenInsider buys)
            "worker_earnings_calendar.py": 43200, # 12 hodin (Yahoo Earnings)
            "worker_macro_intel.py": 14400,       # 4 hodiny (FED, CPI)
            "worker_tech_intel.py": 21600,        # 6 hodin (RAM, Tech Leaks)
            "worker_jim_cramer.py": 14400,        # 4 hodiny (Inverse Cramer)
            "worker_crypto_whales.py": 60,        # 1 minuta (HFT RSS polling)
            "worker_hack_alerts.py": 30,          # 30 vteřin (HFT Hack/Exploit alerts)
            "worker_corporate_flights.py": 43200, # 12 hodin (M&A Private Jets)
            "worker_youtube_crypto.py": 14400,    # 4 hodiny (Pribyl YouTube Sentiment)
            "worker_value_titans.py": 86400,      # 24 hodin (Buffett 13F)
            "worker_macro_gurus.py": 43200,       # 12 hodin (Burry/Marks)
            "worker_inverse_cathie.py": 86400,    # 24 hodin (Cathie Wood)
            "worker_strategy_optimizer.py": 86400, # 24 hodin (ML Optimization)
            "worker_wsb_sentiment.py": 14400,     # 4 hodiny (Reddit WSB)
            "worker_app_store_fomo.py": 21600,    # 6 hodin (App Store Retail FOMO)
            "worker_github_activity.py": 43200,   # 12 hodin (GitHub Commits)
            "worker_wikipedia_fear.py": 43200,    # 12 hodin (Wikipedia Pageviews)
            "worker_geopolitics.py": 300,         # 5 minut (Geopolitics HFT)
            "worker_weather_commodities.py": 43200 # 12 hodin (Open-Meteo Brazil)
        }

    async def _run_worker(self, script_name: str, interval_seconds: int):
        """Nekonečná smyčka, která spouští jeden konkrétní worker a pak čeká zadaný interval."""
        script_path = os.path.join(self.workers_dir, script_name)
        
        if not os.path.exists(script_path):
            log.error(f"[WorkerManager] Skript nenalezen: {script_name}")
            return

        while True:
            log.info(f"[WorkerManager] Spouštím {script_name}...")
            try:
                # Vytvoření podprocesu pomocí aktuálního Python interpretru (venv)
                process = await asyncio.create_subprocess_exec(
                    sys.executable, script_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                # Čekáme na dokončení procesu
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    log.warning(f"[WorkerManager] {script_name} selhal s kódem {process.returncode}")
                    if stderr:
                        log.debug(f"[WorkerManager] {script_name} ERROR: {stderr.decode('utf-8', errors='ignore').strip()}")
                else:
                    log.debug(f"[WorkerManager] {script_name} doběhl úspěšně.")
                    
            except asyncio.CancelledError:
                # Odchycení CancelledError pro korektní ukončení z hlavního bota
                log.info(f"[WorkerManager] {script_name} byl zrušen (Graceful Shutdown).")
                # Zkusíme bezpečně zabít běžící proces, pokud existuje
                if 'process' in locals() and process.returncode is None:
                    try:
                        process.terminate()
                    except Exception:
                        pass
                raise  # Propagace zrušení nahoru
            except Exception as e:
                log.error(f"[WorkerManager] Neočekávaná chyba při spouštění {script_name}: {e}")

            # Čekání na další cyklus
            log.debug(f"[WorkerManager] {script_name} čeká {interval_seconds} sekund do dalšího běhu.")
            try:
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                log.info(f"[WorkerManager] Čekání pro {script_name} bylo zrušeno.")
                raise

    def start_all(self):
        """Vytvoří a spustí asynchronní tasky pro všechny workery ze schedule."""
        log.info("[WorkerManager] Startuji všechny alpha workery na pozadí...")
        
        for script, interval in self.worker_schedule.items():
            task = asyncio.create_task(self._run_worker(script, interval), name=f"task_{script}")
            self.tasks.append(task)
            
        return self.tasks

    async def shutdown(self):
        """Zruší všechny běžící worker tasky."""
        log.info("[WorkerManager] Ukončuji alpha workery (Shutdown)...")
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # Počkáme, až se všechny tasky skutečně ukončí
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        log.info("[WorkerManager] Všechny alpha workery byly bezpečně ukončeny.")
