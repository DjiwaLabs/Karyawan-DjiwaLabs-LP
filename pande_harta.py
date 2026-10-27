# pande_harta.py - Penjaga Harta & Web3 (Pande)
import os
import json
from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from solders.system_program import TransferParams, transfer
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
    """
    Fungsi untuk mengirim SOL ke alamat lain (menggunakan solders).
    """
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

        # Menggunakan Transaction dari solders
        txn = Transaction().add(transfer_ix)

        recent_blockhash = client.get_latest_blockhash().value.blockhash
        txn.recent_blockhash = recent_blockhash
        txn.fee_payer = wallet.pubkey()

        txn.sign(wallet)

        print(f"Mengirim {jumlah_sol} SOL ke {tujuan_address_str}...")
        response = client.send_transaction(txn)
        
        tx_hash = response.value
        print(f"SUKSES! Hash Transaksi: {tx_hash}")
        return True, str(tx_hash)

    except Exception as e:
        print(f"Gagal mengirim SOL: {e}")
        return False, str(e)
