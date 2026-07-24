import os
import sqlite3
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

# ==========================================
# 🌐 Dummy Web Server (Render တွင် Port Error မတက်ရန်)
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()
# ==========================================

# ==========================================
# 🗄️ Database Functions (User Data မှတ်ရန်)
# ==========================================
def init_db():
    conn = sqlite3.connect("bot_users.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

def add_user(user_id: int):
    conn = sqlite3.connect("bot_users.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("bot_users.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    return [u[0] for u in users]
# ==========================================

# ==========================================
# 🤖 Bot Handlers
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /start နှိပ်သူတိုင်း၏ ID ကို Database တွင် မှတ်ထားမည် (စာပြန်မပို့ပါ)
    user_id = update.effective_user.id
    add_user(user_id)
    logging.info(f"New user registered: {user_id}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Admin စစ်ဆေးခြင်း
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠️ ဒီ Command ကို Admin သာ အသုံးပြုနိုင်ပါသည်။")
        return

    # Reply ပြန်ထားခြင်း ရှိ/မရှိ စစ်ဆေးခြင်း
    if not update.message.reply_to_message:
        await update.message.reply_text("👉 ကြော်ငြာချင်တဲ့ စာ (သို့) ဓာတ်ပုံကို Reply ပြန်ပြီး `/broadcast` လို့ ရိုက်ပေးပါ။")
        return

    target_message = update.message.reply_to_message
    users = get_all_users()
    
    if len(users) == 0:
        await update.message.reply_text("⚠️ Bot ထဲတွင် User တစ်ယောက်မှ မရှိသေးပါ။")
        return

    status_msg = await update.message.reply_text(f"📢 လူဦးရေ {len(users)} ယောက်ဆီ ကြော်ငြာ စတင် ပို့ဆောင်နေပါပြီ...")
    
    success = 0
    failed = 0

    for user_id in users:
        try:
            await target_message.copy(chat_id=user_id)
            success += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ **Broadcast ပို့ဆောင်မှု ပြီးစီးပါပြီ။**\n\n"
        f"▪️ အောင်မြင်စွာ ပို့ပြီး: {success}\n"
        f"▪️ မအောင်မြင်/Bot Block ထားသူ: {failed}"
    )
# ==========================================

if __name__ == "__main__":
    init_db()
    
    # 1. Render အတွက် Dummy Server ကို နောက်ကွယ်တွင် အရင်ဖွင့်မည်
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    # 2. Telegram Bot စတင်မည်
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    
    print("Bot is successfully running...")
    # drop_pending_updates=True ထည့်ထားသဖြင့် Conflict Error များကို ကာကွယ်ပေးသည်
    app.run_polling(drop_pending_updates=True)
    
