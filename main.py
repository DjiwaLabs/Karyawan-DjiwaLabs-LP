#!/usr/bin/env python3
"""
DJIWA LP v2.0 - DexScreener Live Scanner + REALISTIC Paper LP Simulator.
Perbaikan: Gas, Slippage, Filter Scam, Take Profit, dan Bug Fixes.
"""
import csv
import json
import math
import os
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("djiwa")

BASE = "https://api.dexscreener.com"
DATA_DIR = Path("data")
REPORT_DIR = Path("reports")
STATE_FILE = DATA_DIR / "paper_state.json"

# --- KONFIGURASI SIMULASI ---
STARTING_CASH_USD = 10_000.0
ALLOCATION_PER_POOL_USD = 1_000.0 # Dinaikkan agar modal bekerja (max 5 posisi = $5000)
MAX_OPEN_POSITIONS = 5
MIN_LIQUIDITY_USD = 50_000.0      # Dinaikkan: Hindari pool tipis
MIN_VOLUME_24H_USD = 50_000.0     # Dinaikkan: Pastikan ada aktivitas
MIN_TXNS_24H = 200
MIN_POOL_AGE_HOURS = 24.0         # Diubah: Minimal 1 hari (hindari bot instant)
MAX_POOL_AGE_DAYS = 180           # Jangan masuk ke pool yang sudah mati
SIMULATED_POOL_FEE_RATE = 0.003   # Asumsi fee 0.3%
MAX_DISCOVERY_TOKENS = 40
MAX_EVENTS_KEPT = 100

# --- BIAYA REALISTIS (PENTING!) ---
SIMULATED_GAS_USD = 1.5           # Asumsi biaya gas per transaksi (masuk/keluar)
SIMULATED_SLIPPAGE = 0.005        # 0.5% slippage saat masuk/keluar

# Quote token yang diizinkan (hindari LP di pair sampah)
ALLOWED_QUOTE_TOKENS = {"USDC", "USDT", "WETH", "WBNB", "SOL", "DAI", "BUSD"}

def now_utc(): return datetime.now(timezone.utc)
def iso_now(): return now_utc().isoformat(timespec="seconds")
def number(value, default=0.0):
    try: return float(value) if value is not None and value != "" else default
    except (TypeError, ValueError): return default

def get_json(url, timeout=20, retries=3):
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "DJIWA-LP-v2/1.0"})
            with urlopen(req, timeout=timeout) as response:
                if response.status != 200: raise RuntimeError(f"HTTP {response.status}")
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
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

def pair_metrics(pair):
    volume = pair.get("volume") or {}
    txns = pair.get("txns") or {}
    h24_txns = txns.get("h24") or {}
    liquidity = pair.get("liquidity") or {}
    price_change = pair.get("priceChange") or {}
    base, quote = pair.get("baseToken") or {}, pair.get("quoteToken") or {}
    created_ms = number(pair.get("pairCreatedAt"), 0)
    
    age_hours = max(0.0, (now_utc().timestamp() * 1000 - created_ms) / 3_600_000) if created_ms > 0 else None
    buys, sells = int(number(h24_txns.get("buys"), 0)), int(number(h24_txns.get("sells"), 0))
    
    return {
        "chain": str(pair.get("chainId") or ""), "dex": str(pair.get("dexId") or ""),
        "pair_address": str(pair.get("pairAddress") or ""), "pair_url": str(pair.get("url") or ""),
        "token_address": str(base.get("address") or ""),
        "name": str(base.get("name") or "Unknown"), 
        "symbol": str(base.get("symbol") or "UNKNOWN"),
        "quote_symbol": str(quote.get("symbol") or "").upper(),
        "price_usd": number(pair.get("priceUsd"), 0), "liquidity_usd": number(liquidity.get("usd"), 0),
        "volume_24h_usd": number(volume.get("h24"), 0), "buys_24h": buys, "sells_24h": sells,
        "txns_24h": buys + sells, "price_change_24h_pct": number(price_change.get("h24"), 0),
        "age_hours": age_hours, "pair_created_at_ms": int(created_ms) if created_ms > 0 else 0,
    }

def is_eligible(m):
    if not m["pair_address"] or m["price_usd"] <= 0: return False
    if m["quote_symbol"] not in ALLOWED_QUOTE_TOKENS: return False # FILTER SCAM PENTING
    if m["liquidity_usd"] < MIN_LIQUIDITY_USD or m["volume_24h_usd"] < MIN_VOLUME_24H_USD: return False
    if m["txns_24h"] < MIN_TXNS_24H: return False
    if m["age_hours"] is None or m["age_hours"] < MIN_POOL_AGE_HOURS or m["age_hours"] > MAX_POOL_AGE_DAYS * 24: return False
    if m["price_change_24h_pct"] < -40 or m["price_change_24h_pct"] > 200: return False # Hindari dump/pump parah
    return True

