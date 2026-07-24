import os
import logging
import threading
import psycopg2
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL") 
ADMIN_IDS_STR = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(",") if id.strip().isdigit()]

# ==========================================
# 🌐 Dummy Web Server (Render တွင် Port Error မတက်ရန်)
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive and running with Supabase Database!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()

# ==========================================
# 🗄️ Supabase Database Functions
# ==========================================
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    logging.info("Supabase database initialized successfully.")

def add_user(user_id: int, username: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username) VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
        """, (user_id, username))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"Error adding user to database: {e}")

def get_all_users_info():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username FROM users")
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        return users
    except Exception as e:
        logging.error(f"Error fetching users: {e}")
        return []

# ==========================================
# 🤖 Bot Handlers
# ==========================================
async def track_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type == "private":
        user = update.effective_user
        if user:
            username = f"@{user.username}" if user.username else user.first_name
            add_user(user.id, username)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = f"@{user.username}" if user.username else user.first_name
    add_user(user.id, username)
    await update.message.reply_text("👋 မင်္ဂလာပါ! Bot အဆင်သင့် ဖြစ်ပါပြီ။")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    keyboard = [
        [InlineKeyboardButton("👥 User စာရင်း ကြည့်ရန်", callback_data="view_users")],
        [InlineKeyboardButton("📢 Broadcast အသုံးပြုနည်း", callback_data="help_broadcast")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🛠️ **Admin Panel** မှ ကြိုဆိုပါတယ်။", reply_markup=reply_markup, parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.effective_user.id not in ADMIN_IDS:
        return

    if query.data == "view_users":
        users = get_all_users_info()
        if not users:
            await query.message.reply_text("⚠️ User တစ်ယောက်မှ မရှိသေးပါ။")
            return

        text = f"👥 **Cloud (Supabase) ပေါ်ရှိ User စုစုပေါင်း: {len(users)} ယောက်**\n\n"
        for uid, uname in users:
            display_name = uname if uname else "Unknown"
            text += f"▪️ {display_name} (`{uid}`)\n"

        if len(text) > 4000:
            text = text[:4000] + "\n... (User များနေသဖြင့် အချို့ကို ဖျောက်ထားပါသည်)"

        await query.message.reply_text(text, parse_mode="Markdown")

    elif query.data == "help_broadcast":
        await query.message.reply_text("👉 **Broadcast ပို့ရန်** - သင်ကြော်ငြာချင်တဲ့ စာကို Reply ပြန်ပြီး `/broadcast` လို့ ရိုက်ပေးပါ။", parse_mode="Markdown")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ ဒီ Command ကို Admin သာ အသုံးပြုနိုင်ပါသည်။")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("👉 ကြော်ငြာချင်တဲ့ စာကို Reply ပြန်ပြီး `/broadcast` လို့ ရိုက်ပေးပါ။")
        return

    target_message = update.message.reply_to_message
    users = get_all_users_info()
    
    if len(users) == 0:
        await update.message.reply_text("⚠️ Bot ထဲတွင် User တစ်ယောက်မှ မရှိသေးပါ။")
        return

    status_msg = await update.message.reply_text(f"📢 လူဦးရေ {len(users)} ယောက်ဆီ ကြော်ငြာ စတင် ပို့ဆောင်နေပါပြီ...")
    
    success = 0
    failed = 0

    for uid, _ in users:
        try:
            await target_message.copy(chat_id=uid)
            success += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ **Broadcast ပို့ဆောင်မှု ပြီးစီးပါပြီ။**\n\n"
        f"▪️ အောင်မြင်စွာ ပို့ပြီး: {success} ယောက်\n"
        f"▪️ မအောင်မြင်/Bot Block ထားသူ: {failed} ယောက်"
    )

# ==========================================
if __name__ == "__main__":
    init_db()
    
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_users))
    
    print("Bot is successfully running with Supabase Cloud DB...")
    app.run_polling(drop_pending_updates=True)
    
