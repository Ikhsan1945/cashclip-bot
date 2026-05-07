# 🤖 CashClip Bot - Panduan Setup

Bot Telegram "Watch to Earn" dengan Linkvertise + Supabase

---

## 📋 Persyaratan
- Python 3.10+
- Akun Telegram
- Akun Supabase (gratis): https://supabase.com
- Akun Linkvertise (gratis): https://linkvertise.com

---

## 🚀 Langkah Setup

### 1. Buat Bot Telegram
1. Buka Telegram → cari **@BotFather**
2. Ketik `/newbot`
3. Ikuti instruksi → salin **BOT_TOKEN**

### 2. Setup Supabase
1. Buka https://supabase.com → buat project baru
2. Pergi ke **SQL Editor** → **New Query**
3. Copy-paste isi file `schema.sql` → klik **Run**
4. Pergi ke **Settings → API**:
   - Salin **Project URL** → `SUPABASE_URL`
   - Salin **service_role key** → `SUPABASE_KEY`

### 3. Setup Linkvertise
1. Daftar di https://linkvertise.com
2. Pergi ke **My Links → Create Link**
3. Buat minimal 5 link (URL tujuan bisa apa saja, misal Google)
4. Salin setiap URL link → masukkan ke `AD_LINK_1` dst.
5. Salin **User ID** dari profil → `LINKVERTISE_USER_ID`

### 4. Install & Jalankan Bot
```bash
# Clone / download folder ini
cd cashclip-bot

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
nano .env  # isi semua nilai

# Jalankan bot
python bot.py
```

---

## 🖥️ Deploy ke Server (Rekomendasi)

### Opsi A: Railway.app (Gratis)
1. Push kode ke GitHub
2. Buka https://railway.app → New Project → Deploy from GitHub
3. Tambahkan Environment Variables dari `.env`
4. Deploy!

### Opsi B: VPS (DigitalOcean/Contabo)
```bash
# Di server Ubuntu
sudo apt update && sudo apt install python3 python3-pip -y
git clone <repo> && cd cashclip-bot
pip install -r requirements.txt
cp .env.example .env && nano .env

# Jalankan dengan screen agar tetap berjalan
screen -S bot
python bot.py
# Ctrl+A+D untuk detach
```

---

## 💰 Cara Kerja Monetisasi

```
User tonton iklan
    ↓
Bot kirim link Linkvertise
    ↓
User buka link → tampil iklan Linkvertise (Anda dapat revenue)
    ↓
User klik "Saya sudah menonton"
    ↓
Bot verifikasi (min 15 detik) → kredit Rp600-900 ke user
    ↓
User kumpulkan Rp50.000 → request withdraw
    ↓
Admin approve → transfer manual
```

**Revenue Linkvertise:** ~$1-3 per 1000 views (tergantung negara user)

---

## ⚙️ Perintah Admin
- `/approve <TX_ID>` - Approve penarikan dana user

---

## 📁 Struktur File
```
cashclip-bot/
├── bot.py          # Logic utama bot
├── database.py     # Koneksi Supabase
├── ads.py          # Sistem iklan Linkvertise
├── schema.sql      # Tabel database
├── requirements.txt
└── .env.example    # Template konfigurasi
```
