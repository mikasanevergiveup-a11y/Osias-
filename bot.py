import os
import sys
import sqlite3
import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

# --- Database Functions ---
def init_db():
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

def add_user(user_id: int):
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    return [u[0] for u in users]

# --- ၃ မိနစ်တစ်ခါ sys ကိုသုံးပြီး Bot ကို Restart လုပ်ပေးမည့် Task ---
async def auto_restart():
    await asyncio.sleep(180)  # ၃ မိနစ် (၁၈၀ စက္ကန့်)
    logging.info("3 မိနစ် ပြည့်သွားသဖြင့် Script ကို sys/os ဖြင့် ပြန်လည် စတင် (Restart) ပေးနေပါသည်...")
    # sys.executable နှင့် sys.argv ကို သုံးပြီး လက်ရှိ Python process ကို အစကနေ ပြန်စပေးခြင်း
    os.execv(sys.executable, [sys.executable] + sys.argv)

async def post_init(application):
    # Bot စတင်သည်နှင့် Background တွင် ၃ မိနစ် Auto-Restart Task ကို ပလပ်ထိုးပေးခြင်း
    asyncio.create_task(auto_restart())

# --- Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # User ID ကို Database ထဲ တိတ်တဆိတ် သိမ်းမည် (စာပြန်မပို့ပါ)
    user_id = update.effective_user.id
    add_user(user_id)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Admin ဟုတ်မဟုတ် စစ်ဆေးခြင်း
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠️ ဒီ Command ကို Admin သာ အသုံးပြုနိုင်ပါသည်။")
        return

    # Broadcast မလုပ်မီ ပို့ချင်သည့် စာ/ပုံ ကို Reply ပြန်ထားခြင်း ရှိမရှိ စစ်ခြင်း
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "👉 ကြော်ငြာချင်တဲ့ စာ (သို့) ဓာတ်ပုံ/ဗီဒီယိုကို Reply ပြန်ပြီး `/broadcast` လို့ ရိုက်ပေးပါ။",
            parse_mode="Markdown"
        )
        return

    target_message = update.message.reply_to_message
    users = get_all_users()
    
    status_msg = await update.message.reply_text(f"📢 လူဦးရေ {len(users)} ယောက်ဆီ ကြော်ငြာ စတင် ပို့ဆောင်နေပါပြီ...")
    
    success = 0
    failed = 0

    for user_id in users:
        try:
            await target_message.copy(chat_id=user_id)
            success += 1
            await asyncio.sleep(0.05)  # Telegram Rate Limit မမိစေရန်
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ **Broadcast ပို့ဆောင်မှု ပြီးစီးပါပြီ။**\n\n"
        f"▪️ အောင်မြင်စွာ ပို့ပြီး: {success}\n"
        f"▪️ မအောင်မြင်/Bot Block ထားသူ: {failed}"
    )

if __name__ == "__main__":
    init_db()
    
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    
    print("Bot starting with 3-minute sys restart loop...")
    app.run_polling()
  
