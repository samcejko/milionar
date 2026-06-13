import logging
import sys
import os
import asyncio
import requests
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_weather_commodities")

def check_weather():
    # Sao Paulo, Brazil (Káva, cukr)
    url = "https://api.open-meteo.com/v1/forecast?latitude=-23.55&longitude=-46.63&current_weather=true"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return "NEUTRAL", "Failed to fetch weather data."
            
        data = res.json()
        current = data.get("current_weather", {})
        temp = current.get("temperature", 20)
        
        if temp > 35.0:
            return "BULLISH", f"WEATHER ALERT: Extrémní vedra ({temp}°C) v Brazílii (Sao Paulo). Úroda kávy a cukru je ohrožena, cena poletí nahoru. Nákup zemědělských komodit."
        elif temp < 0.0:
            return "BULLISH", f"WEATHER ALERT: Nečekané mrazy ({temp}°C) v Brazílii. Úroda je zničena. Nákup komodit."
            
        return "NEUTRAL", f"Počasí v zemědělských oblastech je stabilní ({temp}°C)."
    except Exception as e:
        return "ERROR", str(e)

async def main():
    signal, details = await asyncio.to_thread(check_weather)
    result = {
        "source": "weather_commodities",
        "signal": signal,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    update_alpha_signal("weather_commodities", result)
    log.info(f"Weather signal updated: {signal}")

if __name__ == "__main__":
    asyncio.run(main())
