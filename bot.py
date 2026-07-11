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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
        "/status &lt;order_id&gt; - অর্ডার স্ট্যাটাস চেক করতে\n"
        "/history - আপনার অর্ডার ইতিহাস\n"
        "/balance - ব্যালেন্স দেখতে\n"
        "/sysstatus - সিস্টেম স্ট্যাটাস\n\n"
        "⚡ অ্যাডমিন কমান্ড:\n"
        "/addkey &lt;api_key&gt; &lt;platform&gt; - কী যোগ করুন\n"
        "/removekey &lt;api_key&gt; - কী মুছুন\n"
        "/listkeys - সব কী দেখুন\n"
        "/activatekey &lt;api_key&gt; - কী সক্রিয় করুন\n"
        "/checkkey &lt;api_key&gt; - কী চেক করুন",
        parse_mode="HTML"
    )

async def order_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📱 Telegram", callback_data="platform_telegram")],
        [InlineKeyboardButton("📘 Facebook", callback_data="platform_facebook")],
        [InlineKeyboardButton("🎵 TikTok", callback_data="platform_tiktok")],
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
            "অ্যাডমিনকে যোগাযোগ করুন।"
        )
        return

    keyboard = []
    items = list(services.items())
    for service_id, service_name in items[:20]:
        keyboard.append([InlineKeyboardButton(service_name, callback_data=f"service_{platform}_{service_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"✅ প্ল্যাটফর্ম: <b>{platform.capitalize()}</b>\nএখন সার্ভিস নির্বাচন করুন:",
        parse_mode="HTML",
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
        f"📝 <b>{platform.capitalize()}</b> অর্ডারের জন্য <b>লিংক</b> দিন:\n\n"
        "উদাহরণ: <code>https://t.me/username</code> অথবা <code>https://t.me/post/123</code>",
        parse_mode="HTML"
    )
    context.user_data['waiting_for_link'] = True

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_link'):
        return

    link = update.message.text.strip()
    if not link.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ সঠিক লিংক দিন (http:// বা https:// দিয়ে শুরু করতে হবে)।")
        return

    context.user_data['link'] = link
    context.user_data['waiting_for_link'] = False
    context.user_data['waiting_for_quantity'] = True

    await update.message.reply_text(
        "🔢 এখন <b>কোয়ান্টিটি</b> দিন (সংখ্যা):\n"
        "উদাহরণ: <code>100</code>",
        parse_mode="HTML"
    )

async def handle_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_quantity'):
        return

    try:
        quantity = int(update.message.text.strip())
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ দয়া করে একটি সঠিক সংখ্যা দিন।")
        return

    context.user_data['quantity'] = quantity
    context.user_data['waiting_for_quantity'] = False

    platform = context.user_data['platform']
    service_id = context.user_data['service_id']
    link = context.user_data['link']

    # আনুমানিক খরচ (ডিফল্ট রেট 0.03/1000)
    rate = 0.03
    cost = (quantity / 1000) * rate

    context.user_data['cost'] = cost
    context.user_data['order_data'] = {
        'platform': platform,
        'service_id': service_id,
        'link': link,
        'quantity': quantity
    }

    await update.message.reply_text(
        f"📊 <b>অর্ডার সারাংশ</b>\n\n"
        f"📱 প্ল্যাটফর্ম: {platform.capitalize()}\n"
        f"🔗 লিংক: {link}\n"
        f"🔢 কোয়ান্টিটি: {quantity}\n"
        f"💰 আনুমানিক খরচ: <code>${cost:.4f}</code>\n\n"
        "✅ অর্ডার নিশ্চিত করতে <b>'হ্যাঁ'</b> টাইপ করুন\n"
        "❌ বাতিল করতে <b>'না'</b> টাইপ করুন",
        parse_mode="HTML"
    )
    context.user_data['waiting_for_confirmation'] = True

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_confirmation'):
        return

    text = update.message.text.strip().lower()
    if text not in ['হ্যাঁ', 'yes', 'ঠিক', 'ok', 'না', 'no']:
        await update.message.reply_text("❌ 'হ্যাঁ' বা 'না' দিন।")
        return

    if text in ['না', 'no']:
        await update.message.reply_text("❌ অর্ডার বাতিল করা হয়েছে।")
        context.user_data.clear()
        return

    # অর্ডার প্লেস করুন
    platform = context.user_data['platform']
    service_id = context.user_data['service_id']
    link = context.user_data['link']
    quantity = context.user_data['quantity']

    current_key = await auto_switch_key(platform)
    if not current_key:
        await update.message.reply_text(
            f"❌ {platform.capitalize()} এর জন্য কোনো সক্রিয় API Key নেই!\n"
            "অ্যাডমিনকে যোগাযোগ করুন।"
        )
        context.user_data.clear()
        return

    order_result = place_order(current_key, service_id, link, quantity)
    if order_result.get('status') == 'success':
        order_id = order_result.get('order_id')
        add_order(
            user_id=update.effective_user.id,
            platform=platform,
            service=service_id,
            quantity=quantity,
            link=link,
            order_id=order_id
        )
        await update.message.reply_text(
            f"✅ <b>অর্ডার সফল!</b>\n\n"
            f"🆔 অর্ডার আইডি: <code>{order_id}</code>\n"
            f"📱 প্ল্যাটফর্ম: {platform.capitalize()}\n"
            f"🔢 কোয়ান্টিটি: {quantity}\n"
            f"🔗 লিংক: {link}\n\n"
            f"📌 স্ট্যাটাস চেক করতে: <code>/status {order_id}</code>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"❌ অর্ডার ব্যর্থ!\n\n"
            f"কারণ: {order_result.get('message', 'অজানা ত্রুটি')}"
        )

    context.user_data.clear()

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("❌ ব্যবহার: <code>/status &lt;order_id&gt;</code>", parse_mode="HTML")
        return

    order_id = args[0]
    platform = "telegram"
    current_key = get_current_key(platform)
    if not current_key:
        await update.message.reply_text("❌ সক্রিয় API Key নেই।")
        return

    status_data = get_order_status(current_key['key'], order_id)
    if status_data.get('error'):
        await update.message.reply_text(f"❌ {status_data['error']}")
    else:
        charge = status_data.get('charge', 'N/A')
        status = status_data.get('status', 'Unknown')
        start_count = status_data.get('start_count', 'N/A')
        remains = status_data.get('remains', 'N/A')
        await update.message.reply_text(
            f"📊 <b>অর্ডার স্ট্যাটাস</b>\n\n"
            f"🆔 অর্ডার: <code>{order_id}</code>\n"
            f"📊 স্ট্যাটাস: {status}\n"
            f"💵 খরচ: ${charge}\n"
            f"📈 শুরু: {start_count}\n"
            f"⏳ বাকি: {remains}",
            parse_mode="HTML"
        )

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    platform = "telegram"
    current = get_current_key(platform)
    if current:
        balance = check_balance(current['key'])
        update_balance(current['key'], balance)
        await update.message.reply_text(
            f"💰 <b>ব্যালেন্স</b>\n\n"
            f"📱 প্ল্যাটফর্ম: {platform.capitalize()}\n"
            f"💵 ব্যালেন্স: <code>${balance:.6f}</code>\n"
            f"📊 স্ট্যাটাস: {'✅ সক্রিয়' if balance >= config.MIN_BALANCE else '❌ কম ব্যালেন্স'}",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text("❌ কোনো সক্রিয় API Key নেই।")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orders = get_orders(update.effective_user.id, limit=10)
    if not orders:
        await update.message.reply_text("📭 আপনার কোনো অর্ডার নেই।")
        return

    text = "📋 <b>আপনার শেষ ১০টি অর্ডার:</b>\n\n"
    for order in orders:
        text += (
            f"🆔 <code>{order['order_id']}</code> | {order['platform'].capitalize()}\n"
            f"   🔢 {order['quantity']} | 📊 {order['status']}\n"
            f"   📅 {order['created_at'][:16]}\n\n"
        )
    await update.message.reply_text(text, parse_mode="HTML")

async def system_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = get_total_keys()
    active = get_active_count()
    await update.message.reply_text(
        f"📊 <b>সিস্টেম স্ট্যাটাস</b>\n\n"
        f"🔑 মোট API Keys: <code>{total}</code>\n"
        f"✅ সক্রিয় Keys: <code>{active}</code>\n"
        f"⚠️ ন্যূনতম ব্যালেন্স: <code>${config.MIN_BALANCE}</code>\n"
        f"📱 প্ল্যাটফর্ম: Telegram, Facebook, TikTok",
        parse_mode="HTML"
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
            "❌ ব্যবহার: <code>/addkey &lt;api_key&gt; &lt;platform&gt;</code>\n"
            "প্ল্যাটফর্ম: <code>telegram</code>, <code>facebook</code>, <code>tiktok</code>",
            parse_mode="HTML"
        )
        return

    key = args[0]
    platform = args[1].lower()
    valid_platforms = ['telegram', 'facebook', 'tiktok']
    if platform not in valid_platforms:
        await update.message.reply_text(
            f"❌ প্ল্যাটফর্মটি সঠিক নয়। ব্যবহার করুন: {', '.join(valid_platforms)}"
        )
        return

    if not add_api_key(key, platform):
        await update.message.reply_text("❌ এই API Key ইতিমধ্যে যোগ করা হয়েছে।")
        return

    balance = check_balance(key)
    update_balance(key, balance)
    if balance >= config.MIN_BALANCE:
        update_status(key, 'active')
        status_text = "✅ সক্রিয়"
    else:
        update_status(key, 'inactive')
        status_text = f"⚠️ নিষ্ক্রিয় (ব্যালেন্স ${balance:.6f})"

    await update.message.reply_text(
        f"✅ API Key যোগ করা হয়েছে!\n"
        f"📱 প্ল্যাটফর্ম: {platform.capitalize()}\n"
        f"💰 ব্যালেন্স: <code>${balance:.6f}</code>\n"
        f"📊 স্ট্যাটাস: {status_text}",
        parse_mode="HTML"
    )

async def activate_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ এই কমান্ডটি শুধুমাত্র অ্যাডমিনদের জন্য।")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text("❌ ব্যবহার: <code>/activatekey &lt;api_key&gt;</code>", parse_mode="HTML")
        return

    key = args[0]
    key_data = get_key_by_value(key)
    if not key_data:
        await update.message.reply_text("❌ এই API Key ডাটাবেসে নেই।")
        return

    balance = check_balance(key)
    update_balance(key, balance)
    if balance >= config.MIN_BALANCE:
        update_status(key, 'active')
        await update.message.reply_text(
            f"✅ API Key <code>{key[:10]}...</code> সক্রিয় করা হয়েছে।\n"
            f"💰 ব্যালেন্স: <code>${balance:.6f}</code>",
            parse_mode="HTML"
        )
    else:
        update_status(key, 'inactive')
        await update.message.reply_text(
            f"❌ API Key <code>{key[:10]}...</code> সক্রিয় করা সম্ভব নয়।\n"
            f"ব্যালেন্স <code>${balance:.6f}</code> যা ন্যূনতম <code>${config.MIN_BALANCE}</code> এর কম।",
            parse_mode="HTML"
        )

async def remove_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ এই কমান্ডটি শুধুমাত্র অ্যাডমিনদের জন্য।")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text("❌ ব্যবহার: <code>/removekey &lt;api_key&gt;</code>", parse_mode="HTML")
        return

    key = args[0]
    remove_api_key(key)
    await update.message.reply_text(f"✅ API Key <code>{key[:10]}...</code> রিমুভ করা হয়েছে।", parse_mode="HTML")

async def list_keys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ এই কমান্ডটি শুধুমাত্র অ্যাডমিনদের জন্য।")
        return

    keys = get_all_keys()
    if not keys:
        await update.message.reply_text("📭 কোনো API Key নেই।")
        return

    text = "🔑 <b>সব API Keys:</b>\n\n"
    for k in keys[:30]:
        status_icon = "✅" if k['status'] == 'active' else "❌"
        balance = k.get('balance', 0)
        text += f"{status_icon} <code>{k['key'][:15]}...</code> | {k['platform'].capitalize()} | ${balance:.4f}\n"
    if len(keys) > 30:
        text += f"\n... এবং আরও {len(keys)-30}টি কী আছে।"
    await update.message.reply_text(text, parse_mode="HTML")

async def check_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ এই কমান্ডটি শুধুমাত্র অ্যাডমিনদের জন্য।")
        return

    args = context.args
    if len(args) < 1:
        await update.message.reply_text("❌ ব্যবহার: <code>/checkkey &lt;api_key&gt;</code>", parse_mode="HTML")
        return

    key = args[0]
    key_data = get_key_by_value(key)
    if not key_data:
        await update.message.reply_text("❌ এই API Key ডাটাবেসে নেই।")
        return

    balance = check_balance(key)
    update_balance(key, balance)
    if balance >= config.MIN_BALANCE:
        update_status(key, 'active')
        status_text = "✅ সক্রিয়"
    else:
        update_status(key, 'inactive')
        status_text = "❌ নিষ্ক্রিয় (ব্যালেন্স কম)"

    await update.message.reply_text(
        f"🔑 API Key: <code>{key[:10]}...</code>\n"
        f"💰 ব্যালেন্স: <code>${balance:.6f}</code>\n"
        f"📊 স্ট্যাটাস: {status_text}",
        parse_mode="HTML"
    )

# ============================================================
# এরর হ্যান্ডলার
# ============================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text("⚠️ একটি ত্রুটি ঘটেছে। দয়া করে পরে আবার চেষ্টা করুন।")

# ============================================================
# কম্বাইন্ড টেক্সট হ্যান্ডলার
# ============================================================

async def handle_all_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_link'):
        await handle_link(update, context)
    elif context.user_data.get('waiting_for_quantity'):
        await handle_quantity(update, context)
    elif context.user_data.get('waiting_for_confirmation'):
        await handle_confirmation(update, context)
    else:
        # কোনো স্টেট না থাকলে কিছু করবেন না
        pass

# ============================================================
# মেইন
# ============================================================

def main():
    init_db()
    app = Application.builder().token(config.BOT_TOKEN).build()

    # ইউজার কমান্ড
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("order", order_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("sysstatus", system_status_command))

    # অ্যাডমিন কমান্ড
    app.add_handler(CommandHandler("addkey", add_key_command))
    app.add_handler(CommandHandler("removekey", remove_key_command))
    app.add_handler(CommandHandler("listkeys", list_keys_command))
    app.add_handler(CommandHandler("activatekey", activate_key_command))
    app.add_handler(CommandHandler("checkkey", check_key_command))

    # ক্যালব্যাক
    app.add_handler(CallbackQueryHandler(platform_callback, pattern="^platform_"))
    app.add_handler(CallbackQueryHandler(service_callback, pattern="^service_"))

    # টেক্সট হ্যান্ডলার (স্টেট ম্যানেজমেন্ট)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_text))

    # এরর হ্যান্ডলার
    app.add_error_handler(error_handler)

    logger.info("🤖 বট চালু হচ্ছে...")
    app.run_polling()

if __name__ == "__main__":
    main()
