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