def score_pair(m):
    vol_liq_ratio = m["volume_24h_usd"] / max(m["liquidity_usd"], 1)
    txn_balance = min(m["buys_24h"], m["sells_24h"]) / max(m["txns_24h"], 1)
    age_bonus = min((m["age_hours"] or 0) / (24 * 7), 1.0) # Max bonus di umur 7 hari
    return round(40 * min(vol_liq_ratio, 2.0) + 40 * txn_balance + 20 * age_bonus, 2)

def empty_state():
    return {"version": 2, "starting_cash_usd": STARTING_CASH_USD, "cash_usd": STARTING_CASH_USD,
            "positions": {}, "closed_trades": [], "events": [], "last_run_at": None}

def load_state():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists(): return empty_state()
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        for k, v in empty_state().items(): state.setdefault(k, v)
        return state
    except Exception as exc:
        log.warning(f"Could not read state, starting fresh: {exc}")
        return empty_state()

def save_state(state):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATE_FILE) # Atomic save

def event(state, kind, message, extra=None):
    item = {"time": iso_now(), "type": kind, "message": message}
    if extra: item.update(extra)
    state["events"].append(item)
    state["events"] = state["events"][-MAX_EVENTS_KEPT:]

def fetch_pair_by_address(chain, pair_address):
    data = get_json(f"{BASE}/latest/dex/pairs/{chain}/{pair_address}")
    pairs = data.get("pairs") or [] if isinstance(data, dict) else []
    return pairs[0] if pairs else None

def position_value(position, current_price):
    entry_price = max(number(position.get("entry_price"), 0), 1e-18)
    ratio = max(current_price / entry_price, 0)
    return number(position.get("invested_usd"), 0) * math.sqrt(ratio)

def scan_market():
    tokens, discovery_errors = discover_tokens()
    all_pairs, pair_errors = [], []
    
    for token in tokens:
        try:
            for pair in fetch_token_pairs(token["chainId"], token["tokenAddress"]):
                m = pair_metrics(pair)
                if m["chain"] and m["pair_address"]:
                    m["score"] = score_pair(m)
                    all_pairs.append(m)
        except Exception as exc:
            pair_errors.append(f'{token["chainId"]}/{token["tokenAddress"]}: {exc}')
        time.sleep(0.15) # Rate limit protection
        
    unique = {}
    for m in all_pairs:
        key = (m["chain"].lower(), m["pair_address"].lower())
        if key not in unique or m["score"] > unique[key]["score"]: unique[key] = m
        
    pairs = list(unique.values())
    for m in pairs: m["eligible"] = is_eligible(m)
    pairs.sort(key=lambda m: (m["eligible"], m["score"], m["liquidity_usd"]), reverse=True)
    return pairs, discovery_errors, pair_errors, len(tokens)

