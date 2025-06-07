import sqlite3
import threading
from contextlib import contextmanager
import os
from dotenv import load_dotenv

load_dotenv()
# Get API key from .env only
API_KEY = os.getenv("DEEPSEEK_API_KEY")

conn = sqlite3.connect('app.db', check_same_thread=False)
# Use thread-local storage
local = threading.local()

def get_connection():
    if not hasattr(local, 'conn'):
        local.conn = sqlite3.connect('app.db', check_same_thread=False)
    return local.conn

@contextmanager
def get_cursor():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        if conn.in_transaction:
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()

def initialize_database():
    with get_cursor() as c:
        c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            session_id TEXT UNIQUE,
            session_name TEXT,
            session_data TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            is_admin BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        # api_keys table is now only for reference. The key comes from .env and is not created/updated by users.
        c.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            username TEXT,
            used_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            reason TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS api_configurations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_name TEXT UNIQUE,
            base_url TEXT,
            api_key TEXT,
            is_active BOOLEAN DEFAULT 0,
            model_name TEXT DEFAULT 'deepseek-reasoner',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

    # Insert .env API key into api_keys table if not exists for default admin
    if API_KEY:
        with get_cursor() as c:
            c.execute('SELECT 1 FROM api_keys WHERE key = ?', (API_KEY,))
            if not c.fetchone():
                c.execute('''
                    INSERT INTO api_keys (key, username, total_tokens, is_active)
                    VALUES (?, ?, ?, 1)
                ''', (API_KEY, 'admin', 1000000))  # Example: 1M tokens quota

initialize_database()