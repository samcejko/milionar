import os
import json
from filelock import FileLock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNALS_FILE = os.path.join(ROOT_DIR, "alpha_signals.json")
LOCK_FILE = f"{SIGNALS_FILE}.lock"

def update_alpha_signals(source_key: str, inner_key: str, data: dict):
    """
    Safely update the shared alpha_signals.json file using a file lock
    to prevent race conditions between independent alpha workers.
    """
    lock = FileLock(LOCK_FILE, timeout=10)
    with lock:
        current_signals = {}
        if os.path.exists(SIGNALS_FILE):
            try:
                with open(SIGNALS_FILE, "r", encoding="utf-8") as f:
                    content = f.read()
                    if content.strip():
                        current_signals = json.loads(content)
            except Exception as e:
                print(f"Error reading {SIGNALS_FILE}: {e}")
                
        if source_key not in current_signals:
            current_signals[source_key] = {}
            
        current_signals[source_key][inner_key] = data
        
        tmp_path = f"{SIGNALS_FILE}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(current_signals, f, indent=4, ensure_ascii=False)
            os.replace(tmp_path, SIGNALS_FILE)
        except Exception as e:
            print(f"Error writing to {SIGNALS_FILE}: {e}")

def update_alpha_signal(source_key: str, data: dict):
    """
    Safely update the shared alpha_signals.json file using a file lock.
    (2-argument variant for backwards compatibility with older workers)
    """
    lock = FileLock(LOCK_FILE, timeout=10)
    with lock:
        current_signals = {}
        if os.path.exists(SIGNALS_FILE):
            try:
                with open(SIGNALS_FILE, "r", encoding="utf-8") as f:
                    content = f.read()
                    if content.strip():
                        current_signals = json.loads(content)
            except Exception as e:
                pass
                
        current_signals[source_key] = data
        
        tmp_path = f"{SIGNALS_FILE}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(current_signals, f, indent=4, ensure_ascii=False)
            os.replace(tmp_path, SIGNALS_FILE)
        except Exception as e:
            pass
