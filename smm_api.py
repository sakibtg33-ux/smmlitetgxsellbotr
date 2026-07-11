import requests
import logging
import json
import time

logger = logging.getLogger(__name__)

SMM_API_URL = "https://smmlite.com/api/v2"

# ক্যাশে
_service_cache = {}
_cache_time = {}

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
                    "message": data.get('error', 'Unknown error')
                }
        else:
            return {
                "status": "error",
                "message": f"HTTP {response.status_code}: {response.text}"
            }
    except Exception as e:
        logger.error(f"Order error: {e}")
        return {"status": "error", "message": str(e)}

def get_order_status(api_key, order_id):
    """অর্ডার স্ট্যাটাস চেক করে"""
    try:
        url = f"{SMM_API_URL}/status"
        params = {
            "key": api_key,
            "action": "status",
            "order": order_id
        }
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'error' in data:
                return {'error': data['error']}
            return data
        else:
            return {'error': f"HTTP {response.status_code}"}
    except Exception as e:
        return {'error': str(e)}

def fetch_services(api_key=None):
    """
    smmlite.com থেকে সব সার্ভিস লিস্ট ফেচ করে
    API Key না দিলে ডিফল্ট রিটার্ন করবে
    """
    try:
        if api_key:
            url = f"{SMM_API_URL}/services"
            params = {"key": api_key}
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    services = {}
                    for svc in data:
                        service_id = str(svc.get('service', ''))
                        service_name = svc.get('name', f'Service {service_id}')
                        category = svc.get('category', 'Other')
                        if service_id:
                            services[service_id] = {
                                'name': service_name,
                                'category': category,
                                'rate': svc.get('rate', 0),
                                'min': svc.get('min', 0),
                                'max': svc.get('max', 0)
                            }
                    return services
                elif isinstance(data, dict):
                    services_list = data.get('services', [])
                    services = {}
                    for svc in services_list:
                        service_id = str(svc.get('service', ''))
                        service_name = svc.get('name', f'Service {service_id}')
                        if service_id:
                            services[service_id] = {
                                'name': service_name,
                                'category': svc.get('category', 'Other'),
                                'rate': svc.get('rate', 0),
                                'min': svc.get('min', 0),
                                'max': svc.get('max', 0)
                            }
                    return services
    except Exception as e:
        logger.error(f"Error fetching services: {e}")

    # ফেচ করতে ব্যর্থ হলে ডিফল্ট রিটার্ন
    return get_default_services()

def get_default_services():
    """ডিফল্ট সার্ভিস লিস্ট (যখন API Key দিয়ে ফেচ করা সম্ভব নয়)"""
    return {
        # Telegram
        "1": {"name": "Telegram Followers", "category": "Telegram"},
        "2": {"name": "Telegram Members", "category": "Telegram"},
        "3": {"name": "Telegram Reactions", "category": "Telegram"},
        "4": {"name": "Telegram Views", "category": "Telegram"},
        "391": {"name": "🇷🇺 Telegram Post Views - [REAL RUSSIA USER] [1M/DAY] SUPER INSTANT - $0.03 per 1000", "category": "Telegram"},
        # Facebook
        "10": {"name": "Facebook Page Likes", "category": "Facebook"},
        "11": {"name": "Facebook Post Likes", "category": "Facebook"},
        "12": {"name": "Facebook Followers", "category": "Facebook"},
        "13": {"name": "Facebook Comments", "category": "Facebook"},
        # TikTok
        "20": {"name": "TikTok Followers", "category": "TikTok"},
        "21": {"name": "TikTok Likes", "category": "TikTok"},
        "22": {"name": "TikTok Views", "category": "TikTok"},
        "23": {"name": "TikTok Shares", "category": "TikTok"},
        # Instagram
        "30": {"name": "Instagram Followers", "category": "Instagram"},
        "31": {"name": "Instagram Likes", "category": "Instagram"},
        "32": {"name": "Instagram Views", "category": "Instagram"},
        # YouTube
        "40": {"name": "YouTube Subscribers", "category": "YouTube"},
        "41": {"name": "YouTube Views", "category": "YouTube"},
        "42": {"name": "YouTube Likes", "category": "YouTube"},
        # Twitter
        "50": {"name": "Twitter Followers", "category": "Twitter"},
        "51": {"name": "Twitter Likes", "category": "Twitter"},
        "52": {"name": "Twitter Retweets", "category": "Twitter"},
    }

def get_services_by_platform_simple(platform, api_key=None):
    """একটি নির্দিষ্ট প্ল্যাটফর্মের সার্ভিস লিস্ট রিটার্ন করে"""
    all_services = fetch_services(api_key)
    # ক্যাটাগরি অনুযায়ী ফিল্টার
    platform_map = {
        'telegram': 'Telegram',
        'facebook': 'Facebook',
        'tiktok': 'TikTok',
        'instagram': 'Instagram',
        'youtube': 'YouTube',
        'twitter': 'Twitter'
    }
    category = platform_map.get(platform.lower())
    if not category:
        return {}

    result = {}
    for service_id, info in all_services.items():
        if info.get('category') == category:
            result[service_id] = info['name']
    return result
