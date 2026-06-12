import asyncio
import json
import logging
from datetime import datetime, timedelta
import aiohttp
import os

from config import Config
from memory.manager import MemoryManager

log = logging.getLogger("milionar.reflection")

class ReflectionEngine:
    def __init__(self, config: Config, memory: MemoryManager):
        self.config = config
        self.memory = memory

    async def run_weekend_reflection(self):
        log.info("[REFLECTION] Starting weekend reflection...")
        
        path = self.config.TRADES_FILE
        if not path.exists():
            log.info("No trades file found. Skipping reflection.")
            return

        recent_trades = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip(): continue
                    trade = json.loads(line.strip())
                    if not trade.get("executed"): continue
                    try:
                        trade_date = datetime.fromisoformat(trade["timestamp"])
                        if datetime.now() - trade_date < timedelta(days=7):
                            recent_trades.append({
                                "ticker": trade.get("ticker"),
                                "action": trade.get("action"),
                                "confidence": trade.get("confidence"),
                                "reasoning": trade.get("reasoning"),
                            })
                    except ValueError:
                        pass
        except Exception as e:
            log.error(f"Failed to read trades: {e}")
            return
            
        if not recent_trades:
            log.info("No trades in the last 7 days. Skipping reflection.")
            return
            
        trades_summary = json.dumps(recent_trades, indent=2, ensure_ascii=False)
        
        prompt = f"""You are an elite trading AI doing a weekend review.
Review the following trades executed in the last 7 days:

{trades_summary}

Identify patterns of mistakes or successes.
Output exactly 3 new, concise lessons learned.
Do not output anything else except the markdown for the 3 lessons.
Format them exactly like this:
## Lesson - {datetime.now().strftime("%Y-%m-%d")} (Weekly Review)
**Situation:** ...
**Result:** ...
**Lesson:** ...
"""
        
        payload = {
            "model": self.config.ACTIVE_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4
        }
        
        url = f"{self.config.LITELLM_URL}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.config.LITELLM_API_KEY}"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=60) as resp:
                    resp.raise_for_status()
                    result = await resp.json()
                    
            content = result["choices"][0]["message"]["content"]
            
            with open(self.config.LESSONS_FILE, "a", encoding="utf-8") as f:
                f.write("\n\n" + content + "\n\n")
                
            log.info("[REFLECTION] Weekend reflection completed and lessons saved.")
            
        except Exception as e:
            log.error(f"[REFLECTION] Failed to run LLM reflection: {e}")
