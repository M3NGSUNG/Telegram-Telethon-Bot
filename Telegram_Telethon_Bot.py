#!/usr/bin/env python3
"""
Bank AutoSum Userbot - Telethon
Supports ACLEDA + ABA
Storage: Supabase (single file, no db.py needed)

Fixes:
- Better amount patterns (including *13,000 paid by)
- Always store under the userbot's own user ID so /menu always shows correct totals
- Better logging when a bank message is seen but amount cannot be parsed
"""

import os, re, asyncio, threading, base64
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import calendar
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.custom import Button
from supabase import create_client

# ── Web Server ────────────────────────────────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, *args):
        pass

def run_web_server():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"🌐 Web server on port {port}")
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ── Configuration ─────────────────────────────────────────────────────────────
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
PHONE = os.getenv("PHONE", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")  # service_role key, server-side only

if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("❌ SUPABASE_URL and SUPABASE_KEY must be set in environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
TABLE = "daily_totals"

def get_session_string():
    raw = os.getenv("SESSION_STRING", "").strip()
    if not raw:
        print("⚠️  SESSION_STRING is empty")
        return ""
    if raw.startswith("1"):
        print("✅ Using SESSION_STRING (already decoded)")
        return raw
    try:
        padding = 4 - (len(raw) % 4)
        if padding and padding != 4:
            raw = raw + ("=" * padding)
        decoded = base64.b64decode(raw).decode("utf-8")
        print("✅ SESSION_STRING decoded from base64url")
        return decoded
    except Exception as e:
        print(f"❌ Failed to decode SESSION_STRING: {e}")
        return ""

SESSION_STRING = get_session_string()

# Global: will be set after login so we always store under the same ID
OWNER_ID = None

# Khmer months
KH_MONTHS = ["","មករា","កុម្ភៈ","មីនា","មេសា","ឧសភា","មិថុនា",
             "កក្កដា","សីហា","កញ្ញា","តុលា","វិច្ឆិកា","ធ្នូ"]
EN_MONTHS = ["", "January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]

# Bank message patterns (improved)
PATTERNS = [
    # Khmer ACLEDA style
    (r"បានទទួល.*?([\d,]+(?:\.\d+)?)\s*រៀល", "KHR"),
    (r"បានទទួល.*?([\d,]+(?:\.\d+)?)\s*ដុល្លារ", "USD"),

    # Currency symbol + paid by
    (r"[៛₸*]([\d,]+(?:\.\d+)?)\s*paid\s+by", "KHR"),   # *13,000 paid by  / ៛13,000 paid by
    (r"\$([\d,]+(?:\.\d+)?)\s*paid\s+by", "USD"),

    # Explicit currency
    (r"([\d,]+(?:\.\d+)?)\s*KHR\s*paid\s+by", "KHR"),
    (r"([\d,]+(?:\.\d+)?)\s*USD\s*paid\s+by", "USD"),

    # Fallback: number + paid by  → treat as KHR (most common for ABA)
    (r"([\d,]+(?:\.\d+)?)\s*paid\s+by", "KHR"),

    # Other
    (r"received\s+\$?\s*([\d,]+(?:\.\d+)?)", "USD"),
    (r"amount[:\s]+([\d,]+(?:\.\d+)?)", "KHR"),
]

BANK_KEYWORDS = [
    "បានទទួល", "រៀល", "ដុល្លារ", "STAND:", "ACLEDA", "KHQR",
    "paid by", "ABA PAY", "PayWay", "APV:", "Trx. ID", "Trx.ID",
    "៛", "₸", "ABA", "ACLEDA Bank"
]

# ── Parsing ───────────────────────────────────────────────────────────────────
def parse_bank_message(text):
    for pattern, currency in PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if m:
            try:
                amount = float(m.group(1).replace(",", ""))
                if amount > 0:
                    return (amount, 0.0) if currency == "USD" else (0.0, amount)
            except Exception:
                continue
    return 0.0, 0.0

def is_bank_message(text):
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in BANK_KEYWORDS)

# ── Storage (Supabase) ────────────────────────────────────────────────────────
EMPTY = {"usd": 0.0, "khr": 0.0, "count": 0}

def record(chat_id, date_str, usd, khr):
    key = {"chat_id": str(chat_id), "day": date_str}
    res = 
