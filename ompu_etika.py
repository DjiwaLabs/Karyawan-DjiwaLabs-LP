# ompu_etika.py - Penjaga Etika & Keamanan (Ompu)
import re

def sanitasi_error(pesan_error):
    """
    Menerjemahkan error mentah dari Blockchain/Python menjadi pesan manusiawi.
    """
    err = str(pesan_error)
    
    # Sembunyikan API Key RPC jika tidak sengaja tercetak
    err = re.sub(r'api-key=[a-zA-Z0-9\-]+', 'api-key=***', err)
    
    if "InsufficientFundsForRent" in err or "insufficient funds" in err.lower():
        return "Saldo SOL tidak cukup untuk biaya sewa akun token."
    elif "SlippageToleranceExceeded" in err or "slippage" in err.lower():
        return "Harga berubah terlalu cepat (Slippage). Transaksi dibatalkan demi keamanan."
    elif "BlockhashNotFound" in err:
        return "Jaringan Solana sedang sibuk. Transaksi kadaluarsa."
    elif "Transaction simulation failed" in err:
        return "Simulasi transaksi gagal. Periksa kembali parameter atau saldo."
    elif "HTTP Error 429" in err:
        return "Batas permintaan RPC tercapai. Bot butuh istirahat sejenak."
    else:
        return f"Error tidak dikenal: {err[:150]}..."

def validasi_transaksi(saldo_sekarang, jumlah_diminta, batas_maksimal):
    """
    Memastikan saldo cukup dan tidak melebihi batas maksimal.
    """
    if jumlah_diminta <= 0:
        return False, "Jumlah transaksi harus lebih dari 0."
    if saldo_sekarang < (jumlah_diminta + 0.005): # Sisakan 0.005 SOL untuk gas
        return False, f"Saldo kurang. Saldo saat ini: {saldo_sekarang:.4f} SOL, dibutuhkan: {jumlah_diminta + 0.005:.4f} SOL."
    if jumlah_diminta > batas_maksimal:
        return False, f"Jumlah {jumlah_diminta} SOL melebihi batas aman per transaksi ({batas_maksimal} SOL)."
    return True, "Validasi sukses."
