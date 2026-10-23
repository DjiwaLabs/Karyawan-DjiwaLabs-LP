# main.py - Sang Manajer (Kepala Divisi)
import json, os
from pathlib import Path

# Panggil Karyawan
from siboru_scanner import scan_market, fetch_pair_by_address
from parhata_validator import process_and_validate
from raja_executor import execute_trades
from panongani_reporter import write_reports, send_discord_notification

DATA_DIR = Path("data")
STATE_FILE = DATA_DIR / "paper_state.json"

def load_state():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        return {"version": 2, "starting_cash_usd": 10000.0, "cash_usd": 10000.0, "positions": {}, "closed_trades": [], "events": [], "last_run_at": None}
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        state.setdefault("positions", {})
        return state
    except Exception:
        return {"version": 2, "starting_cash_usd": 10000.0, "cash_usd": 10000.0, "positions": {}, "closed_trades": [], "events": [], "last_run_at": None}

def save_state(state):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_FILE)

def main():
    print("=== MANAJER: Memulai Rapat Karyawan DJIWA LP ===")
    
    # 1. Siboru Mencari Data
    raw_pairs, disc_err, pair_err, token_count = scan_market()
    print(f"Siboru selesai: {len(raw_pairs)} data mentah ditemukan.")
    
    # 2. Parhata Memvalidasi
    valid_pairs = process_and_validate(raw_pairs)
    print(f"Parhata selesai: {sum(1 for p in valid_pairs if p['eligible'])} pool lolos seleksi.")
    
    # Tambahkan data posisi lama ke valid_pairs agar Raja bisa evaluasi
    state = load_state()
    for pos in state["positions"].values():
        try:
            p = fetch_pair_by_address(pos["chain"], pos["pair_address"])
            if p:
                from parhata_validator import pair_metrics, score_pair, is_eligible
                m = pair_metrics(p)
                m["score"] = score_pair(m)
                m["eligible"] = is_eligible(m)
                valid_pairs.append(m)
        except: pass
    
    # 3. Raja Eksekusi
    execute_trades(valid_pairs, state)
    print(f"Raja selesai: {len(state['positions'])} posisi aktif saat ini.")
    
    # 4. Panongani Lapor
    state["last_run_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds")
    save_state(state)
    write_reports(valid_pairs, state, disc_err, pair_err, token_count)
    
    # Ambil ringkasan untuk discord
    equity = state["cash_usd"] + sum(p.get("invested_usd", 0) for p in state["positions"].values()) # simplified
    summary = {"generated_at": state["last_run_at"], "equity_usd": equity, "total_pnl_usd": equity - 10000, "cash_usd": state["cash_usd"], "open_positions": len(state["positions"])}
    send_discord_notification(state, summary)
    
    print("=== RAPAT SELESAI ===")

if __name__ == "__main__":
    main()
