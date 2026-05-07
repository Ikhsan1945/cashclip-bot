-- ============================================================
-- JALANKAN SEMUA SQL INI DI SUPABASE SQL EDITOR
-- Dashboard Supabase → SQL Editor → New Query → Paste → Run
-- ============================================================

-- Tabel Users
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    balance INTEGER DEFAULT 0,
    total_earned INTEGER DEFAULT 0,
    referral_code TEXT UNIQUE,
    referred_by BIGINT REFERENCES users(telegram_id),
    last_watch_at TIMESTAMPTZ,
    daily_streak INTEGER DEFAULT 0,
    last_daily_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabel Transactions
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(telegram_id),
    type TEXT NOT NULL CHECK (type IN ('ad', 'bonus', 'referral', 'withdrawal')),
    amount INTEGER NOT NULL,
    description TEXT,
    token TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabel Withdrawals
CREATE TABLE IF NOT EXISTS withdrawals (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(telegram_id),
    amount INTEGER NOT NULL,
    method TEXT NOT NULL,
    account TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    approved_at TIMESTAMPTZ
);

-- Index untuk performa
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_withdrawals_user_id ON withdrawals(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_token ON transactions(token);

-- ============================================================
-- RPC Functions (wajib dibuat)
-- ============================================================

-- Fungsi increment balance (atomic)
CREATE OR REPLACE FUNCTION increment_balance(p_user_id BIGINT, p_amount INTEGER)
RETURNS VOID AS $$
BEGIN
    UPDATE users
    SET balance = balance + p_amount,
        total_earned = total_earned + p_amount
    WHERE telegram_id = p_user_id;
END;
$$ LANGUAGE plpgsql;

-- Fungsi decrement balance (atomic)
CREATE OR REPLACE FUNCTION decrement_balance(p_user_id BIGINT, p_amount INTEGER)
RETURNS VOID AS $$
BEGIN
    UPDATE users
    SET balance = balance - p_amount
    WHERE telegram_id = p_user_id
    AND balance >= p_amount;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- Row Level Security (Opsional tapi disarankan)
-- ============================================================
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE withdrawals ENABLE ROW LEVEL SECURITY;

-- Izinkan service role (server bot) akses penuh
CREATE POLICY "Service role full access on users" ON users
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access on transactions" ON transactions
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access on withdrawals" ON withdrawals
    FOR ALL USING (true) WITH CHECK (true);
