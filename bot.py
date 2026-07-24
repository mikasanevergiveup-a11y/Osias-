import os
import sqlite3
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
# Admin ID များကို ကော်မာ (,) ခြားပြီး ယူမည် (ဥပမာ - "111111,222222")
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
        self.wfile.write(b"Bot is alive and running!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()

# ==========================================
# 🗄️ Database Functions (ID နှင့် Username မှတ်ရန်)
# ==========================================
def init_db():
    conn = sqlite3.connect("bot_users.db", check_same_thread=False)
    cursor = conn.cursor()
    # Table ဖန်တီးမည် (username column ပါ ထည့်ထားသည်)
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT)")
    
    # Database အဟောင်းရှိနေခဲ့လျှင် username column အသစ်တိုးပေးရန်
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
    except Exception:
        pass # Column ရှိပြီးသားဖြစ်ပါက ကျော်သွားမည်
        
    conn.commit()
    conn.close()

def add_user(user_id: int, username: str):
    conn = sqlite3.connect("bot_users.db", check_same_thread=False)
    cursor = conn.cursor()
    # User အသစ်ဆိုလျှင် ထည့်မည်၊ အဟောင်းဆိုလျှင် Username အသစ်ပြန်ပြောင်းပေးမည်
    cursor.execute("INSERT OR REPLACE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

def get_all_users_info():
    conn = sqlite3.connect("bot_users.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username FROM users")
    users = cursor.fetchall()
    conn.close()
    return users

# ==========================================
# 🤖 Bot Handlers
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Username ရှိလျှင် @username ကိုယူမည်၊ မရှိလျှင် First Name ကိုယူမည်
    username = f"@{user.username}" if user.username else user.first_name
    
    # ID နှင့် Username ကို မှတ်မည် (စာမပြန်ပါ)
    add_user(user.id, username)
    logging.info(f"User registered: {username} ({user.id})")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Admin ဟုတ်မဟုတ် စစ်ဆေးခြင်း
    if update.effective_user.id not in ADMIN_IDS:
        return

    # Admin Panel ခလုတ်များ
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

        text = f"👥 **လက်ရှိ User စုစုပေါင်း: {len(users)} ယောက်**\n\n"
        for uid, uname in users:
            # Username များမရှိခဲ့လျှင် "Unknown" ဟုပြမည်
            display_name = uname if uname else "Unknown"
            text += f"▪️ {display_name} (`{uid}`)\n"

        # Telegram ၏ စာလုံးရေကန့်သတ်ချက်ကြောင့် ဖြတ်ထုတ်ခြင်း
        if len(text) > 4000:
            text = text[:4000] + "\n... (User များနေသဖြင့် အချို့ကို ဖျောက်ထားပါသည်)"

        await query.message.reply_text(text, parse_mode="Markdown")

    elif query.data == "help_broadcast":
        await query.message.reply_text("👉 **Broadcast ပို့ရန်** - သင်ကြော်ငြာချင်တဲ့ စာ (သို့) ဓာတ်ပုံကို Reply ပြန်ပြီး `/broadcast` လို့ ရိုက်ပေးပါ။", parse_mode="Markdown")

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
    
    # Handlers များ ချိတ်ဆက်ခြင်း
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel)) # Admin Panel အတွက် Command သစ်
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(button_callback)) # ခလုတ်များအတွက် Handler
    
    print("Bot is successfully running with Admin Panel...")
    app.run_polling(drop_pending_updates=True)

