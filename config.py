# config.py - Buku Panduan & SOP Karyawan Digital DJIWA LP

# 1. SOP MODAL & ALOKASI
STARTING_CASH_USD = 10_000.0
ALLOCATION_PER_POOL_USD = 1_000.0 
MAX_OPEN_POSITIONS = 5

# 2. SOP SCANNER (Karyawan 1 - Siboru)
MAX_DISCOVERY_TOKENS = 40
ALLOWED_QUOTE_TOKENS = {"USDC", "USDT", "WETH", "WBNB", "SOL", "DAI", "BUSD"}

# 3. SOP VALIDATOR (Karyawan 2 - Parhata)
MIN_LIQUIDITY_USD = 50_000.0      
MIN_VOLUME_24H_USD = 50_000.0     
MIN_TXNS_24H = 200
MIN_POOL_AGE_HOURS = 24.0         
MAX_POOL_AGE_DAYS = 180           

# 4. SOP EKSEKUTOR DISIPLIN (Karyawan 3 - Raja)
SIMULATED_POOL_FEE_RATE = 0.003   
SIMULATED_GAS_USD = 1.5           
SIMULATED_SLIPPAGE = 0.005        
TAKE_PROFIT_PCT = 0.50            # Ambil untung jika naik 50%
STOP_LOSS_PRICE_PCT = 0.35        # Cut loss jika harga turun 35%
STOP_LOSS_LIQ_PCT = 0.40          # Cut loss jika likuiditas turun 40%
MAX_HOLD_DAYS = 7                 # Keluar paksa jika sudah 7 hari

# 5. SOP REPORTER (Karyawan 4 - Panongani)
MAX_EVENTS_KEPT = 100
