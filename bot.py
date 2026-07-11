import asyncio
import logging
import re
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

import config
from database import (
    init_db, add_api_key, remove_api_key, get_all_keys, get_active_keys,
    update_balance, update_status, get_current_key, get_next_key,
    get_total_keys, get_active_count, add_order, get_orders,
    get_setting, set_setting, get_key_by_value
)
from smm_api import check_balance, place_order, get_services_by_platform_simple, get_order_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def is_admin(user_id):
    return user_id in config.ADMIN_IDS

async def auto_switch_key(platform):
    current = get_current_key(platform)
    if current:
        balance = check_balance(current['key'])
        update_balance(current['key'], balance)
        if balance < config.MIN_BALANCE:
            update_status(current['key'], 'inactive')
            logger.info(f"🔴 Key {current['key'][:10]}... removed (balance: {balance})")
            new_key = get_next_key(platform)
            if new_key:
                logger.info(f"🔄 Switched to new key: {new_key['key'][:10]}...")
                return new_key['key']
            else:
                logger.warning(f"⚠️ No active key found for {platform}")
                return None
    return current['key'] if current else None

# ============================================================
# ইউজার কমান্ড
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 হ্যালো {user.first_name}!\n\n"
        "🤖 আমি SMMLite অটোমেশন বট।\n"
        "আমি Telegram, Facebook, TikTok-এর জন্য অর্ডার নিতে পারি।\n\n"
        "📌 কমান্ড:\n"
        "/order - নতুন অর্ডার শুরু করতে\n"
        "/status <order_id> - অর্ডার স্ট্যাটাস চেক করতে\n"
        "/history - আপনার অর্ডার ইতিহাস\n"
        "/balance - ব্যালেন্স দেখতে\n"
        "/status - সিস্টেম স্ট্যাটাস\n\n"
        "⚡ অ্যাডমিন কমান্ড:\n"
        "/addkey <api_key> <platform> - কী যোগ করুন\n"
        "/removekey <api_key> - কী মুছুন\n"
        "/listkeys - সব কী দেখুন\n"
        "/activatekey <api_key> - কী সক্রিয় করুন\n"
        "/checkkey <api_key> - কী চেক করুন",
        parse_mode="HTML"
    )

# ... (বাকি ফাংশনগুলো আগের মতো থাকবে, কিন্তু parse_mode সব জায়গায় HTML ব্যবহার করুন)

# ============================================================
# মেইন
# ============================================================

def main():
    init_db()
    app = Application.builder().token(config.BOT_TOKEN).build()

    # হ্যান্ডলার যোগ করুন
    app.add_handler(CommandHandler("start", start))
    # ... বাকি হ্যান্ডলার

    # এরর হ্যান্ডলার (ঐচ্ছিক)
    async def error_handler(update, context):
        logger.error(msg="Exception while handling an update:", exc_info=context.error)
    app.add_error_handler(error_handler)

    logger.info("🤖 বট চালু হচ্ছে...")
    app.run_polling()

if __name__ == "__main__":
    main()
