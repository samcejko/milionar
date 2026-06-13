import logging
import sys
import os
import asyncio
import json
import requests
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from alpha_workers.utils import update_alpha_signal
from config import Config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("worker_youtube_crypto")

def analyze_transcript_with_llm(title: str, transcript: str, api_key: str) -> str:
    """Uses OpenRouter LLM to analyze the actual sentiment of the transcript."""
    # Truncate transcript to save context window (first 4000 chars is usually enough to get the gist)
    truncated = transcript[:4000]
    
    prompt = f"""
Jsi expert na analýzu kryptoměn. Přečti si následující název videa a prvních pár minut jeho přepisu (transcript).
Analyzuj, jaký je skutečný postoj analytika (BULLISH, BEARISH, nebo NEUTRAL). Nenech se zmást clickbaitovým názvem, sleduj jeho skutečné argumenty.

Název videa: {title}
Přepis:
{truncated}

Odpověz POUZE ve formátu JSON:
{{"signal": "BULLISH/BEARISH/NEUTRAL", "reason": "Tvé stručné vysvětlení proč (1-2 věty)."}}
"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=30)
        res_json = res.json()
        content = res_json['choices'][0]['message']['content']
        # Try to parse JSON from the response
        import re
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            return parsed.get("signal", "NEUTRAL"), parsed.get("reason", "N/A")
        return "NEUTRAL", "Nepodařilo se parsovat odpověď z LLM."
    except Exception as e:
        log.error(f"LLM request failed: {e}")
        return "NEUTRAL", "Chyba při komunikaci s LLM."

def check_youtube_sentiment():
    """
    Searches for latest videos from Jiří Přibyl, downloads transcript, and evaluates sentiment via LLM.
    """
    try:
        from duckduckgo_search import DDGS
        from youtube_transcript_api import YouTubeTranscriptApi
        import urllib.parse as urlparse
        
        cfg = Config()
        
        log.info("Fetching YouTube videos for Jiří Přibyl...")
        query = '"Jiří Přibyl" (Bitcoin OR krypto OR trhy) site:youtube.com'
        
        latest_video = None
        
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            for res in results:
                url = res.get("href", "")
                if "youtube.com/watch" in url:
                    latest_video = res
                    break
                    
        if not latest_video:
            return "NEUTRAL", "Nebyla nalezena žádná nová videa."
            
        url = latest_video["href"]
        title = latest_video["title"]
        
        # Extract video ID
        parsed = urlparse.urlparse(url)
        qs = urlparse.parse_qs(parsed.query)
        video_id = qs.get("v", [""])[0]
        
        if not video_id:
            return "NEUTRAL", "Nepodařilo se získat video ID."
            
        # Download transcript
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(['cs'])
        except:
            transcript = next(iter(transcript_list))
            
        data = transcript.fetch()
        full_text = " ".join([t['text'] for t in data])
        
        # Ask LLM
        signal, reason = analyze_transcript_with_llm(title, full_text, cfg.OPENROUTER_API_KEY)
        
        return signal, f"Jiří Přibyl (YouTube): {reason} [Zdroj: {title}]"
        
    except Exception as e:
        log.error(f"YouTube worker failed: {e}")
        return "ERROR", str(e)

async def main():
    signal, details = await asyncio.to_thread(check_youtube_sentiment)
    
    result = {
        "source": "youtube_crypto_pribyl",
        "signal": signal,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    
    update_alpha_signal("pribyl_crypto", result)
    log.info(f"YouTube Crypto signal updated: {signal}")

if __name__ == "__main__":
    asyncio.run(main())
