# main.py - Sang Manajer (Kepala Divisi)
import json
import os
import sys
import logging
import re
from pathlib import Path
from datetime import datetime, timezone

# Import Karyawan
from siboru_scanner import scan_market, fetch_pair_by_address
from parhata_validator import process_and_validate, pair_metrics, score_pair, is_eligible
from raja_executor import execute_trades, position_value, number
from panongani_reporter import write_reports, send_discord_notification
from config import STARTING_CASH_USD

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("manajer")

DATA_DIR = Path("data")
STATE_FILE = DATA_DIR / "paper_state.json"

def load_state():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        return {"version": 2, "starting_cash_usd": STARTING_CASH_USD, "cash_usd": STARTING_CASH_USD, "positions": {}, "closed_trades": [], "events": [], "last_run_at": None}
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        state.setdefault("positions", {})
        return state
    except Exception as exc:
        log.error(f"Gagal baca state: {exc}")
        return {"version": 2, "starting_cash_usd": STARTING_CASH_USD, "cash_usd": STARTING_CASH_USD, "positions": {}, "closed_trades": [], "events": [], "last_run_at": None}

def save_state(state):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_FILE)

def main():
    log.info("=== MANAJER: Memulai Rapat Karyawan DJIWA LP ===")
    
    # 1. Siboru Mencari Data
    raw_pairs, disc_err, pair_err, token_count = scan_market()
    log.info(f"Siboru selesai: {len(raw_pairs)} data mentah ditemukan.")
    
    # 2. Parhata Memvalidasi
    valid_pairs = process_and_validate(raw_pairs)
    log.info(f"Parhata selesai: {sum(1 for p in valid_pairs if p['eligible'])} pool lolos seleksi.")
    
    state = load_state()
    
    # Tambahkan data posisi lama agar Raja bisa evaluasi harga terbarunya
    for pos in state["positions"].values():
        try:
            p = fetch_pair_by_address(pos["chain"], pos["pair_address"])
            if p:
                m = pair_metrics(p)
                m["score"] = score_pair(m)
                m["eligible"] = is_eligible(m)
                valid_pairs.append(m)
        except Exception as exc: 
            log.warning(f"Gagal refresh {pos.get('symbol')}: {exc}")
    
    # 3. Raja Eksekusi
    execute_trades(valid_pairs, state)
    log.info(f"Raja selesai: {len(state['positions'])} posisi aktif saat ini.")
    
    # 4. Panongani Lapor
    state["last_run_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_state(state)
    
    # Tulis laporan ke file
    write_reports(valid_pairs, state, disc_err, pair_err, token_count)
    
    # --- PERHITUNGAN EKUITAS ---
    total_position_value = 0.0
    for p in state["positions"].values():
        total_position_value += position_value(p, number(p.get("last_price_usd"), 0)) + number(p.get("estimated_fees_usd"), 0)
        
    cash = number(state.get("cash_usd"), 0)
    equity = cash + total_position_value
    pnl = equity - number(state.get("starting_cash_usd"), STARTING_CASH_USD)
    
    summary_for_discord = {
        "generated_at": state["last_run_at"], 
        "equity_usd": equity, 
        "total_pnl_usd": pnl, 
        "cash_usd": cash, 
        "open_positions": len(state["positions"])
    }
    
    # Suruh Panongani kirim ke Discord
    send_discord_notification(state, summary_for_discord)
    
    # 5. Manajer Update Kantor Virtual (index.html)
    try:
        html_path = Path("index.html")
        if html_path.exists():
            html_content = html_path.read_text(encoding="utf-8")
            
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            pnl_class = "profit" if pnl >= 0 else "loss"
            
            float_str = pnl_str
            float_class = pnl_class

            html_content = re.sub(r'<strong class="[^"]*">[-+]\$[\d\.]+</strong>\s*</div>\s*<div class="stat-box">\s*<span>PnL Mengambang', 
                                  f'<strong class="{pnl_class}">{pnl_str}</strong></div><div class="stat-box"><span>PnL Mengambang', html_content, count=1)
            
            html_content = re.sub(r'<strong class="[^"]*">[-+]\$[\d\.]+</strong>\s*</div>\s*<div class="stat-box">\s*<span>Posisi Terbuka', 
                                  f'<strong class="{float_class}">{float_str}</strong></div><div class="stat-box"><span>Posisi Terbuka', html_content, count=1)
            
            html_content = re.sub(r'<strong>\d+/\d+</strong>', 
                                  f'<strong>{len(state["positions"])}/5</strong>', html_content, count=1)
            
            html_path.write_text(html_content, encoding="utf-8")
            log.info("Kantor Virtual (index.html) berhasil diperbarui!")
    except Exception as e:
        log.error(f"Gagal update Kantor Virtual: {e}")
    
    log.info("=== RAPAT SELESAI ===")

if __name__ == "__main__":
    main()
