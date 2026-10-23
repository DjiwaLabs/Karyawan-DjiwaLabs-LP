# parhata_validator.py - Karyawan 2: Validasi Syarat & Anti-Scam (Parhata)
from datetime import datetime, timezone
from config import (
    ALLOWED_QUOTE_TOKENS, MIN_LIQUIDITY_USD, MIN_VOLUME_24H_USD,
    MIN_TXNS_24H, MIN_POOL_AGE_HOURS, MAX_POOL_AGE_DAYS
)

def now_utc(): return datetime.now(timezone.utc)
def number(value, default=0.0):
    try: return float(value) if value is not None and value != "" else default
    except (TypeError, ValueError): return default

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
    if m["quote_symbol"] not in ALLOWED_QUOTE_TOKENS: return False 
    if m["liquidity_usd"] < MIN_LIQUIDITY_USD or m["volume_24h_usd"] < MIN_VOLUME_24H_USD: return False
    if m["txns_24h"] < MIN_TXNS_24H: return False
    if m["age_hours"] is None or m["age_hours"] < MIN_POOL_AGE_HOURS or m["age_hours"] > MAX_POOL_AGE_DAYS * 24: return False
    if m["price_change_24h_pct"] < -40 or m["price_change_24h_pct"] > 200: return False 
    return True

def score_pair(m):
    vol_liq_ratio = m["volume_24h_usd"] / max(m["liquidity_usd"], 1)
    txn_balance = min(m["buys_24h"], m["sells_24h"]) / max(m["txns_24h"], 1)
    age_bonus = min((m["age_hours"] or 0) / (24 * 7), 1.0) 
    return round(40 * min(vol_liq_ratio, 2.0) + 40 * txn_balance + 20 * age_bonus, 2)

def process_and_validate(raw_pairs):
    valid_pairs = []
    for pair in raw_pairs:
        m = pair_metrics(pair)
        if m["chain"] and m["pair_address"]:
            m["eligible"] = is_eligible(m)
            m["score"] = score_pair(m)
            valid_pairs.append(m)
    return valid_pairs
