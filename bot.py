import asyncio
import logging
import os
import psycopg2
import requests
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

# Environment Variables များယူခြင်း
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

# Admin ID များကို Environment Variable မှ ယူခြင်း (ဥပမာ - 12345678,87654321)
ADMIN_IDS = [
    int(x.strip())
    for x in os.environ.get("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]


# Database Connection
def get_db_connection():
  return psycopg2.connect(DATABASE_URL, sslmode="require")


# Database Table မရှိသေးပါက အသစ်ဆောက်ခြင်း
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
    logger.info("Supabase database initialized successfully.")
  except Exception as e:
    logger.error(f"Database error: {e}")


# User အချက်အလက်များကို Database ထဲ သိမ်းဆည်းခြင်း
def save_user(user_id, username, first_name):
  try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
            INSERT INTO users (user_id, username, first_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING;
        """,
        (user_id, username, first_name),
    )
    conn.commit()
    cur.close()
    conn.close()
  except Exception as e:
    logger.error(f"Error saving user: {e}")


# စုစုပေါင်း User အရေအတွက်ကို ရယူခြင်း
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


# Render Server မအိပ်သွားစေရန် ၁၀ မိနစ်တစ်ခါ Self-Ping လုပ်ပေးသည့် System
async def self_ping():
  while True:
    await asyncio.sleep(600)  # 600 စက္ကန့် (၁၀ မိနစ်)
    if RENDER_EXTERNAL_URL:
      try:
        response = requests.get(RENDER_EXTERNAL_URL)
        logger.info(f"Self ping successful: status {response.status_code}")
      except Exception as e:
        logger.error(f"Self ping failed: {e}")


# /start Command Handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
  user = update.effective_user
  user_id = user.id

  # User ကို Database ထဲ သို့ တိတ်တဆိတ် သိမ်းမည်
  save_user(user_id, user.username, user.first_name)

  # Admin ဟုတ်မဟုတ် စစ်ဆေးခြင်း
  if user_id in ADMIN_IDS:
    keyboard = [[
        InlineKeyboardButton(
            "👥 User စာရင်း ကြည့်ရန်", callback_data="view_users"
        )
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg_text = (
        "သင်သည် admin ဖြစ်သောကြောင့် အောက်ပါ feature များကို"
        " အသုံးပြုနိုင်ပါသည်။"
    )
    await update.message.reply_text(msg_text, reply_markup=reply_markup)
  else:
    # သာမန် User ဖြစ်ပါက ဘာမှ ပြန်မပို့ပါ (Silent)
    return


# Button နှိပ်သည့်အခါ အလုပ်လုပ်မည့် Handler
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
  query = update.callback_query
  await query.answer()

  user_id = query.from_user.id
  if user_id not in ADMIN_IDS:
    return

  if query.data == "view_users":
    count = get_users_count()
    text = (
        f"သင်သည် admin ဖြစ်သောကြောင့် အောက်ပါ feature များကို"
        f" အသုံးပြုနိုင်ပါသည်။\n\n📊 **စုစုပေါင်း User အရေအတွက်:** {count} ယောက်"
    )
    keyboard = [[
        InlineKeyboardButton(
            "👥 User စာရင်း ကြည့်ရန်", callback_data="view_users"
        )
    ]]
    await query.message.edit_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


# Bot စတင်ချိန်တွင် Self-Ping System ကို Background မှာ စတင်ရန်
async def post_init(application: Application):
  asyncio.create_task(self_ping())


def main():
  init_db()

  app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

  app.add_handler(CommandHandler("start", start_command))
  app.add_handler(CallbackQueryHandler(button_click))

  logger.info("Bot is successfully running with Supabase Cloud DB...")
  app.run_polling()


if __name__ == "__main__":
  main()
    
