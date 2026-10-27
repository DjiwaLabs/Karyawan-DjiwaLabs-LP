# pande_harta.py - Penjaga Harta & Web3 (Pande)
import os
import json
import requests
import base64
from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.message import Message
from solders.transaction import VersionedTransaction
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction
import base58

def get_client():
    rpc_url = os.environ.get("SOLANA_RPC_URL")
    if not rpc_url:
        raise ValueError("SOLANA_RPC_URL tidak ditemukan di environment!")
    return Client(rpc_url)

def get_wallet():
    private_key_str = os.environ.get("SOLANA_PRIVATE_KEY")
    if not private_key_str:
        raise ValueError("SOLANA_PRIVATE_KEY tidak ditemukan!")
    
    try:
        if private_key_str.startswith('['):
            secret_key = bytes(json.loads(private_key_str))
        else:
            secret_key = base58.b58decode(private_key_str)
            
        return Keypair.from_bytes(secret_key)
    except Exception as e:
        print(f"Gagal membaca Private Key: {e}")
        return None

def cek_saldo():
    try:
        client = get_client()
        wallet = get_wallet()
        if not wallet:
            return 0.0
            
        response = client.get_balance(wallet.pubkey())
        saldo_sol = response.value / 1_000_000_000
        return saldo_sol
    except Exception as e:
        print(f"Error cek saldo: {e}")
        return 0.0

def kirim_sol(tujuan_address_str, jumlah_sol):
    try:
        client = get_client()
        wallet = get_wallet()
        if not wallet:
            return False, "Wallet tidak ditemukan"

        tujuan_pubkey = Pubkey.from_string(tujuan_address_str)
        lamports = int(jumlah_sol * 1_000_000_000)

        transfer_ix = transfer(
            TransferParams(
                from_pubkey=wallet.pubkey(),
                to_pubkey=tujuan_pubkey,
                lamports=lamports
            )
        )

        recent_blockhash = client.get_latest_blockhash().value.blockhash
        msg = Message.new_with_blockhash([transfer_ix], wallet.pubkey(), recent_blockhash)
        txn = Transaction([wallet], msg, recent_blockhash)

        print(f"Mengirim {jumlah_sol} SOL ke {tujuan_address_str}...")
        response = client.send_transaction(txn)
        return True, str(response.value)

    except Exception as e:
        return False, str(e)

def swap_token(jumlah_sol, target_mint_address, slippage_bps=50):
    """
    Fungsi untuk menukar SOL menjadi token lain menggunakan Jupiter API (Devnet).
    """
    client = get_client()
    wallet = get_wallet()
    if not wallet: return False, "Wallet tidak ditemukan"

    # 1. Dapatkan Quote (Harga & Rute) - Jupiter API
    # Input mint untuk SOL (Wrapped SOL): So11111111111111111111111111111111111111112
    quote_url = f"https://quote-api.jup.ag/v6/quote?inputMint=So11111111111111111111111111111111111111112&outputMint={target_mint_address}&amount={int(jumlah_sol * 1_000_000_000)}&slippageBps={slippage_bps}"
    
    try:
        print("Meminta Quote dari Jupiter...")
        quote_res = requests.get(quote_url).json()
        if "error" in quote_res:
            return False, f"Jupiter Error: {quote_res['error']}"
            
        # 2. Buat Transaksi (Swap)
        swap_url = "https://quote-api.jup.ag/v6/swap"
        swap_payload = {
            "quoteResponse": quote_res,
            "userPublicKey": str(wallet.pubkey()),
            "wrapAndUnwrapSol": True
        }
        
        print("Meminta Transaksi dari Jupiter...")
        swap_res = requests.post(swap_url, json=swap_payload).json()
        
        if "error" in swap_res:
            return False, f"Jupiter Swap Error: {swap_res['error']}"
            
        # Transaksi dari Jupiter dikirim dalam bentuk base64 string
        tx_base64 = swap_res["swapTransaction"]
        tx_bytes = base64.b64decode(tx_base64)
        
        # 3. Tanda tangani dan Kirim
        from solders.transaction import VersionedTransaction
        txn = VersionedTransaction.from_bytes(tx_bytes)
        
        # Tanda tangani transaksi
        signed_txn = wallet.sign_message(txn.message)
        final_txn = VersionedTransaction(txn.message, [signed_txn])
        
        print("Mengirim transaksi Swap ke jaringan...")
        response = client.send_transaction(final_txn)
        tx_hash = response.value
        
        # 4. Konfirmasi Transaksi (Menunggu Validasi)
        print("Menunggu konfirmasi (maksimal 30 detik)...")
        client.confirm_transaction(tx_hash, commitment="confirmed")
        
        return True, str(tx_hash)

    except Exception as e:
        return False, f"Error Swap: {e}"
