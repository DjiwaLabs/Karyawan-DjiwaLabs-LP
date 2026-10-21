
# DJIWA Liquidity Provider

Sistem eksperimen empat karyawan digital untuk pemantauan token,
analisis risiko, paper trading, dan pelaporan.

## Empat karyawan digital

1. DJIWA LP SCOUT — mengumpulkan kandidat token.
2. DJIWA LP GUARD — menyaring kandidat berdasarkan aturan risiko.
3. DJIWA LP EXECUTOR — menjalankan simulasi transaksi.
4. DJIWA LP MANAGER — menyusun laporan hasil kerja.

## Status versi

- [x] Struktur empat karyawan
- [x] Paper trading berbasis data demo
- [x] Laporan JSON dan CSV
- [x] GitHub Actions untuk menjalankan simulasi
- [ ] Integrasi data live GMGN
- [ ] Pemantauan pool LP live
- [ ] Simulator penyetoran dan penarikan likuiditas
- [ ] Dashboard kinerja

## Menjalankan simulasi

Gunakan Python 3.12 atau versi kompatibel.

```bash
python main.py
```

Modal simulasi default adalah USD 1.000.

Untuk mengganti modal simulasi:

PowerShell:
```powershell
$env:SIMULATION_CASH="5000"
python main.py
```

## Laporan

Program menghasilkan:
- `reports/report_*.json`
- `reports/trades_*.csv`

File tersebut berisi hasil simulasi, bukan bukti transaksi blockchain.

## Keamanan

- Transaksi nyata dinonaktifkan.
- Jangan masukkan private key dompet ke repositori.
- Simpan kredensial API menggunakan GitHub Actions Secrets.
- Data demo tidak boleh dianggap sebagai harga pasar live.

## Integrasi GMGN

Integrasi belum aktif. Sebelum mengaktifkannya, periksa dokumentasi resmi
GMGN Agent API dan konfirmasikan endpoint, jaringan, autentikasi,
batas permintaan, serta izin yang tersedia.

Dokumentasi: https://docs.gmgn.ai/index/gmgn-agent-api
