
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

PROJECT = "DJIWA Liquidity Provider"
INITIAL_CASH = float(os.getenv("SIMULATION_CASH", "1000"))
MAX_POSITION = 50.0
FEE_RATE = 0.01

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

# Data contoh untuk menguji sistem.
# Belum merupakan data pasar live dari GMGN.
DEMO_TOKENS = [
    {
        "symbol": "DEMO1",
        "price": 1.00,
        "liquidity": 50000,
        "volume": 12000,
    },
    {
        "symbol": "DEMO2",
        "price": 0.50,
        "liquidity": 12000,
        "volume": 3000,
    },
    {
        "symbol": "DEMO3",
        "price": 2.00,
        "liquidity": 1500,
        "volume": 500,
    },
]


def scout(tokens):
    """DJIWA LP SCOUT: mengumpulkan kandidat token."""
    print("\n[DJIWA LP SCOUT] Memindai kandidat...")
    return tokens


def guard(tokens):
    """DJIWA LP GUARD: menyaring kandidat berdasarkan aturan demo."""
    print("[DJIWA LP GUARD] Memeriksa likuiditas dan volume...")
    approved = []

    for token in tokens:
        if token["price"] <= 0:
            continue
        if token["liquidity"] < 10000:
            print(f"DITOLAK {token['symbol']}: likuiditas terlalu rendah")
            continue
        if token["volume"] < 1000:
            print(f"DITOLAK {token['symbol']}: volume terlalu rendah")
            continue
        approved.append(token)

    return approved


def execute_simulation(tokens):
    """DJIWA LP EXECUTOR: simulasi, tidak mengirim transaksi nyata."""
    print("[DJIWA LP EXECUTOR] PAPER TRADING AKTIF")
    cash = INITIAL_CASH
    positions = []
    trades = []

    for token in tokens:
        amount = min(MAX_POSITION, cash)
        if amount <= 0:
            break

        fee = amount * FEE_RATE
        quantity = (amount - fee) / token["price"]
        cash -= amount

        # Simulasi perubahan harga -1%, 0%, atau +2%.
        # Bukan prediksi maupun harga pasar aktual.
        simulated_change = {
            "DEMO1": 0.02,
            "DEMO2": -0.01,
            "DEMO3": 0.00,
        }.get(token["symbol"], 0.00)

        exit_price = token["price"] * (1 + simulated_change)
        gross_exit = quantity * exit_price
        exit_fee = gross_exit * FEE_RATE
        net_exit = gross_exit - exit_fee
        pnl = net_exit - amount

        cash += net_exit

        positions.append({
            "symbol": token["symbol"],
            "entry_price": token["price"],
            "exit_price": round(exit_price, 8),
            "amount_usd": round(amount, 2),
            "quantity": round(quantity, 8),
            "pnl_usd": round(pnl, 4),
        })
        trades.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": token["symbol"],
            "mode": "PAPER",
            "buy_usd": round(amount, 2),
            "entry_price": token["price"],
            "exit_price": round(exit_price, 8),
            "pnl_usd": round(pnl, 4),
            "real_transaction": False,
        })

    return cash, positions, trades


def manager(cash, positions, trades):
    """DJIWA LP MANAGER: membuat laporan kerja."""
    pnl = sum(item["pnl_usd"] for item in positions)
    report = {
        "project": PROJECT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "PAPER_TRADING_ONLY",
        "real_transactions_enabled": False,
        "initial_cash_usd": INITIAL_CASH,
        "ending_cash_usd": round(cash, 4),
        "total_pnl_usd": round(pnl, 4),
        "trade_count": len(trades),
        "workers": [
            "DJIWA LP SCOUT",
            "DJIWA LP GUARD",
            "DJIWA LP EXECUTOR",
            "DJIWA LP MANAGER",
        ],
        "positions": positions,
        "trades": trades,
        "notice": (
            "Data dan hasil harga adalah simulasi. "
            "Belum terhubung ke data live GMGN."
        ),
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = REPORTS / f"report_{stamp}.json"
    csv_path = REPORTS / f"trades_{stamp}.csv"

    json_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    with csv_path.open("w", newline="", encoding="utf-8") as file:
        fields = [
            "timestamp", "symbol", "mode", "buy_usd",
            "entry_price", "exit_price", "pnl_usd",
            "real_transaction",
        ]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(trades)

    print("\n=== DJIWA LP MANAGER ===")
    print(f"Modal awal     : ${INITIAL_CASH:.2f}")
    print(f"Saldo akhir    : ${cash:.2f}")
    print(f"Untung/rugi    : ${pnl:.2f}")
    print(f"Jumlah simulasi: {len(trades)}")
    print("Transaksi nyata: NONAKTIF")
    print(f"Laporan JSON   : {json_path}")
    print(f"Laporan CSV    : {csv_path}")


def main():
    print(f"=== {PROJECT} ===")
    print("MODE: SIMULASI — UANG ASLI TIDAK DIGUNAKAN")

    candidates = scout(DEMO_TOKENS)
    approved = guard(candidates)
    cash, positions, trades = execute_simulation(approved)
    manager(cash, positions, trades)


if __name__ == "__main__":
    main()
