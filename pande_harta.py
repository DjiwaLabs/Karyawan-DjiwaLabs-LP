# pande_harta.py - Penjaga Harta & Web3 (Pande)
import os
import json
from solana.rpc.api import Client
from solders.keypair import Keypair

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
            import base58
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
            
        # Ambil saldo dalam Lamports (1 SOL = 1_000_000_000 Lamports)
        response = client.get_balance(wallet.pubkey())
        saldo_sol = response.value / 1_000_000_000
        return saldo_sol
    except Exception as e:
        print(f"Error cek saldo: {e}")
        return 0.0
