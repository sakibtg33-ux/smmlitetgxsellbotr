import asyncio
import logging
import random
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
    get_setting, set_setting
)
from smm_api import (
    check_balance, place_order, get_services_by_platform_simple,
    fetch_services
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# হেল্পার ফাংশন
# ============================================================
def is_admin(user_id):
    return user_id in config.ADMIN_IDS

async def auto_switch_key(platform):
    """যদি current key এর balance কম থাকে, তাহলে নতুন key নিবে"""
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
# ইউজার কমান্ড হ্যান্ডলার
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 হ্যালো {user.first_name}!\n\n"
        "🤖 আমি SMMLite অটোমেশন বট।\n"
        "আমি Telegram, Facebook, TikTok, Instagram, YouTube, Twitter-এর জন্য অর্ডার নিতে পারি।\n\n"
        "📌 *কমান্ডসমূহ:*\n"
        "/order - নতুন অর্ডার দিতে\n"
        "/balance - ব্যালেন্স চেক করতে\n"
        "/history - আপনার অর্ডার ইতিহাস\n"
        "/status - সিস্টেম স্ট্যাটাস\n\n"
        "⚡ *অ্যাডমিন কমান্ড:*\n"
        "/addkey <api_key> <platform> - নতুন কী যোগ করুন\n"
        "/removekey <api_key> - কী মুছুন\n"
        "/listkeys - সব কী দেখুন\n"
        "/refreshservices - সার্ভিস লিস্ট রিফ্রেশ করুন",
        parse_mode="Markdown"
    )

