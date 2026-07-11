import sqlite3
import json
from datetime import datetime

DB_FILE = "bot_data.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            platform TEXT NOT NULL,
            balance REAL DEFAULT 0,
            status TEXT DEFAULT 'active',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            service TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            link TEXT NOT NULL,
            order_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

# API Keys
def add_api_key(key, platform):
    conn = get_db()
    try:
        conn.execute("INSERT INTO api_keys (key, platform) VALUES (?, ?)", (key, platform))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_api_key(key):
    conn = get_db()
    conn.execute("DELETE FROM api_keys WHERE key = ?", (key,))
    conn.commit()
    conn.close()

def get_all_keys():
    conn = get_db()
    rows = conn.execute("SELECT * FROM api_keys ORDER BY added_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_active_keys():
    conn = get_db()
    rows = conn.execute("SELECT * FROM api_keys WHERE status = 'active'").fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_balance(key, balance):
    conn = get_db()
    conn.execute("UPDATE api_keys SET balance = ? WHERE key = ?", (balance, key))
    conn.commit()
    conn.close()

def update_status(key, status):
    conn = get_db()
    conn.execute("UPDATE api_keys SET status = ? WHERE key = ?", (status, key))
    conn.commit()
    conn.close()

def get_current_key(platform):
    """একটি প্ল্যাটফর্মের জন্য সক্রিয় কী খুঁজে বের করে"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM api_keys WHERE platform = ? AND status = 'active' LIMIT 1",
        (platform,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def get_next_key(platform):
    """ব্যালেন্স কমে গেলে পরবর্তী কী নির্বাচন করে"""
    conn = get_db()
    # active keys থেকে র্যান্ডম একটি
    rows = conn.execute(
        "SELECT * FROM api_keys WHERE platform = ? AND status = 'active' ORDER BY RANDOM() LIMIT 1",
        (platform,)
    ).fetchall()
    conn.close()
    return dict(rows[0]) if rows else None

def get_total_keys():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
    conn.close()
    return count

def get_active_count():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM api_keys WHERE status = 'active'").fetchone()[0]
    conn.close()
    return count

# Orders
def add_order(user_id, platform, service, quantity, link, order_id=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO orders (user_id, platform, service, quantity, link, order_id) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, platform, service, quantity, link, order_id)
    )
    conn.commit()
    conn.close()

def get_orders(user_id=None, limit=20):
    conn = get_db()
    if user_id:
        rows = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Settings
def get_setting(key, default=None):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = get_db()
    conn.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()
