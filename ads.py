import os
import uuid
import random
import hashlib
from datetime import datetime
from database import Database

# ─── Konfigurasi ─────────────────────────────────────────────────────────────
LINKVERTISE_USER_ID = os.getenv("LINKVERTISE_USER_ID", "")  # ID akun Linkvertise Anda
MIN_WATCH_SECONDS = 15   # Minimum detik sebelum bisa klaim
AD_RATE_MIN = 600
AD_RATE_MAX = 900

# Pool URL iklan (isi dengan URL Linkvertise buatan Anda)
# Cara: Login linkvertise.com → Create Link → masukkan URL tujuan
# Ganti list ini dengan link Linkvertise Anda yang sudah dibuat
AD_LINKS = [
    os.getenv("AD_LINK_1", "https://linkvertise.com/YOUR_ID/ad1"),
    os.getenv("AD_LINK_2", "https://linkvertise.com/YOUR_ID/ad2"),
    os.getenv("AD_LINK_3", "https://linkvertise.com/YOUR_ID/ad3"),
    os.getenv("AD_LINK_4", "https://linkvertise.com/YOUR_ID/ad4"),
    os.getenv("AD_LINK_5", "https://linkvertise.com/YOUR_ID/ad5"),
]

# Simpan token pending di memory (untuk production: gunakan Redis)
pending_tokens: dict = {}
# Format: { token: { "user_id": int, "rate": int, "created_at": datetime } }

db = Database()

class AdsManager:
    def generate_token(self, user_id: int) -> str:
        raw = f"{user_id}-{uuid.uuid4()}-{datetime.utcnow().timestamp()}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    async def generate_ad_link(self, user_id: int) -> dict:
        rate = random.randint(AD_RATE_MIN, AD_RATE_MAX)
        token = self.generate_token(user_id)
        link = random.choice(AD_LINKS)

        # Simpan token
        pending_tokens[token] = {
            "user_id": user_id,
            "rate": rate,
            "created_at": datetime.utcnow(),
            "link": link
        }

        return {"token": token, "rate": rate, "link": link}

    async def verify_and_credit(self, user_id: int, token: str) -> dict:
        # Cek token ada di pending
        if token not in pending_tokens:
            return {"success": False, "reason": "invalid_token"}

        data = pending_tokens[token]

        # Cek token milik user yang benar
        if data["user_id"] != user_id:
            return {"success": False, "reason": "invalid_token"}

        # Cek sudah digunakan di DB
        if await db.is_token_used(token):
            return {"success": False, "reason": "already_used"}

        # Cek waktu minimum (15 detik)
        elapsed = (datetime.utcnow() - data["created_at"]).total_seconds()
        if elapsed < MIN_WATCH_SECONDS:
            return {
                "success": False,
                "reason": "too_fast",
                "min_seconds": MIN_WATCH_SECONDS
            }

        # Kredit ke user
        amount = data["rate"]
        new_balance = await db.record_ad_watch(user_id, amount, token)

        # Hapus dari pending
        del pending_tokens[token]

        return {"success": True, "amount": amount, "new_balance": new_balance}