async def order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """অর্ডার প্রক্রিয়া শুরু করে"""
    keyboard = [
        [InlineKeyboardButton("📱 Telegram", callback_data="platform_telegram")],
        [InlineKeyboardButton("📘 Facebook", callback_data="platform_facebook")],
        [InlineKeyboardButton("🎵 TikTok", callback_data="platform_tiktok")],
        [InlineKeyboardButton("📷 Instagram", callback_data="platform_instagram")],
        [InlineKeyboardButton("▶️ YouTube", callback_data="platform_youtube")],
        [InlineKeyboardButton("🐦 Twitter", callback_data="platform_twitter")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📌 যে প্ল্যাটফর্মে অর্ডার দিতে চান সেটি নির্বাচন করুন:",
        reply_markup=reply_markup
    )

async def platform_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    platform = query.data.replace("platform_", "")
    context.user_data['platform'] = platform

    current = get_current_key(platform)
    api_key = current['key'] if current else None

    services = get_services_by_platform_simple(platform, api_key)
    if not services:
        await query.edit_message_text(
            f"❌ {platform.capitalize()} এর জন্য কোনো সার্ভিস পাওয়া যায়নি।\n"
            "অ্যাডমিনকে যোগাযোগ করুন অথবা `/refreshservices` চালান।"
        )
        return

    # ক্যাটাগরি অনুযায়ী গ্রুপ করতে চাইলে এখানে লজিক যোগ করা যেতে পারে
    keyboard = []
    # ২০টির বেশি হলে পেজিনেশন (সহজ সমাধান: ২০টি দেখিয়ে "আরও...")
    items = list(services.items())
    if len(items) > 20:
        items = items[:20]
        keyboard.append([InlineKeyboardButton("📌 আরও সার্ভিস (আপডেট আসছে)", callback_data="more_coming")])

    for service_id, service_name in items:
        keyboard.append([InlineKeyboardButton(service_name, callback_data=f"service_{platform}_{service_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"✅ প্ল্যাটফর্ম: *{platform.capitalize()}*\nএখন সার্ভিস নির্বাচন করুন:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def service_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    platform = data[1]
    service_id = data[2]
    context.user_data['service_id'] = service_id
    context.user_data['platform'] = platform

    await query.edit_message_text(
        f"📝 এখন *{platform.capitalize()}* অর্ডারের বিবরণ দিন:\n\n"
        "ফরম্যাট: `লিংক|কোয়ান্টিটি`\n"
        "উদাহরণ: `https://t.me/username|100`",
        parse_mode="Markdown"
    )
    context.user_data['waiting_for_order_details'] = True

async def handle_order_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_order_details'):
        return

    text = update.message.text.strip()
    if '|' not in text:
        await update.message.reply_text(
            "❌ ভুল ফরম্যাট! ব্যবহার করুন: `লিংক|কোয়ান্টিটি`\n"
            "উদাহরণ: `https://t.me/username|100`"
        )
        return

    link, quantity_str = text.split('|', 1)
    try:
        quantity = int(quantity_str.strip())
    except ValueError:
        await update.message.reply_text("❌ কোয়ান্টিটি অবশ্যই সংখ্যা হতে হবে।")
        return

    platform = context.user_data.get('platform')
    service_id = context.user_data.get('service_id')

    if not platform or not service_id:
        await update.message.reply_text("❌ প্ল্যাটফর্ম বা সার্ভিস নির্বাচন করা হয়নি। /order দিয়ে আবার শুরু করুন।")
        return

    # অটো-সুইচ চেক
    current_key = await auto_switch_key(platform)
    if not current_key:
        await update.message.reply_text(
            f"❌ {platform.capitalize()} এর জন্য কোনো সক্রিয় API Key নেই!\n"
            "অ্যাডমিনকে যোগাযোগ করুন।"
        )
        return

    # অর্ডার প্লেস করুন
    order_result = place_order(current_key, service_id, link.strip(), quantity)
    if order_result.get('status') == 'success':
        order_id = order_result.get('order_id')
        add_order(
            user_id=update.effective_user.id,
            platform=platform,
            service=service_id,
            quantity=quantity,
            link=link.strip(),
            order_id=order_id
        )
        await update.message.reply_text(
            f"✅ *অর্ডার সফল!*\n\n"
            f"🆔 অর্ডার আইডি: `{order_id}`\n"
            f"📱 প্ল্যাটফর্ম: {platform.capitalize()}\n"
            f"🔢 কোয়ান্টিটি: {quantity}\n"
            f"🔗 লিংক: {link.strip()}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"❌ অর্ডার ব্যর্থ!\n\n"
            f"কারণ: {order_result.get('message', 'অজানা ত্রুটি')}"
        )

    context.user_data['waiting_for_order_details'] = False

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """বর্তমান সক্রিয় কী-এর ব্যালেন্স দেখায়"""
    platform = "telegram"  # ডিফল্ট
    current = get_current_key(platform)
    if current:
        balance = check_balance(current['key'])
        update_balance(current['key'], balance)
        await update.message.reply_text(
            f"💰 *ব্যালেন্স*\n\n"
            f"📱 প্ল্যাটফর্ম: {platform.capitalize()}\n"
            f"🔑 API Key: `{current['key'][:10]}...`\n"
            f"💵 ব্যালেন্স: `${balance:.6f}`\n"
            f"📊 স্ট্যাটাস: {'✅ সক্রিয়' if balance >= config.MIN_BALANCE else '❌ কম ব্যালেন্স'}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ কোনো সক্রিয় API Key নেই।")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ইউজারের অর্ডার ইতিহাস"""
    orders = get_orders(update.effective_user.id, limit=10)
    if not orders:
        await update.message.reply_text("📭 আপনার কোনো অর্ডার নেই।")
        return

    text = "📋 *আপনার শেষ ১০টি অর্ডার:*\n\n"
    for order in orders:
        text += (
            f"🆔 `{order['order_id']}` | {order['platform'].capitalize()}\n"
            f"   🔢 {order['quantity']} | 📊 {order['status']}\n"
            f"   📅 {order['created_at'][:16]}\n\n"
        )
    await update.message.reply_text(text, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সিস্টেম স্ট্যাটাস দেখায়"""
    total = get_total_keys()
    active = get_active_count()
    await update.message.reply_text(
        f"📊 *সিস্টেম স্ট্যাটাস*\n\n"
        f"🔑 মোট API Keys: `{total}`\n"
        f"✅ সক্রিয় Keys: `{active}`\n"
        f"⚠️ ন্যূনতম ব্যালেন্স: `${config.MIN_BALANCE}`\n"
        f"📱 প্ল্যাটফর্ম: Telegram, Facebook, TikTok, Instagram, YouTube, Twitter",
        parse_mode="Markdown"
    )

# ============================================================
# অ্যাডমিন কমান্ড
# ============================================================

async def add_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ এই কমান্ডটি শুধুমাত্র অ্যাডমিনদের জন্য।")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ ব্যবহার: `/addkey <api_key> <platform>`\n"
            "প্ল্যাটফর্ম: `telegram`, `facebook`, `tiktok`, `instagram`, `youtube`, `twitter`"
        )
        return

    key = args[0]
    platform = args[1].lower()
    valid_platforms = ['telegram', 'facebook', 'tiktok', 'instagram', 'youtube', 'twitter']
    if platform not in valid_platforms:
        await update.message.reply_text(
            f"❌ প্ল্যাটফর্মটি সঠিক নয়। ব্যবহার করুন: {', '.join(valid_platforms)}"
        )
        return

    if add_api_key(key, platform):
        await update.message.reply_text(f"✅ API Key সফলভাবে যোগ করা হয়েছে!\n📱 প্ল্যাটফর্ম: {platform.capitalize()}")
    else:
        await update.message.reply_text("❌ এই API Key ইতিমধ্যে যোগ করা হয়েছে।")

async def remove_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ এই কমান্ডটি শুধুমাত্র অ্যাডমিনদের জন্য।")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text("❌ ব্যবহার: `/removekey <api_key>`")
        return

    key = args[0]
    remove_api_key(key)
    await update.message.reply_text(f"✅ API Key `{key[:10]}...` রিমুভ করা হয়েছে।")

async def list_keys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ এই কমান্ডটি শুধুমাত্র অ্যাডমিনদের জন্য।")
        return

    keys = get_all_keys()
    if not keys:
        await update.message.reply_text("📭 কোনো API Key নেই।")
        return

    text = "🔑 *সব API Keys:*\n\n"
    for k in keys[:30]:  # ৩০টি দেখাবে
        status_icon = "✅" if k['status'] == 'active' else "❌"
        balance = k.get('balance', 0)
        text += f"{status_icon} `{k['key'][:15]}...` | {k['platform'].capitalize()} | ${balance:.4f}\n"
    if len(keys) > 30:
        text += f"\n... এবং আরও {len(keys)-30}টি কী আছে।"
    await update.message.reply_text(text, parse_mode="Markdown")

async def refresh_services_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সার্ভিস ক্যাশে রিফ্রেশ করে"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ এই কমান্ডটি শুধুমাত্র অ্যাডমিনদের জন্য।")
        return

    # ক্যাশে ইনভ্যালিড করতে smm_api মডিউলে একটি ফাংশন কল করি
    from smm_api import _service_cache, _cache_time
    _service_cache.clear()
    _cache_time.clear()
    await update.message.reply_text("✅ সার্ভিস ক্যাশে রিফ্রেশ করা হয়েছে।")

# ============================================================
# মেইন ফাংশন
# ============================================================

def main():
    init_db()

    app = Application.builder().token(config.BOT_TOKEN).build()

    # কমান্ড
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("order", order_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("status", status_command))

    # অ্যাডমিন
    app.add_handler(CommandHandler("addkey", add_key_command))
    app.add_handler(CommandHandler("removekey", remove_key_command))
    app.add_handler(CommandHandler("listkeys", list_keys_command))
    app.add_handler(CommandHandler("refreshservices", refresh_services_command))

    # ক্যালব্যাক
    app.add_handler(CallbackQueryHandler(platform_callback, pattern="^platform_"))
    app.add_handler(CallbackQueryHandler(service_callback, pattern="^service_"))

    # টেক্সট হ্যান্ডলার
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_order_details))

    logger.info("🤖 বট চালু হচ্ছে...")
    app.run_polling()

if __name__ == "__main__":
    main()
