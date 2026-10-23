# siboru_scanner.py - Karyawan 1: Pencari Data (Siboru)
import time
from urllib.request import Request, urlopen
import json
from config import MAX_DISCOVERY_TOKENS

BASE = "https://api.dexscreener.com"

def get_json(url, timeout=20, retries=3):
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "DJIWA-Siboru/1.0"})
            with urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            if attempt == retries - 1: raise
            time.sleep(2 ** attempt)

def api_list(path):
    data = get_json(BASE + path)
    return data if isinstance(data, list) else []

def discover_tokens():
    candidates, errors = [], []
    for endpoint in ("/token-profiles/latest/v1", "/token-boosts/latest/v1"):
        try: candidates.extend(api_list(endpoint))
        except Exception as exc: errors.append(f"{endpoint}: {exc}")
    
    seen, unique = set(), []
    for item in candidates:
        chain, address = str(item.get("chainId") or "").strip(), str(item.get("tokenAddress") or "").strip()
        key = (chain.lower(), address.lower())
        if chain and address and key not in seen:
            seen.add(key)
            unique.append({"chainId": chain, "tokenAddress": address})
    return unique[:MAX_DISCOVERY_TOKENS], errors

def fetch_token_pairs(chain, address):
    data = get_json(f"{BASE}/token-pairs/v1/{chain}/{address}")
    return data if isinstance(data, list) else []

def fetch_pair_by_address(chain, pair_address):
    data = get_json(f"{BASE}/latest/dex/pairs/{chain}/{pair_address}")
    pairs = data.get("pairs") or [] if isinstance(data, dict) else []
    return pairs[0] if pairs else None

def scan_market():
    tokens, discovery_errors = discover_tokens()
    all_pairs, pair_errors = [], []
    
    for token in tokens:
        try:
            for pair in fetch_token_pairs(token["chainId"], token["tokenAddress"]):
                all_pairs.append(pair) 
        except Exception as exc:
            pair_errors.append(f'{token["chainId"]}/{token["tokenAddress"]}: {exc}')
        time.sleep(0.15)
        
    return all_pairs, discovery_errors, pair_errors, len(tokens)
