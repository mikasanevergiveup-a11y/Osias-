import asyncio
import logging
import os
import psycopg2
import requests
import threading
import time
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# Logging သတ်မှတ်ခြင်း
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Environment Variables များ
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

# Admin IDs များကို ယူခြင်း
ADMIN_IDS = [
    int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()
]


# ==========================================
# DATABASE SYSTEM
# ==========================================
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                first_name VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        logger.info("✅ Database initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database error: {e}")

def save_user(user_id, username, first_name):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (user_id, username, first_name) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO NOTHING;",
            (user_id, username, first_name),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving user: {e}")

def get_users_count():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users;")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Error getting user count: {e}")
        return 0


# ==========================================
# FLASK WEB SERVER (Render Port အတွက်)
# ==========================================
web_app = Flask(__name__)

@web_app.route('/')
@web_app.route('/health')
def health_check():
    return "Bot is running smoothly!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


# ==========================================
# SELF PING SYSTEM (Render မအိပ်သွားစေရန်)
# ==========================================
def self_ping():
    url = RENDER_EXTERNAL_URL
    if not url:
        return
    while True:
        time.sleep(300) # ၅ မိနစ် တစ်ခါ Ping မည်
        try:
            requests.get(f"{url}/health")
            logger.info("✅ Self ping successful")
        except Exception as e:
            logger.error(f"❌ Self ping failed: {e}")


# ==========================================
# BOT HANDLERS (/start & Admin Panel)
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    # User ကို Database ထဲသို့ တိတ်တဆိတ် သိမ်းမည်
    save_user(user_id, user.username, user.first_name)

    # Admin ဟုတ်မဟုတ် စစ်ဆေးခြင်း
    if user_id in ADMIN_IDS:
        keyboard = [[InlineKeyboardButton("👥 User စာရင်း ကြည့်ရန်", callback_data="view_users")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg_text = "သင်သည် admin ဖြစ်သောကြောင့် အောက်ပါ feature များကို အသုံးပြုနိုင်ပါသည်။"
        await update.message.reply_text(msg_text, reply_markup=reply_markup)
    else:
        # သာမန် User ဖြစ်ပါက ဘာမှစာမပြန်ပါ (Silent)
        return


# ==========================================
# BUTTON CLICK (User စာရင်းကြည့်ရန်)
# ==========================================
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        return

    if query.data == "view_users":
        count = get_users_count()
        text = f"သင်သည် admin ဖြစ်သောကြောင့် အောက်ပါ feature များကို အသုံးပြုနိုင်ပါသည်။\n\n📊 **စုစုပေါင်း User အရေအတွက်:** {count} ယောက်"
        keyboard = [[InlineKeyboardButton("👥 User စာရင်း ကြည့်ရန်", callback_data="view_users")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ==========================================
# BROADCAST SYSTEM (/broadcast)
# ==========================================
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        return

    if not context.args:
        await update.message.reply_text("⚠️ အသုံးပြုနည်း: `/broadcast ပို့ချင်သောစာသား`", parse_mode="Markdown")
        return

    broadcast_msg = " ".join(context.args)
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users;")
        users = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Database error during broadcast: {e}")
        await update.message.reply_text("❌ Database ချိတ်ဆက်မှု အဆင်မပြေပါ။")
        return

    if not users:
        await update.message.reply_text("⚠️ စာပို့ရန် User တစ်ယောက်မှ မရှိသေးပါ။")
        return

    await update.message.reply_text(f"⏳ User စုစုပေါင်း {len(users)} ယောက်ထံသို့ စာများ စတင်ပို့ဆောင်နေပါပြီ...")
    
    success_count = 0
    fail_count = 0
    
    for user in users:
        target_id = user[0]
        try:
            await context.bot.send_message(chat_id=target_id, text=broadcast_msg)
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Failed to send message to {target_id}: {e}")
            fail_count += 1
            
    await update.message.reply_text(
        f"✅ Broadcast အောင်မြင်စွာ ပြီးဆုံးပါပြီ။\n\n"
        f"✅ အောင်မြင်: {success_count} ယောက်\n"
        f"❌ မအောင်မြင်: {fail_count} ယောက်"
    )


# ==========================================
# MAIN FUNCTION
# ==========================================
def main():
    # Database ဆောက်ခြင်း
    init_db()

    # Flask နဲ့ Self-Ping ကို Background မှာ ဖွင့်ရန်
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=self_ping, daemon=True).start()

    # Telegram Bot ကို တည်ဆောက်ခြင်း
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(CommandHandler("broadcast", broadcast_command))

    logger.info("🤖 Bot is successfully running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
        
