import requests
import json
import time
import logging

logger = logging.getLogger(__name__)

SMM_API_URL = "https://smmlite.com/api/v2"

def check_balance(api_key):
    """API Key-এর ব্যালেন্স চেক করে"""
    try:
        url = f"{SMM_API_URL}/balance"
        params = {"key": api_key}
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return float(data.get('balance', 0))
        else:
            logger.error(f"Balance check failed: {response.text}")
            return 0.0
    except Exception as e:
        logger.error(f"Balance check error: {e}")
        return 0.0

def place_order(api_key, service_id, link, quantity):
    """অর্ডার প্লেস করে"""
    try:
        url = f"{SMM_API_URL}/order"
        params = {
            "key": api_key,
            "service": service_id,
            "link": link,
            "quantity": quantity
        }
        response = requests.post(url, data=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get('order'):
                return {
                    "status": "success",
                    "order_id": data['order']
                }
            else:
                return {
                    "status": "error",
                    "message": data.get('error', 'অজানা ত্রুটি')
                }
        else:
            return {
                "status": "error",
                "message": f"HTTP {response.status_code}: {response.text}"
            }
    except Exception as e:
        logger.error(f"Order error: {e}")
        return {"status": "error", "message": str(e)}

def get_services(platform):
    """প্ল্যাটফর্ম অনুযায়ী সার্ভিস লিস্ট"""
    # এটি আপনার smmlite.com অ্যাকাউন্ট অনুযায়ী কাস্টমাইজ করুন
    services = {
        "telegram": {
            "1": "Telegram Followers",
            "2": "Telegram Members",
            "3": "Telegram Reactions",
        },
        "facebook": {
            "10": "Facebook Page Likes",
            "11": "Facebook Post Likes",
            "12": "Facebook Followers",
        },
        "tiktok": {
            "20": "TikTok Followers",
            "21": "TikTok Likes",
            "22": "TikTok Views",
        }
    }
    return services.get(platform, {})
