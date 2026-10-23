# panongani_reporter.py - Karyawan 4: Laporan & Discord (Panongani)
import csv, json, os
from pathlib import Path
from urllib.request import Request, urlopen
from datetime import datetime, timezone
from raja_executor import position_value, number, iso_now

REPORT_DIR = Path("reports")

def write_reports(pairs, state, discovery_errors, pair_errors, token_count):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    open_rows = []
    total_position_value = 0.0
    
    for key, pos in state["positions"].items():
        value = position_value(pos, number(pos.get("last_price_usd"), number(pos.get("entry_price"), 0)))
        fees = number(pos.get("estimated_fees_usd"), 0)
        total_position_value += value + fees
        open_rows.append({
            "symbol": pos.get("symbol", ""), "chain": pos.get("chain", ""),
            "invested_usd": round(number(pos.get("invested_usd"), 0), 2),
            "current_value_usd": round(value + fees, 2),
            "pnl_usd": round(value + fees - number(pos.get("invested_usd"), 0), 2)
        })
        
    cash = number(state.get("cash_usd"), 0)
    equity = cash + total_position_value
    pnl = equity - number(state.get("starting_cash_usd"), 10000)
    
    summary = {
        "generated_at": iso_now(), "tokens_checked": token_count, "pairs_seen": len(pairs),
        "open_positions": len(state["positions"]), "cash_usd": round(cash, 2),
        "equity_usd": round(equity, 2), "total_pnl_usd": round(pnl, 2),
        "errors": discovery_errors + pair_errors
    }
    
    (REPORT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    
    # Simpan CSV sederhana
    if open_rows:
        with (REPORT_DIR / "open_positions.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=open_rows[0].keys())
            writer.writeheader()
            writer.writerows(open_rows)

def send_discord_notification(state, summary):
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("Discord webhook not configured.")
        return

    def usd(val): return f"${val:,.2f}"
    pnl = summary["total_pnl_usd"]
    
    desc = (
        f"**Status:** PAPER SIMULATION 🟢\n"
        f"**Waktu:** {summary['generated_at']} UTC\n"
        f"**Total Ekuitas:** {usd(summary['equity_usd'])}\n"
        f"**P/L Total:** {'+' if pnl >= 0 else ''}{usd(pnl)}\n"
        f"**Saldo Kas:** {usd(summary['cash_usd'])}\n"
        f"**Posisi Terbuka:** {summary['open_positions']} / 5\n"
    )
    
    if state["positions"]:
        desc += "\n**Detail Posisi:**\n"
        for pos in state["positions"].values():
            val = position_value(pos, number(pos.get("last_price_usd"), 0)) + number(pos.get("estimated_fees_usd"), 0)
            roi = ((val / number(pos.get("invested_usd"), 1)) - 1) * 100
            desc += f"• {pos['symbol']} ({pos['chain']}): {roi:+.1f}% | {usd(val)}\n"
            
    payload = {
        "username": "Panongani (DJIWA LP)",
        "embeds": [{
            "title": "📊 Laporan Karyawan Digital",
            "description": desc[:4000],
            "color": 3447003 if pnl >= 0 else 15158332,
            "footer": {"text": "DexScreener • Paper Simulator • Bukan Saran Investasi"}
        }]
    }
    
    try:
        req = Request(webhook_url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as response:
            if response.status not in (200, 204): raise Exception("HTTP Error")
        print("Discord notification sent.")
    except Exception as exc:
        print(f"WARNING: Discord failed: {exc}")
