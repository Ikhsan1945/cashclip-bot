import logging, os, json, asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from database import Database
from ads import AdsManager

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

db = Database()
ads = AdsManager()

BOT_TOKEN  = os.getenv("BOT_TOKEN")
ADMIN_ID   = int(os.getenv("ADMIN_ID", "0"))
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://YOUR_GITHUB_PAGES.github.io/cashclip/webapp/ad.html")

def main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("▶️ Tonton Iklan")],
        [KeyboardButton("💰 Saldo"), KeyboardButton("👥 Mitra")],
        [KeyboardButton("🎁 Bonus"), KeyboardButton("⚙️ Lainnya")],
    ], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    result = await db.register_user(telegram_id=user.id, username=user.username or user.first_name, referral_code=args[0] if args else None)
    if result["is_new"]:
        bonus_text = f"\n🎁 Bonus referral <b>Rp{result['referral_bonus']:,}</b>!" if result.get("referral_bonus") else ""
        await update.message.reply_text(
            f"👋 Selamat datang, <b>{user.first_name}</b>!\n\n💸 Hasilkan uang nyata dengan menonton iklan!\n📺 Tarif: <b>Rp600 - Rp900</b> per iklan\n💳 Min. penarikan: <b>Rp50.000</b>{bonus_text}\n\nTekan tombol di bawah untuk mulai 👇",
            parse_mode="HTML", reply_markup=main_keyboard()
        )
    else:
        await update.message.reply_text(f"👋 Selamat datang kembali, <b>{user.first_name}</b>!", parse_mode="HTML", reply_markup=main_keyboard())

async def tonton_iklan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Silakan /start terlebih dahulu.")
        return
    last_watch = user.get("last_watch_at")
    if last_watch:
        last_dt = datetime.fromisoformat(last_watch)
        cooldown = timedelta(seconds=30)
        if datetime.utcnow() - last_dt < cooldown:
            remaining = int((cooldown - (datetime.utcnow() - last_dt)).total_seconds())
            await update.message.reply_text(f"⏳ Tunggu <b>{remaining}</b> detik lagi.", parse_mode="HTML")
            return
    ad_data = await ads.generate_ad_link(user_id)
    token = ad_data["token"]
    rate  = ad_data["rate"]
    webapp_url = f"{WEBAPP_URL}?token={token}&rate={rate}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("👁 Tonton Iklan Sekarang", web_app=WebAppInfo(url=webapp_url))]])
    await update.message.reply_text(
        f"📺 <b>Iklan tersedia!</b>\n\n📊 Kurs pembayaran saat ini: <b>Rp{rate:,}</b> per 1 iklan\n\nKlik tombol di bawah ini untuk melanjutkan ke tayangan iklan 👇",
        parse_mode="HTML", reply_markup=keyboard
    )

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    raw = update.effective_message.web_app_data.data
    try:
        payload = json.loads(raw)
        token = payload.get("token")
    except Exception:
        return
    result = await ads.verify_and_credit(user_id, token)
    if result["success"]:
        earned = result["amount"]
        new_balance = result["new_balance"]
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("👁 Lanjutkan tonton iklan", callback_data="next_ad")]])
        await update.message.reply_text(
            f"✅ <b>Anda telah menghasilkan Rp{earned:,} dari menonton iklan</b>\n\n💰 Saldo: <b>Rp{new_balance:,}</b>",
            parse_mode="HTML", reply_markup=keyboard
        )
    elif result["reason"] == "too_fast":
        await update.message.reply_text(f"⚠️ Tonton minimal <b>{result['min_seconds']}</b> detik!", parse_mode="HTML")
    elif result["reason"] == "already_used":
        await update.message.reply_text("❌ Iklan ini sudah diklaim.")
    else:
        await update.message.reply_text("❌ Verifikasi gagal.")

async def cek_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Silakan /start terlebih dahulu.")
        return
    stats = await db.get_user_stats(user_id)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("💸 Tarik Dana", callback_data="withdraw"), InlineKeyboardButton("📊 Riwayat", callback_data="history")]])
    await update.message.reply_text(
        f"💰 <b>Saldo Anda</b>\n\n├ Saldo aktif: <b>Rp{user['balance']:,}</b>\n├ Total earned: <b>Rp{user['total_earned']:,}</b>\n├ Iklan ditonton: <b>{stats['total_watches']} iklan</b>\n└ Referral: <b>{stats['referral_count']} orang</b>\n\n💳 Min. penarikan: <b>Rp50.000</b>",
        parse_mode="HTML", reply_markup=keyboard
    )

async def withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = await db.get_user(query.from_user.id)
    if user["balance"] < 50000:
        await query.edit_message_text(f"❌ Saldo tidak cukup!\n\nSaldo: <b>Rp{user['balance']:,}</b>\nMin: <b>Rp50.000</b>", parse_mode="HTML")
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("DANA", callback_data="wd_method:dana"), InlineKeyboardButton("OVO", callback_data="wd_method:ovo")],
        [InlineKeyboardButton("GoPay", callback_data="wd_method:gopay"), InlineKeyboardButton("Bank Transfer", callback_data="wd_method:bank")],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel")]
    ])
    await query.edit_message_text(f"💸 <b>Penarikan Dana</b>\n\nSaldo: <b>Rp{user['balance']:,}</b>\n\nPilih metode:", parse_mode="HTML", reply_markup=keyboard)

