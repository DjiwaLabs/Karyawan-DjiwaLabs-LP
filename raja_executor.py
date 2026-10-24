# raja_executor.py - Karyawan 3: Eksekutor Disiplin (Raja)
import math
from datetime import datetime, timezone
from config import (
    STARTING_CASH_USD, ALLOCATION_PER_POOL_USD, MAX_OPEN_POSITIONS,
    SIMULATED_POOL_FEE_RATE, SIMULATED_GAS_USD, SIMULATED_SLIPPAGE,
    TAKE_PROFIT_PCT, STOP_LOSS_PRICE_PCT, STOP_LOSS_LIQ_PCT, MAX_HOLD_DAYS
)

def now_utc(): return datetime.now(timezone.utc)
def iso_now(): return now_utc().isoformat(timespec="seconds")
def number(value, default=0.0):
    try: return float(value) if value is not None and value != "" else default
    except (TypeError, ValueError): return default

def position_value(position, current_price):
    entry_price = max(number(position.get("entry_price"), 0), 1e-18)
    ratio = max(current_price / entry_price, 0)
    return number(position.get("invested_usd"), 0) * math.sqrt(ratio)

def event(state, kind, message, extra=None):
    item = {"time": iso_now(), "type": kind, "message": message}
    if extra: item.update(extra)
    state["events"].append(item)
    state["events"] = state["events"][-100:] # Simpan 100 event terakhir

def execute_trades(pairs, state):
    # 1. CEK POSISI TERBUKA (Cari alasan untuk CLOSE)
    for key, pos in list(state["positions"].items()):
        m = next((p for p in pairs if p["chain"].lower() == pos["chain"].lower() and p["pair_address"].lower() == pos["pair_address"].lower()), None)
        
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

        # Hitung Fee
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

        # Evaluasi Aturan Disiplin
        price_ratio = m["price_usd"] / max(number(pos.get("entry_price"), 0), 1e-18)
        entry_liq = number(pos.get("entry_liquidity_usd"), 0)
        if entry_liq <= 0: entry_liq = m["liquidity_usd"]
        liquidity_ratio = m["liquidity_usd"] / entry_liq
        
        close_reason = None
        if liquidity_ratio < (1 - STOP_LOSS_LIQ_PCT): 
            close_reason = f"GUARD: Likuiditas turun >{STOP_LOSS_LIQ_PCT*100}%"
        elif price_ratio < (1 - STOP_LOSS_PRICE_PCT): 
            close_reason = f"STOP LOSS: Harga turun >{STOP_LOSS_PRICE_PCT*100}%"
        elif price_ratio > (1 + TAKE_PROFIT_PCT) and pos["estimated_fees_usd"] > 10: 
            close_reason = f"TAKE PROFIT: Harga naik >{TAKE_PROFIT_PCT*100}%"
        elif (now_utc() - datetime.fromisoformat(pos["entry_time"])).days >= MAX_HOLD_DAYS:
            close_reason = f"TIME EXIT: Ditahan >{MAX_HOLD_DAYS} hari"

        # Eksekusi Close
        if close_reason:
            lp_value = position_value(pos, m["price_usd"])
            fees = number(pos.get("estimated_fees_usd"), 0)
            raw_proceeds = lp_value + fees
            net_proceeds = (raw_proceeds * (1 - SIMULATED_SLIPPAGE)) - (SIMULATED_GAS_USD * 2)
            
            state["cash_usd"] = number(state.get("cash_usd"), 0) + max(0, net_proceeds)
            pnl_trade = net_proceeds - number(pos.get("invested_usd"), 0)
            
            trade = {
                "closed_at": iso_now(), "symbol": pos.get("symbol"), "chain": pos.get("chain"), 
                "pair_address": pos.get("pair_address"), "invested_usd": number(pos.get("invested_usd"), 0), 
                "lp_value_usd": round(lp_value, 4), "estimated_fees_usd": round(fees, 4), 
                "net_proceeds_usd": round(net_proceeds, 4),
                "pnl_usd": round(pnl_trade, 4), "reason": close_reason
            }
            state["closed_trades"].append(trade)
            state["closed_trades"] = state["closed_trades"][-100:]
            
            # Catat Event untuk Panongani
            event(state, "LP_CLOSE", f"Closed {pos.get('symbol')}: {close_reason}", trade)
            
            del state["positions"][key]

    # 2. BUKA POSISI BARU
    eligible = [m for m in pairs if m.get("eligible") and f'{m["chain"].lower()}:{m["pair_address"].lower()}' not in state["positions"]]
    eligible.sort(key=lambda m: (m["score"], m["liquidity_usd"]), reverse=True)
    
    for m in eligible:
        if len(state["positions"]) >= MAX_OPEN_POSITIONS: break
        allocation = min(ALLOCATION_PER_POOL_USD, number(state.get("cash_usd"), 0))
        if allocation < 100: break
        
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
        
        # Catat Event untuk Panongani
        event(state, "LP_OPEN", f'Opened LP {m["symbol"]} on {m["chain"]}', {"invested_usd": net_allocation, "score": m["score"]})
