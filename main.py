#!/usr/bin/env python3
"""
DJIWA LP - DexScreener live scanner + virtual LP simulator.
No wallet, no private key, no signing, and no on-chain transactions.
"""
import csv
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://api.dexscreener.com"
DATA_DIR = Path("data")
REPORT_DIR = Path("reports")
STATE_FILE = DATA_DIR / "paper_state.json"

# Virtual portfolio settings. Edit these values if you want different simulation limits.
STARTING_CASH_USD = 10_000.0
ALLOCATION_PER_POOL_USD = 500.0
MAX_OPEN_POSITIONS = 5
MIN_LIQUIDITY_USD = 20_000.0
MIN_VOLUME_24H_USD = 10_000.0
MIN_TXNS_24H = 100
MIN_POOL_AGE_HOURS = 1.0
MAX_POOL_AGE_DAYS = 365
SIMULATED_POOL_FEE_RATE = 0.003  # Assumption: 0.30%; actual DEX pool fee may differ.
MAX_DISCOVERY_TOKENS = 30
MAX_EVENTS_KEPT = 100

def now_utc():
    return datetime.now(timezone.utc)

def iso_now():
    return now_utc().isoformat(timespec="seconds")

def number(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def get_json(url, timeout=20):
    req = Request(url, headers={"User-Agent": "DJIWA-LP-PaperSimulator/1.0", "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"API HTTP {response.status}: {url}")
        return json.loads(response.read().decode("utf-8"))

def api_list(path):
    data = get_json(BASE + path)
    if isinstance(data, list):
        return data
    return []

def discover_tokens():
    """Use public discovery endpoints; no API key is required for these requests."""
    candidates = []
    errors = []
    for endpoint in ("/token-profiles/latest/v1", "/token-boosts/latest/v1"):
        try:
            candidates.extend(api_list(endpoint))
        except Exception as exc:
            errors.append(f"{endpoint}: {exc}")
    # Deduplicate by chain + token address, then keep a bounded number of API calls.
    seen = set()
    unique = []
    for item in candidates:
        chain = str(item.get("chainId") or "").strip()
        address = str(item.get("tokenAddress") or "").strip()
        key = (chain.lower(), address.lower())
        if not chain or not address or key in seen:
            continue
        seen.add(key)
        unique.append({"chainId": chain, "tokenAddress": address})
    return unique[:MAX_DISCOVERY_TOKENS], errors

def fetch_token_pairs(chain, address):
    url = f"{BASE}/token-pairs/v1/{chain}/{address}"
    data = get_json(url)
    return data if isinstance(data, list) else []

def pair_metrics(pair):
    volume = pair.get("volume") or {}
    txns = pair.get("txns") or {}
    h24_txns = txns.get("h24") or {}
    liquidity = pair.get("liquidity") or {}
    price_change = pair.get("priceChange") or {}
    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}
    created_ms = number(pair.get("pairCreatedAt"), 0)
    age_hours = None
    if created_ms > 0:
        age_hours = max(0.0, (now_utc().timestamp() * 1000 - created_ms) / 3_600_000)
    buys = int(number(h24_txns.get("buys"), 0))
    sells = int(number(h24_txns.get("sells"), 0))
    total_txns = buys + sells
    return {
        "chain": str(pair.get("chainId") or ""),
        "dex": str(pair.get("dexId") or ""),
        "pair_address": str(pair.get("pairAddress") or ""),
        "pair_url": str(pair.get("url") or ""),
        "token_address": str(base.get("address") or ""),
        "symbol": str(base.get("symbol") or "UNKNOWN"),
        "name": str(base.get("name") or "Unknown"),
        "quote_symbol": str(quote.get("symbol") or ""),
        "price_usd": number(pair.get("priceUsd"), 0),
        "liquidity_usd": number(liquidity.get("usd"), 0),
        "volume_24h_usd": number(volume.get("h24"), 0),
        "buys_24h": buys,
        "sells_24h": sells,
        "txns_24h": total_txns,
        "price_change_24h_pct": number(price_change.get("h24"), 0),
        "fdv_usd": number(pair.get("fdv"), 0),
        "market_cap_usd": number(pair.get("marketCap"), 0),
        "age_hours": age_hours,
        "pair_created_at_ms": int(created_ms) if created_ms > 0 else 0,
    }

def is_eligible(m):
    if not m["pair_address"] or m["price_usd"] <= 0:
        return False
    if m["liquidity_usd"] < MIN_LIQUIDITY_USD:
        return False
    if m["volume_24h_usd"] < MIN_VOLUME_24H_USD:
        return False
    if m["txns_24h"] < MIN_TXNS_24H:
        return False
    if m["age_hours"] is None or m["age_hours"] < MIN_POOL_AGE_HOURS:
        return False
    if m["age_hours"] > MAX_POOL_AGE_DAYS * 24:
        return False
    return True

def score_pair(m):
    # A transparent heuristic, not a prediction or guarantee of safety.
    volume_to_liquidity = m["volume_24h_usd"] / max(m["liquidity_usd"], 1)
    txn_balance = min(m["buys_24h"], m["sells_24h"]) / max(m["buys_24h"] + m["sells_24h"], 1)
    age_bonus = min((m["age_hours"] or 0) / 24, 1.0)
    return round(50 * min(volume_to_liquidity, 2.0) + 30 * txn_balance + 20 * age_bonus, 2)

def empty_state():
    return {
        "version": 1,
        "starting_cash_usd": STARTING_CASH_USD,
        "cash_usd": STARTING_CASH_USD,
        "positions": {},
        "closed_trades": [],
        "events": [],
        "last_run_at": None,
    }

def load_state():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        return empty_state()
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        state.setdefault("starting_cash_usd", STARTING_CASH_USD)
        state.setdefault("cash_usd", STARTING_CASH_USD)
        state.setdefault("positions", {})
        state.setdefault("closed_trades", [])
        state.setdefault("events", [])
        return state
    except Exception as exc:
        print(f"WARNING: Could not read state; starting fresh: {exc}")
        return empty_state()

def save_state(state):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

def event(state, kind, message, extra=None):
    item = {"time": iso_now(), "type": kind, "message": message}
    if extra:
        item.update(extra)
    state["events"].append(item)
    state["events"] = state["events"][-MAX_EVENTS_KEPT:]

def fetch_pair_by_address(chain, pair_address):
    url = f"{BASE}/latest/dex/pairs/{chain}/{pair_address}"
    data = get_json(url)
    pairs = data.get("pairs") or [] if isinstance(data, dict) else []
    return pairs[0] if pairs else None

def position_value(position, current_price):
    entry_price = max(number(position.get("entry_price"), 0), 1e-18)
    ratio = max(current_price / entry_price, 0)
    # Idealized 50/50 constant-product LP value, excluding fees and other effects.
    return number(position.get("invested_usd"), 0) * math.sqrt(ratio)

def scan_market():
    tokens, discovery_errors = discover_tokens()
    all_pairs = []
    pair_errors = []
    for token in tokens:
        try:
            pairs = fetch_token_pairs(token["chainId"], token["tokenAddress"])
            for pair in pairs:
                m = pair_metrics(pair)
                if m["chain"] and m["pair_address"]:
                    m["score"] = score_pair(m)
                    all_pairs.append(m)
        except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as exc:
            pair_errors.append(f'{token["chainId"]}/{token["tokenAddress"]}: {exc}')
        except Exception as exc:
            pair_errors.append(f'{token["chainId"]}/{token["tokenAddress"]}: {exc}')
        time.sleep(0.10)  # Gentle pacing; well below the documented endpoint limit.
    # Prefer the highest-scoring pair per chain/pool address.
    unique = {}
    for m in all_pairs:
        key = (m["chain"].lower(), m["pair_address"].lower())
        if key not in unique or m["score"] > unique[key]["score"]:
            unique[key] = m
    pairs = list(unique.values())
    for m in pairs:
        m["eligible"] = is_eligible(m)
    pairs.sort(key=lambda m: (m["eligible"], m["score"], m["liquidity_usd"]), reverse=True)
    return pairs, discovery_errors, pair_errors, len(tokens)

def run_simulation(pairs, state):
    by_key = {(m["chain"].lower(), m["pair_address"].lower()): m for m in pairs}
    # Refresh existing virtual LP positions even if they no longer appear in discovery.
    for key, pos in list(state["positions"].items()):
        chain = str(pos.get("chain") or "")
        pair_addr = str(pos.get("pair_address") or "")
        try:
            pair = fetch_pair_by_address(chain, pair_addr)
            if pair:
                m = pair_metrics(pair)
                m["score"] = score_pair(m)
                m["eligible"] = is_eligible(m)
                by_key[(m["chain"].lower(), m["pair_address"].lower())] = m
            else:
                m = None
        except Exception as exc:
            print(f"WARNING: could not refresh position {key}: {exc}")
            m = None
        if not m or m["price_usd"] <= 0:
            continue

        elapsed_hours = 1.0
        try:
            previous = datetime.fromisoformat(pos.get("last_updated_at") or state.get("last_run_at") or iso_now())
            elapsed_hours = max(0.0, min((now_utc() - previous).total_seconds() / 3600, 24.0))
        except Exception:
            pass
        current_liq = m["liquidity_usd"]
        # Estimated fee accrual based on current 24h volume and assumed fee tier.
        pool_share = number(pos.get("invested_usd"), 0) / max(current_liq, 1)
        estimated_fee = (m["volume_24h_usd"] / 24.0) * SIMULATED_POOL_FEE_RATE * pool_share * elapsed_hours
        pos["estimated_fees_usd"] = number(pos.get("estimated_fees_usd"), 0) + max(0, estimated_fee)
        pos["last_updated_at"] = iso_now()
        pos["last_price_usd"] = m["price_usd"]
        pos["last_liquidity_usd"] = current_liq
        pos["last_score"] = m["score"]

        price_ratio = m["price_usd"] / max(number(pos.get("entry_price"), 0), 1e-18)
        entry_liq = max(number(pos.get("entry_liquidity_usd"), 0), 1)
        liquidity_ratio = current_liq / entry_liq
        close_reason = None
        if liquidity_ratio < 0.60:
            close_reason = "GUARD: pool liquidity fell more than 40% from entry"
        elif price_ratio < 0.65:
            close_reason = "GUARD: token price fell more than 35% from entry"
        if close_reason:
            lp_value = position_value(pos, m["price_usd"])
            fees = number(pos.get("estimated_fees_usd"), 0)
            proceeds = max(0, lp_value + fees)
            state["cash_usd"] = number(state.get("cash_usd"), 0) + proceeds
            trade = {
                "closed_at": iso_now(),
                "symbol": pos.get("symbol"),
                "chain": chain,
                "pair_address": pair_addr,
                "invested_usd": number(pos.get("invested_usd"), 0),
                "lp_value_usd": round(lp_value, 4),
                "estimated_fees_usd": round(fees, 4),
                "proceeds_usd": round(proceeds, 4),
                "pnl_usd": round(proceeds - number(pos.get("invested_usd"), 0), 4),
                "reason": close_reason,
                "pair_url": pos.get("pair_url", ""),
            }
            state["closed_trades"].append(trade)
            state["closed_trades"] = state["closed_trades"][-MAX_EVENTS_KEPT:]
            event(state, "LP_CLOSE", f'Closed virtual LP {pos.get("symbol")}: {close_reason}', trade)
            del state["positions"][key]

    # Open virtual LP positions from the highest-scoring eligible pools.
    eligible = [m for m in pairs if m["eligible"]]
    eligible.sort(key=lambda m: (m["score"], m["liquidity_usd"], m["volume_24h_usd"]), reverse=True)
    for m in eligible:
        key = f'{m["chain"].lower()}:{m["pair_address"].lower()}'
        if key in state["positions"]:
            continue
        if len(state["positions"]) >= MAX_OPEN_POSITIONS:
            break
        allocation = min(ALLOCATION_PER_POOL_USD, number(state.get("cash_usd"), 0))
        if allocation < 50:
            break
        state["cash_usd"] = number(state.get("cash_usd"), 0) - allocation
        pos = {
            "symbol": m["symbol"],
            "name": m["name"],
            "chain": m["chain"],
            "dex": m["dex"],
            "pair_address": m["pair_address"],
            "pair_url": m["pair_url"],
            "invested_usd": round(allocation, 4),
            "entry_price": m["price_usd"],
            "entry_liquidity_usd": m["liquidity_usd"],
            "entry_volume_24h_usd": m["volume_24h_usd"],
            "entry_score": m["score"],
            "entry_time": iso_now(),
            "last_updated_at": iso_now(),
            "last_price_usd": m["price_usd"],
            "last_liquidity_usd": m["liquidity_usd"],
            "estimated_fees_usd": 0.0,
        }
        state["positions"][key] = pos
        event(state, "LP_OPEN", f'Opened virtual LP {m["symbol"]} on {m["chain"]}', {
            "invested_usd": allocation, "score": m["score"], "pair_url": m["pair_url"]
        })

def write_reports(pairs, state, discovery_errors, pair_errors, token_count):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = iso_now()
    open_rows = []
    total_position_value = 0.0
    for key, pos in state["positions"].items():
        value = position_value(pos, number(pos.get("last_price_usd"), number(pos.get("entry_price"), 0)))
        fees = number(pos.get("estimated_fees_usd"), 0)
        total_position_value += value + fees
        open_rows.append({
            "chain": pos.get("chain", ""),
            "dex": pos.get("dex", ""),
            "symbol": pos.get("symbol", ""),
            "pair_address": pos.get("pair_address", ""),
            "pair_url": pos.get("pair_url", ""),
            "invested_usd": round(number(pos.get("invested_usd"), 0), 4),
            "entry_price_usd": number(pos.get("entry_price"), 0),
            "last_price_usd": number(pos.get("last_price_usd"), 0),
            "lp_value_estimate_usd": round(value, 4),
            "estimated_fees_usd": round(fees, 4),
            "unrealized_pnl_estimate_usd": round(value + fees - number(pos.get("invested_usd"), 0), 4),
            "entry_liquidity_usd": number(pos.get("entry_liquidity_usd"), 0),
            "last_liquidity_usd": number(pos.get("last_liquidity_usd"), 0),
            "entry_time": pos.get("entry_time", ""),
        })
    cash = number(state.get("cash_usd"), 0)
    equity = cash + total_position_value
    closed_pnl = sum(number(t.get("pnl_usd"), 0) for t in state.get("closed_trades", []))
    summary = {
        "project": "DJIWA LP - DexScreener Live Scan + Paper LP",
        "generated_at": stamp,
        "mode": "PAPER_ONLY_NO_ONCHAIN_TRANSACTIONS",
        "data_source": "DexScreener public API",
        "discovery_tokens_checked": token_count,
        "pairs_seen": len(pairs),
        "eligible_pools": sum(1 for m in pairs if m["eligible"]),
        "open_positions": len(state["positions"]),
        "cash_usd": round(cash, 4),
        "open_positions_value_estimate_usd": round(total_position_value, 4),
        "total_equity_estimate_usd": round(equity, 4),
        "equity_pnl_estimate_usd": round(equity - number(state.get("starting_cash_usd"), STARTING_CASH_USD), 4),
        "closed_trades_pnl_recorded_usd": round(closed_pnl, 4),
        "starting_cash_usd": number(state.get("starting_cash_usd"), STARTING_CASH_USD),
        "assumed_pool_fee_rate": SIMULATED_POOL_FEE_RATE,
        "warnings": [
            "Virtual LP valuation is an approximation, not a live on-chain LP position.",
            "Fee estimates assume a 0.30% pool fee and current 24h volume spread evenly over time.",
            "DexScreener public market data does not guarantee token safety or pool fee accuracy.",
        ] + [f"Discovery warning: {e}" for e in discovery_errors] + [f"Pair warning: {e}" for e in pair_errors[:10]],
    }
    (REPORT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (REPORT_DIR / "live_scan.csv").open("w", newline="", encoding="utf-8-sig") as f:
        fields = ["chain", "dex", "symbol", "name", "pair_address", "pair_url", "price_usd",
                  "liquidity_usd", "volume_24h_usd", "buys_24h", "sells_24h", "txns_24h",
                  "price_change_24h_pct", "age_hours", "score", "eligible"]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for m in pairs:
            row = dict(m)
            row["age_hours"] = round(m["age_hours"], 2) if m["age_hours"] is not None else ""
            writer.writerow(row)
    with (REPORT_DIR / "open_positions.csv").open("w", newline="", encoding="utf-8-sig") as f:
        fields = list(open_rows[0].keys()) if open_rows else [
            "chain", "dex", "symbol", "pair_address", "pair_url", "invested_usd",
            "entry_price_usd", "last_price_usd", "lp_value_estimate_usd", "estimated_fees_usd",
            "unrealized_pnl_estimate_usd", "entry_liquidity_usd", "last_liquidity_usd", "entry_time"
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(open_rows)
    (REPORT_DIR / "events.json").write_text(json.dumps(state.get("events", [])[-MAX_EVENTS_KEPT:], indent=2), encoding="utf-8")
    (REPORT_DIR / "closed_trades.json").write_text(json.dumps(state.get("closed_trades", [])[-MAX_EVENTS_KEPT:], indent=2), encoding="utf-8")


def send_discord_notification(pairs, state, discovery_errors, pair_errors, token_count):
    """Send a compact run summary to Discord via an optional GitHub Actions secret."""
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("Discord webhook not configured; skipping notification.")
        return

    eligible = [m for m in pairs if m.get("eligible")]
    eligible.sort(key=lambda m: (m.get("score", 0), m.get("liquidity_usd", 0)), reverse=True)
    total_position_value = 0.0
    for pos in state.get("positions", {}).values():
        value = position_value(pos, number(pos.get("last_price_usd"), number(pos.get("entry_price"), 0)))
        total_position_value += value + number(pos.get("estimated_fees_usd"), 0)
    cash = number(state.get("cash_usd"), 0)
    equity = cash + total_position_value
    starting = number(state.get("starting_cash_usd"), STARTING_CASH_USD)
    pnl = equity - starting

    def usd(value):
        return f"${value:,.2f}"

    lines = [
        f"**Mode:** PAPER SIMULATION ONLY — tidak ada transaksi blockchain",
        f"**Waktu (UTC):** {state.get('last_run_at') or iso_now()}",
        f"**Token discovery diperiksa:** {token_count}",
        f"**Pool terpantau:** {len(pairs)}",
        f"**Pool lolos filter:** {len(eligible)}",
        f"**Posisi LP virtual terbuka:** {len(state.get('positions', {}))}",
        f"**Saldo virtual:** {usd(cash)}",
        f"**Estimasi nilai portofolio:** {usd(equity)}",
        f"**Estimasi P/L total:** {'+' if pnl >= 0 else ''}{usd(pnl)}",
    ]
    if eligible:
        lines.append("")
        lines.append("**Top pool lolos filter:**")
        for m in eligible[:5]:
            symbol = str(m.get("symbol", "UNKNOWN"))[:24]
            url = str(m.get("pair_url", "")).strip()
            score = number(m.get("score"), 0)
            liq = usd(number(m.get("liquidity_usd"), 0))
            vol = usd(number(m.get("volume_24h_usd"), 0))
            line = f"• **{symbol}** — skor `{score}` | likuiditas {liq} | volume 24j {vol}"
            if url.startswith("https://") or url.startswith("http://"):
                line += f" | [DexScreener]({url})"
            lines.append(line)
    if discovery_errors or pair_errors:
        lines.append("")
        lines.append(f"⚠️ Peringatan API: {len(discovery_errors) + len(pair_errors)} masalah (lihat log GitHub Actions).")
    description = "\n".join(lines)
    # Discord embed description limit is 4096 characters.
    description = description[:3900]
    payload = {
        "username": "DJIWA LP Manager",
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "title": "📊 Laporan Karyawan Digital DJIWA LP",
            "description": description,
            "color": 3447003 if pnl >= 0 else 15158332,
            "footer": {"text": "DexScreener public data • Paper simulation • Bukan saran investasi"},
        }],
    }
    req = Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "DJIWA-LP-Discord-Notifier/1.0"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as response:
            if response.status not in (200, 204):
                raise RuntimeError(f"Discord returned HTTP {response.status}")
        print("Discord notification sent.")
    except Exception as exc:
        # Keep scan/report output usable even if Discord is temporarily unavailable.
        print(f"WARNING: Discord notification failed: {type(exc).__name__}: {exc}")

def main():
    print("=== DJIWA LP: LIVE DATA + PAPER-ONLY LP SIMULATION ===")
    print("No wallet, no private key, no transaction signing.")
    pairs, discovery_errors, pair_errors, token_count = scan_market()
    print(f"Discovery tokens checked: {token_count}; pools seen: {len(pairs)}")
    state = load_state()
    run_simulation(pairs, state)
    state["last_run_at"] = iso_now()
    save_state(state)
    write_reports(pairs, state, discovery_errors, pair_errors, token_count)
    send_discord_notification(pairs, state, discovery_errors, pair_errors, token_count)
    eligible_count = sum(1 for m in pairs if m["eligible"])
    print(f"Eligible pools: {eligible_count}")
    print(f"Open virtual LP positions: {len(state['positions'])}")
    print(f"Virtual cash: ${state['cash_usd']:.2f}")
    print("Reports written to reports/")
    # Treat total discovery API failure as an error so Actions clearly shows it.
    if not pairs and discovery_errors:
        print("ERROR: No market data retrieved. Check API availability/network.")
        sys.exit(1)

if __name__ == "__main__":
    main()