async def withdraw_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split(":")[1]
    context.user_data["wd_method"] = method
    context.user_data["waiting_for"] = "wd_account"
    names = {"dana": "DANA", "ovo": "OVO", "gopay": "GoPay", "bank": "Rekening Bank"}
    await query.edit_message_text(f"✅ Metode: <b>{names[method]}</b>\n\nMasukkan nomor {names[method]}:", parse_mode="HTML")

async def mitra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    stats = await db.get_user_stats(user_id)
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user['referral_code']}"
    await update.message.reply_text(
        f"👥 <b>Program Mitra</b>\n\n├ Referral: <b>{stats['referral_count']} orang</b>\n├ Komisi: <b>Rp{stats['referral_earned']:,}</b>\n└ Bonus/referral: <b>Rp2.000</b>\n\n🔗 Link Anda:\n<code>{ref_link}</code>",
        parse_mode="HTML"
    )

async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = await db.claim_daily_bonus(update.effective_user.id)
    if result["success"]:
        await update.message.reply_text(f"🎁 <b>Bonus harian diklaim!</b>\n\n💰 Dapat: <b>Rp{result['amount']:,}</b>\n🔥 Streak: <b>{result['streak']} hari</b>\n💳 Saldo: <b>Rp{result['new_balance']:,}</b>", parse_mode="HTML")
    else:
        await update.message.reply_text("⏳ Bonus harian sudah diklaim! Kembali besok 00.00 WIB.")

async def lainnya(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    await update.message.reply_text(f"⚙️ <b>Info Akun</b>\n\n🆔 ID: <code>{user_id}</code>\n👤 Username: @{update.effective_user.username or '-'}\n📅 Bergabung: {user['created_at'][:10]}", parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    waiting = context.user_data.get("waiting_for")
    if waiting == "wd_account":
        account = text.strip()
        method = context.user_data.get("wd_method")
        user = await db.get_user(user_id)
        amount = user["balance"]
        result = await db.create_withdrawal(user_id, amount, method, account)
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text(
            f"✅ <b>Permintaan penarikan dikirim!</b>\n\n├ Metode: <b>{method.upper()}</b>\n├ Nomor: <b>{account}</b>\n├ Jumlah: <b>Rp{amount:,}</b>\n└ Status: <b>⏳ Diproses 1x24 jam</b>\n\nID Transaksi: <code>{result['id']}</code>",
            parse_mode="HTML", reply_markup=main_keyboard()
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 <b>Withdrawal Baru!</b>\nUser: {user_id} (@{update.effective_user.username})\nMetode: {method.upper()}\nNomor: {account}\nJumlah: Rp{amount:,}\nTX: {result['id']}", parse_mode="HTML")
        return
    routing = {"▶️ Tonton Iklan": tonton_iklan, "💰 Saldo": cek_saldo, "👥 Mitra": mitra, "🎁 Bonus": bonus, "⚙️ Lainnya": lainnya}
    if text in routing:
        await routing[text](update, context)

async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: await update.message.reply_text("Usage: /approve <TX_ID>"); return
    result = await db.approve_withdrawal(context.args[0])
    if result["success"]:
        await update.message.reply_text(f"✅ Approved {context.args[0]}")
        await context.bot.send_message(chat_id=result["user_id"], text=f"✅ <b>Penarikan Berhasil!</b>\nRp{result['amount']:,} telah dikirim!", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ TX tidak ditemukan.")

async def reject_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: return
    result = await db.reject_withdrawal(context.args[0])
    if result["success"]:
        await update.message.reply_text(f"❌ Rejected {context.args[0]}. Saldo dikembalikan.")
        await context.bot.send_message(chat_id=result["user_id"], text=f"❌ <b>Penarikan Ditolak</b>\nRp{result['amount']:,} dikembalikan ke saldo.", parse_mode="HTML")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    stats = await db.get_global_stats()
    await update.message.reply_text(
        f"📊 <b>Statistik Bot</b>\n\n👥 Total user: <b>{stats['total_users']}</b>\n📺 Total iklan: <b>{stats['total_watches']}</b>\n💰 Total dibayar: <b>Rp{stats['total_paid']:,}</b>\n⏳ Pending WD: <b>{stats['pending_wd']}</b>",
        parse_mode="HTML"
    )

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args: await update.message.reply_text("Usage: /broadcast <pesan>"); return
    msg = ' '.join(context.args)
    users = await db.get_all_user_ids()
    sent = 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text=msg, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await update.message.reply_text(f"📢 Terkirim ke {sent}/{len(users)} user.")

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == "withdraw": await withdraw_callback(update, context)
    elif data.startswith("wd_method:"): await withdraw_method_callback(update, context)
    elif data == "cancel": await update.callback_query.edit_message_text("❌ Dibatalkan.")
    elif data == "history": await history_callback(update, context)
    elif data == "next_ad":
        await update.callback_query.answer()
        await tonton_iklan(update, context)

async def history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    history = await db.get_history(query.from_user.id, limit=10)
    if not history:
        await query.edit_message_text("📭 Belum ada riwayat.")
        return
    text = "📊 <b>Riwayat (10 terakhir)</b>\n\n"
    icons = {"ad": "📺", "bonus": "🎁", "referral": "👥", "withdrawal": "💸"}
    for h in history:
        text += f"{icons.get(h['type'],'•')} {h['description']} | <b>Rp{h['amount']:,}</b> | {h['created_at'][:10]}\n"
    await query.edit_message_text(text, parse_mode="HTML")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve", approve_cmd))
    app.add_handler(CommandHandler("reject", reject_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🤖 CashClip Bot + Mini App berjalan!")
    app.run_polling()

if __name__ == "__main__":
    main()