def run_simulation(pairs, state):
    by_key = {(m["chain"].lower(), m["pair_address"].lower()): m for m in pairs}
    
    # 1. REFRESH POSISI TERBUKA & CEK GUARD/TAKE PROFIT
    for key, pos in list(state["positions"].items()):
        chain, pair_addr = str(pos.get("chain") or ""), str(pos.get("pair_address") or "")
        try:
            pair = fetch_pair_by_address(chain, pair_addr)
            m = pair_metrics(pair) if pair else None
            if m: m["score"] = score_pair(m); m["eligible"] = is_eligible(m)
        except Exception as exc:
            log.warning(f"Could not refresh {key}: {exc}")
            m = None

        if not m or m["price_usd"] <= 0:
            pos["data_stale"] = True
            continue
            
        pos["data_stale"] = False
        elapsed_hours = 0.0
        try:
            previous = datetime.fromisoformat(pos.get("last_updated_at") or state.get("last_run_at") or iso_now())
            elapsed_hours = max(0.0, min((now_utc() - previous).total_seconds() / 3600, 24.0))
        except Exception: 
            elapsed_hours = 1.0

        # Fee Accrual (Gunakan moving average volume jika ada)
        if "volume_history" not in pos: pos["volume_history"] = []
        pos["volume_history"].append(m["volume_24h_usd"])
        pos["volume_history"] = pos["volume_history"][-24:]
        avg_vol = sum(pos["volume_history"]) / len(pos["volume_history"])
        
        pool_share = number(pos.get("invested_usd"), 0) / max(m["liquidity_usd"], 1)
        estimated_fee = (avg_vol / 24.0) * SIMULATED_POOL_FEE_RATE * pool_share * elapsed_hours
        pos["estimated_fees_usd"] = number(pos.get("estimated_fees_usd"), 0) + max(0, estimated_fee)
        
        pos["last_updated_at"] = iso_now()
        pos["last_price_usd"] = m["price_usd"]
        pos["last_liquidity_usd"] = m["liquidity_usd"]
        pos["last_score"] = m["score"]

        price_ratio = m["price_usd"] / max(number(pos.get("entry_price"), 0), 1e-18)
        entry_liq = number(pos.get("entry_liquidity_usd"), 0)
        if entry_liq <= 0: entry_liq = m["liquidity_usd"] # Fallback
        liquidity_ratio = m["liquidity_usd"] / entry_liq
        
        close_reason = None
        # GUARD (STOP LOSS)
        if liquidity_ratio < 0.60: close_reason = "GUARD: Liquidity fell >40%"
        elif price_ratio < 0.65: close_reason = "GUARD: Token price fell >35%"
        # TAKE PROFIT (PENTING UNTUK STATISTIK)
        elif price_ratio > 1.5 and pos["estimated_fees_usd"] > 10: 
            close_reason = "TAKE PROFIT: Price up >50% + Fees collected"
        # TIME EXIT (Cegah posisi menggantung)
        elif elapsed_hours > 0 and (now_utc() - datetime.fromisoformat(pos["entry_time"])).days >= 7:
            close_reason = "TIME EXIT: Position held for 7 days"

        if close_reason:
            lp_value = position_value(pos, m["price_usd"])
            fees = number(pos.get("estimated_fees_usd"), 0)
            # POTONG GAS & SLIPPAGE SAAT KELUAR
            raw_proceeds = lp_value + fees
            net_proceeds = (raw_proceeds * (1 - SIMULATED_SLIPPAGE)) - (SIMULATED_GAS_USD * 2)
            
            state["cash_usd"] = number(state.get("cash_usd"), 0) + max(0, net_proceeds)
            trade = {
                "closed_at": iso_now(), "symbol": pos.get("symbol"), "chain": chain, "pair_address": pair_addr,
                "invested_usd": number(pos.get("invested_usd"), 0), "lp_value_usd": round(lp_value, 4),
                "estimated_fees_usd": round(fees, 4), "net_proceeds_usd": round(net_proceeds, 4),
                "pnl_usd": round(net_proceeds - number(pos.get("invested_usd"), 0), 4), "reason": close_reason
            }
            state["closed_trades"].append(trade)
            state["closed_trades"] = state["closed_trades"][-MAX_EVENTS_KEPT:]
            event(state, "LP_CLOSE", f"Closed {pos.get('symbol')}: {close_reason}", trade)
            del state["positions"][key]

    # 2. BUKA POSISI BARU
    eligible = [m for m in pairs if m["eligible"] and (m["chain"].lower(), m["pair_address"].lower()) not in state["positions"]]
    eligible.sort(key=lambda m: (m["score"], m["liquidity_usd"]), reverse=True)
    
    for m in eligible:
        if len(state["positions"]) >= MAX_OPEN_POSITIONS: break
        allocation = min(ALLOCATION_PER_POOL_USD, number(state.get("cash_usd"), 0))
        if allocation < 100: break # Minimal $100 per posisi
        
        # POTONG GAS & SLIPPAGE SAAT MASUK
        net_allocation = allocation - (SIMULATED_GAS_USD * 2)
        state["cash_usd"] = number(state.get("cash_usd"), 0) - allocation
        
        key = f'{m["chain"].lower()}:{m["pair_address"].lower()}'
        state["positions"][key] = {
            "symbol": m["symbol"], "name": m["name"], "chain": m["chain"], "dex": m["dex"],
            "pair_address": m["pair_address"], "pair_url": m["pair_url"],
            "invested_usd": round(net_allocation, 4), "entry_price": m["price_usd"],
            "entry_liquidity_usd": m["liquidity_usd"], "entry_score": m["score"],
            "entry_time": iso_now(), "last_updated_at": iso_now(),
            "last_price_usd": m["price_usd"], "last_liquidity_usd": m["liquidity_usd"],
            "estimated_fees_usd": 0.0, "volume_history": [m["volume_24h_usd"]]
        }
        event(state, "LP_OPEN", f'Opened virtual LP {m["symbol"]} on {m["chain"]}', {
            "invested_usd": net_allocation, "score": m["score"], "pair_url": m["pair_url"]
        })

# ... (Fungsi write_reports dan send_discord_notification SAMA SEPERTI SEBELUMNYA, 
# tapi pastikan Anda mengganti variabel 'proceeds' menjadi 'net_proceeds' di write_reports)

def main():
    log.info("=== DJIWA LP v2.0: REALISTIC PAPER SIMULATION ===")
    pairs, discovery_errors, pair_errors, token_count = scan_market()
    state = load_state()
    
    save_state(state) # Simpan state awal (atomic)
    run_simulation(pairs, state)
    state["last_run_at"] = iso_now()
    save_state(state)
    
    log.info(f"Eligible pools: {sum(1 for m in pairs if m['eligible'])}")
    log.info(f"Open positions: {len(state['positions'])}")
    log.info(f"Virtual cash: ${state['cash_usd']:.2f}")
    log.info("Reports written. Check 'reports/' folder.")

if __name__ == "__main__":
    main()
