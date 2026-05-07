import os
import uuid
import random
import string
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
REFERRAL_BONUS = 2000
DAILY_BONUS_BASE = 1000

class Database:
    def __init__(self):
        self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    def _gen_referral_code(self) -> str:
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    # ─── User ───────────────────────────────────────────────────────────────

    async def register_user(self, telegram_id: int, username: str, referral_code: str = None) -> dict:
        existing = self.client.table("users").select("*").eq("telegram_id", telegram_id).execute()

        if existing.data:
            return {"is_new": False, "user": existing.data[0]}

        # Cek referral
        referrer_id = None
        if referral_code:
            ref_user = self.client.table("users").select("*").eq("referral_code", referral_code).execute()
            if ref_user.data:
                referrer_id = ref_user.data[0]["telegram_id"]

        my_code = self._gen_referral_code()
        new_user = {
            "telegram_id": telegram_id,
            "username": username,
            "balance": 0,
            "total_earned": 0,
            "referral_code": my_code,
            "referred_by": referrer_id,
            "last_watch_at": None,
            "daily_streak": 0,
            "last_daily_at": None,
            "created_at": datetime.utcnow().isoformat()
        }
        self.client.table("users").insert(new_user).execute()

        referral_bonus = 0
        if referrer_id:
            # Beri bonus ke referrer
            self.client.rpc("increment_balance", {
                "p_user_id": referrer_id,
                "p_amount": REFERRAL_BONUS
            }).execute()
            # Catat transaksi referral
            self.client.table("transactions").insert({
                "id": str(uuid.uuid4()),
                "user_id": referrer_id,
                "type": "referral",
                "amount": REFERRAL_BONUS,
                "description": f"Bonus referral dari @{username}",
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            referral_bonus = REFERRAL_BONUS

        return {"is_new": True, "referral_bonus": referral_bonus}

    async def get_user(self, telegram_id: int) -> dict | None:
        res = self.client.table("users").select("*").eq("telegram_id", telegram_id).execute()
        return res.data[0] if res.data else None

    async def get_user_stats(self, telegram_id: int) -> dict:
        watches = self.client.table("transactions") \
            .select("id", count="exact") \
            .eq("user_id", telegram_id) \
            .eq("type", "ad") \
            .execute()

        referrals = self.client.table("users") \
            .select("id", count="exact") \
            .eq("referred_by", telegram_id) \
            .execute()

        ref_earned = self.client.table("transactions") \
            .select("amount") \
            .eq("user_id", telegram_id) \
            .eq("type", "referral") \
            .execute()

        total_ref_earned = sum(r["amount"] for r in ref_earned.data) if ref_earned.data else 0

        return {
            "total_watches": watches.count or 0,
            "referral_count": referrals.count or 0,
            "referral_earned": total_ref_earned
        }

    # ─── Iklan ──────────────────────────────────────────────────────────────

    async def record_ad_watch(self, telegram_id: int, amount: int, token: str):
        # Update last_watch_at
        self.client.table("users").update({
            "last_watch_at": datetime.utcnow().isoformat()
        }).eq("telegram_id", telegram_id).execute()

        # Tambah balance
        self.client.rpc("increment_balance", {
            "p_user_id": telegram_id,
            "p_amount": amount
        }).execute()

        # Catat transaksi
        self.client.table("transactions").insert({
            "id": str(uuid.uuid4()),
            "user_id": telegram_id,
            "type": "ad",
            "amount": amount,
            "description": "Tonton iklan",
            "token": token,
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        user = await self.get_user(telegram_id)
        return user["balance"]

    async def is_token_used(self, token: str) -> bool:
        res = self.client.table("transactions").select("id").eq("token", token).execute()
        return bool(res.data)

    # ─── Bonus Harian ────────────────────────────────────────────────────────

    async def claim_daily_bonus(self, telegram_id: int) -> dict:
        user = await self.get_user(telegram_id)
        now = datetime.utcnow()

        last_daily = user.get("last_daily_at")
        if last_daily:
            last_dt = datetime.fromisoformat(last_daily)
            # Cek apakah sudah lewat hari ini (UTC)
            if last_dt.date() >= now.date():
                return {"success": False}

            # Cek streak
            streak = user.get("daily_streak", 0)
            if (now.date() - last_dt.date()).days == 1:
                streak += 1
            else:
                streak = 1
        else:
            streak = 1

        # Bonus naik seiring streak (max 5000)
        amount = min(DAILY_BONUS_BASE + (streak - 1) * 200, 5000)

        self.client.table("users").update({
            "last_daily_at": now.isoformat(),
            "daily_streak": streak
        }).eq("telegram_id", telegram_id).execute()

        self.client.rpc("increment_balance", {
            "p_user_id": telegram_id,
            "p_amount": amount
        }).execute()

        self.client.table("transactions").insert({
            "id": str(uuid.uuid4()),
            "user_id": telegram_id,
            "type": "bonus",
            "amount": amount,
            "description": f"Bonus harian (streak {streak} hari)",
            "created_at": now.isoformat()
        }).execute()

        user = await self.get_user(telegram_id)
        return {"success": True, "amount": amount, "streak": streak, "new_balance": user["balance"]}

    # ─── Withdrawal ──────────────────────────────────────────────────────────

    async def create_withdrawal(self, telegram_id: int, amount: int, method: str, account: str) -> dict:
        tx_id = str(uuid.uuid4())[:8].upper()

        # Kurangi balance
        self.client.rpc("decrement_balance", {
            "p_user_id": telegram_id,
            "p_amount": amount
        }).execute()

        self.client.table("withdrawals").insert({
            "id": tx_id,
            "user_id": telegram_id,
            "amount": amount,
            "method": method,
            "account": account,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        return {"id": tx_id}

    async def approve_withdrawal(self, tx_id: str) -> dict:
        res = self.client.table("withdrawals").select("*").eq("id", tx_id).execute()
        if not res.data:
            return {"success": False}

        wd = res.data[0]
        self.client.table("withdrawals").update({
            "status": "approved",
            "approved_at": datetime.utcnow().isoformat()
        }).eq("id", tx_id).execute()

        return {"success": True, "user_id": wd["user_id"], "amount": wd["amount"]}

    # ─── History ─────────────────────────────────────────────────────────────

    async def get_history(self, telegram_id: int, limit: int = 10) -> list:
        res = self.client.table("transactions") \
            .select("*") \
            .eq("user_id", telegram_id) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()
        return res.data or []

    async def reject_withdrawal(self, tx_id: str) -> dict:
        res = self.client.table("withdrawals").select("*").eq("id", tx_id).execute()
        if not res.data:
            return {"success": False}
        wd = res.data[0]
        self.client.table("withdrawals").update({"status": "rejected"}).eq("id", tx_id).execute()
        # Kembalikan saldo
        self.client.rpc("increment_balance", {"p_user_id": wd["user_id"], "p_amount": wd["amount"]}).execute()
        return {"success": True, "user_id": wd["user_id"], "amount": wd["amount"]}

    async def get_global_stats(self) -> dict:
        users = self.client.table("users").select("id", count="exact").execute()
        watches = self.client.table("transactions").select("id", count="exact").eq("type", "ad").execute()
        paid = self.client.table("withdrawals").select("amount").eq("status", "approved").execute()
        pending = self.client.table("withdrawals").select("id", count="exact").eq("status", "pending").execute()
        total_paid = sum(r["amount"] for r in paid.data) if paid.data else 0
        return {
            "total_users": users.count or 0,
            "total_watches": watches.count or 0,
            "total_paid": total_paid,
            "pending_wd": pending.count or 0
        }

    async def get_all_user_ids(self) -> list:
        res = self.client.table("users").select("telegram_id").execute()
        return [r["telegram_id"] for r in res.data] if res.data else []
