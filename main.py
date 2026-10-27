# main.py - Sang Manajer (Kepala Divisi)
import json
import os
import sys
import logging
import re
from pathlib import Path
from datetime import datetime, timezone

from siboru_scanner import scan_market, fetch_pair_by_address
from parhata_validator import process_and_validate, pair_metrics, score_pair, is_eligible
from raja_executor import execute_trades, position_value, number
from panongani_reporter import write_reports, send_discord_notification
from pande_harta import cek_saldo # <--- IMPORT PANDE
from config import STARTING_CASH_USD

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("manajer")

DATA_DIR = Path("data")
STATE_FILE = DATA_DIR / "paper_state.json"

def load_state():
    # ... (sama seperti sebelumnya)
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
    
    # --- UJI COBA KONEKSI WEB3 ---
    log.info("Memanggil Pande untuk mengecek saldo Dompet Web3...")
    saldo_devnet = cek_saldo()
    log.info(f"💰 SALDO DEVNET SAAT INI: {saldo_devnet} SOL")
    # -----------------------------

    raw_pairs, disc_err, pair_err, token_count = scan_market()
    log.info(f"Siboru selesai: {len(raw_pairs)} data mentah ditemukan.")
    
    valid_pairs = process_and_validate(raw_pairs)
    eligible_count = sum(1 for p in valid_pairs if p['eligible'])
    log.info(f"Parhata selesai: {eligible_count} pool lolos seleksi.")
    
    state = load_state()
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
    
    execute_trades(valid_pairs, state)
    log.info(f"Raja selesai: {len(state['positions'])} posisi aktif saat ini.")
    
    state["last_run_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_state(state)
    write_reports(valid_pairs, state, disc_err, pair_err, token_count)
    
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
        "open_positions": len(state["positions"]),
        "saldo_devnet": saldo_devnet # Kirim saldo devnet ke discord
    }
    
    send_discord_notification(state, summary_for_discord)
    
    # 5. MANAJER UPDATE KANTOR VIRTUAL & BUBBLE CHAT
    try:
        html_path = Path("index.html")
        if html_path.exists():
            html_content = html_path.read_text(encoding="utf-8")
            
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            pnl_class = "profit" if pnl >= 0 else "loss"
            
            html_content = re.sub(r'<strong id="pnl-total" class="[^"]*">.*?</strong>', 
                                  f'<strong id="pnl-total" class="{pnl_class}">{pnl_str}</strong>', html_content)
            html_content = re.sub(r'<strong id="pnl-mengambang" class="[^"]*">.*?</strong>', 
                                  f'<strong id="pnl-mengambang" class="{pnl_class}">{pnl_str}</strong>', html_content)
            html_content = re.sub(r'<strong id="posisi-terbuka">.*?</strong>', 
                                  f'<strong id="posisi-terbuka">{len(state["positions"])}/5</strong>', html_content)

            recent_events = state.get("events", [])
            last_event = recent_events[-1] if recent_events else None
            
            teks_siboru = f"Radar temukan {token_count} token!" if token_count > 0 else "Pasar sepi nih..."
            teks_parhata = f"Lolos {eligible_count} pool." if eligible_count > 0 else "Semua token sampah, ditolak!"
            teks_raja = f"Saldo Devnet: {saldo_devnet:.2f} SOL" # Tampilkan di bubble Raja
            teks_panongani = "Laporan terkirim ke Bos."

            if last_event:
                msg = last_event.get("message", "")
                pnl_trade = last_event.get("pnl_usd", 0)
                
                if "Opened LP" in msg:
                    symbol = msg.replace("Opened LP ", "").split(" on ")[0]
                    teks_raja = f"Beli {symbol}! (Saldo: {saldo_devnet:.2f} SOL)"
                    teks_panongani = f"Siap, catat {symbol}!"
                elif "TAKE PROFIT" in msg:
                    symbol = msg.replace("Closed ", "").split(":")[0]
                    teks_raja = f"TP {symbol}! Cuan +${pnl_trade:.0f}!"
                    teks_panongani = "Mantap! Ekuitas naik Bos!"
                    teks_siboru = "Asik, jajan kopi dulu!"
                elif "STOP LOSS" in msg or "GUARD" in msg:
                    symbol = msg.replace("Closed ", "").split(":")[0]
                    teks_raja = f"Cut loss {symbol}. Rugi ${abs(pnl_trade):.0f}."
                    teks_panongani = "Tenang, laporin ke Bos ah."
                    teks_parhata = "Maaf, token itu lolos radar."

            html_content = re.sub(r'(<div class="bubble bubble-siboru" id="bubble-siboru">).*?(</div>)', f'\\1{teks_siboru}\\2', html_content)
            html_content = re.sub(r'(<div class="bubble bubble-parhata" id="bubble-parhata">).*?(</div>)', f'\\1{teks_parhata}\\2', html_content)
            html_content = re.sub(r'(<div class="bubble bubble-raja" id="bubble-raja">).*?(</div>)', f'\\1{teks_raja}\\2', html_content)
            html_content = re.sub(r'(<div class="bubble bubble-panongani" id="bubble-panongani">).*?(</div>)', f'\\1{teks_panongani}\\2', html_content)
            
            html_path.write_text(html_content, encoding="utf-8")
    except Exception as e:
        log.error(f"Gagal update Kantor Virtual: {e}")
    
    log.info("=== RAPAT SELESAI ===")

if __name__ == "__main__":
    main()
