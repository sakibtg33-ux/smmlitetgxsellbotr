import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = [int(id) for id in os.environ.get("ADMIN_IDS", "123456789").split(",")]

# SMMLite API
SMM_API_URL = "https://smmlite.com/api/v2"
MIN_BALANCE = 0.0003  # 0.0003$ এর কম হলে কী রিমুভ হবে

# প্ল্যাটফর্ম অনুযায়ী সার্ভিস আইডি (আপনার smmlite.com থেকে নিতে হবে)
SERVICES = {
    "telegram": {
        "followers": 1,      # আপনার smmlite.com সার্ভিস আইডি
        "members": 2,
        "reactions": 3,
    },
    "facebook": {
        "page_likes": 10,
        "post_likes": 11,
        "followers": 12,
    },
    "tiktok": {
        "followers": 20,
        "likes": 21,
        "views": 22,
    }
}
