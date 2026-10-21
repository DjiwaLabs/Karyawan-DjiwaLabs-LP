import os
import time
import requests
import json
import google.generativeai as genai

# Ambil API Key dari Secret GitHub secara aman
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("❌ Error: GEMINI_API_KEY tidak ditemukan di environment variables!")
    exit(1)

# Konfigurasi Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Parameter Target Token (Contoh: Wrapped SOL di Solana)
TOKEN_ADDRESS = "So11111111111111111111111111111111111111112"
CHAIN = "sol"
MODAL_AWAL_USD = 1000.0

def get_gmgn_data(token_address, chain):
    """Mengambil data harga real-time dari GMGN.ai"""
    url = f"https://gmgn.ai/defi/quotation/v1/tokens/{chain}/{token_address}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            res_data = response.json().get('data', {})
            token_info = res_data.get('token', {})
            return {
                "symbol": token_info.get('symbol', 'SOL'),
                "price": float(token_info.get('price', 0))
            }
        else:
            print(f"⚠️ Gagal akses GMGN. Status: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error koneksi GMGN: {e}")
        return None

def ask_ai_agent(current_price, symbol):
    """Meminta analisis dan keputusan dari Otak AI Gemini"""
    prompt = f"""
    Kamu adalah Karyawan Digital profesional sebagai Liquidity Provider (LP) Manager.
    Token yang dipantau: {symbol}
    Harga terkini di pasaran: ${current_price}
    
    Tugasmu: Berikan analisis singkat apakah saat ini kondisi pasar stabil untuk posisi LP, dan berikan keputusan dengan format JSON:
    {{
        "action": "HOLD" atau "REBALANCE",
        "reason": "Penjelasan singkat logis dalam 1-2 kalimat"
    }}
    Berikan output FORMAT JSON SAJA tanpa teks tambahan di luar markdown.
    """
    
    try:
        response = model.generate_content(prompt)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        print(f"⚠️ Gagal mendapatkan respons dari Gemini AI: {e}")
        return {"action": "HOLD", "reason": "Error parsing AI response, defaulting to HOLD."}

if __name__ == "__main__":
    print("🚀 [Karyawan Digital LP]: Memulai pemeriksaan rutin pasar...")
    
    # 1. Ambil data harga dari GMGN
    market_data = get_gmgn_data(TOKEN_ADDRESS, CHAIN)
    
    if market_data and market_data['price'] > 0:
        symbol = market_data['symbol']
        price = market_data['price']
        print(f"📡 Data GMGN Berhasil Diambil -> Token: {symbol} | Harga: ${price}")
        
        # 2. Konsultasi ke Otak AI
        decision = ask_ai_agent(price, symbol)
        
        print("\n" + "="*40)
        print(f"🤖 KEPUTUSAN KARYAWAN DIGITAL:")
        print(f"   ► Aksi Dipilih : {decision.get('action')}")
        print(f"   ► Alasan Analisis: {decision.get('reason')}")
        print("="*40)
    else:
        print("❌ Gagal mendapatkan harga valid dari GMGN.")
