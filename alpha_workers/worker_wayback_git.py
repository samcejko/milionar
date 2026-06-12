from utils import update_alpha_signals
import asyncio
import json
import os
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

from ddgs import DDGS

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(ROOT_DIR, "memory", "state.json")
WATCHLIST_FILE = os.path.join(ROOT_DIR, "memory", "watchlist.json")
SIGNALS_FILE = os.path.join(ROOT_DIR, "alpha_signals.json")

def get_tracked_tickers():
    """Loads tracked and held tickers from memory."""
    tickers = set()
    
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                hwm = state.get("high_water_marks", {})
                for ticker in hwm.keys():
                    tickers.add(ticker)
        except Exception as e:
            print(f"Error reading state.json: {e}")

    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                wl = json.load(f)
                for item in wl.get("symbols", []):
                    if isinstance(item, dict) and "ticker" in item:
                        tickers.add(item["ticker"])
        except Exception as e:
            print(f"Error reading watchlist.json: {e}")
            
    return list(tickers)

def get_company_name(ticker):
    """Gets full company name using Yahoo Finance API."""
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={ticker}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            quotes = data.get("quotes", [])
            if quotes:
                name = quotes[0].get("shortname") or quotes[0].get("longname")
                if name:
                    return name
    except Exception as e:
        print(f"Error getting company name for {ticker}: {e}")
    return ticker

def get_company_website(company_name):
    """Finds official website using DuckDuckGo."""
    try:
        with DDGS() as ddgs:
            results = ddgs.text(f"{company_name} official website investor relations", max_results=3)
            for res in results:
                url = res.get('href', '')
                if "yahoo.com" not in url and "bloomberg.com" not in url and "wikipedia.org" not in url:
                    return url
    except Exception as e:
        print(f"Error searching website for {company_name}: {e}")
    return None

def get_github_repo(company_name):
    """Finds the most known GitHub repository of the company."""
    org_name = company_name.split()[0].split(',')[0].split('.')[0].lower()
    url = f"https://api.github.com/search/repositories?q=org:{org_name}&sort=stars"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            items = data.get("items", [])
            if items:
                return items[0].get("full_name")
    except urllib.error.HTTPError as e:
        if e.code not in (404, 422):
            print(f"GitHub API HTTP error for {org_name}: {e}")
    except Exception as e:
        print(f"Error searching GitHub repository for {company_name}: {e}")
    return None

def check_wayback(url):
    """Checks Wayback Machine for 404 or content length drop of 30%."""
    domain = urllib.parse.urlparse(url).netloc or url
    domain = domain.replace("www.", "")
    
    api_url = f"http://web.archive.org/cdx/search/cdx?url={domain}&output=json&limit=-2&fl=timestamp,statuscode,length"
    req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data and len(data) >= 3:
                prev = data[1]
                latest = data[2]
                
                status = latest[1]
                if status == "404":
                    return -1.0, "Latest Wayback snapshot returned 404."
                
                try:
                    prev_len = int(prev[2])
                    latest_len = int(latest[2])
                    if prev_len > 0:
                        drop = (prev_len - latest_len) / prev_len
                        if drop > 0.3:
                            return -1.0, f"Content length dropped by {drop*100:.1f}%."
                except ValueError:
                    pass
            return 0.0, "No significant negative changes found."
    except Exception as e:
        print(f"Error checking Wayback Machine for {url}: {e}")
    return 0.0, "API error."

def check_github(repo_full_name):
    """Checks if repository was active in the last 30 days."""
    url = f"https://api.github.com/repos/{repo_full_name}/commits"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data and isinstance(data, list):
                last_commit_date_str = data[0].get("commit", {}).get("author", {}).get("date")
                if last_commit_date_str:
                    dt = datetime.fromisoformat(last_commit_date_str.replace("Z", "+00:00"))
                    days_ago = (datetime.now(timezone.utc) - dt).days
                    if days_ago > 30:
                        return -1.0, f"Last commit was {days_ago} days ago."
                    return 0.0, f"Active repository, last commit {days_ago} days ago."
    except Exception as e:
        print(f"Error checking GitHub commits for {repo_full_name}: {e}")
    return 0.0, "API error."

async def analyze_ticker(ticker):
    print(f"[{datetime.now().isoformat()}] Starting autodiscovery for {ticker}...")
    
    name = await asyncio.to_thread(get_company_name, ticker)
    print(f"[{datetime.now().isoformat()}] Company name for {ticker}: {name}")
    
    website = await asyncio.to_thread(get_company_website, name)
    repo = await asyncio.to_thread(get_github_repo, name)
    
    print(f"[{datetime.now().isoformat()}] {ticker} Domain: {website}")
    print(f"[{datetime.now().isoformat()}] {ticker} GitHub: {repo}")
    
    wb_score = 0.0
    wb_reason = "No suitable website found."
    if website:
        wb_score, wb_reason = await asyncio.to_thread(check_wayback, website)
        
    git_score = 0.0
    git_reason = "No suitable GitHub repository found."
    if repo:
        git_score, git_reason = await asyncio.to_thread(check_github, repo)
        
    total_score = 0.0
    signal = "NEUTRAL"
    if wb_score < 0 or git_score < 0:
        signal = "BEARISH"
        total_score = -1.0
        
    return {
        "source": "wayback_git_worker",
        "ticker": ticker,
        "signal": signal,
        "score": total_score,
        "confidence": abs(total_score) if total_score != 0 else 0.5,
        "timestamp": datetime.now().isoformat(),
        "details": f"Wayback: {wb_reason} | GitHub: {git_reason}"
    }

async def main():
    print(f"[{datetime.now().isoformat()}] Running worker_wayback_git.py (Autodiscovery)")
    tickers = get_tracked_tickers()
    if not tickers:
        print("No tracked tickers found in state.json and watchlist.json. Using fallback [NVDA, TSLA].")
        tickers = ["NVDA", "TSLA"]
        
    print(f"Tracked tickers: {tickers}")
    tasks = [analyze_ticker(ticker) for ticker in tickers]
    results = await asyncio.gather(*tasks)
    
    current_signals = {}
    if os.path.exists(SIGNALS_FILE):
        try:
            with open(SIGNALS_FILE, "r", encoding="utf-8") as f:
                content = f.read()
                if content.strip():
                    current_signals = json.loads(content)
        except Exception as e:
            print(f"Error reading {SIGNALS_FILE}: {e}")
            
    for res in results:
        update_alpha_signals("wayback_scraper", res["ticker"], res)
        
    f"Error writing to {SIGNALS_FILE}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
