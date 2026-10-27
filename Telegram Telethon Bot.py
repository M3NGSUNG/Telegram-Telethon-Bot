#!/usr/bin/env python3
"""
Bank AutoSum Userbot - Telethon
Supports ACLEDA + ABA
"""

import os, re, json, asyncio, threading, base64
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import calendar
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.custom import Button

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

# Function to safely load SESSION_STRING
def get_session_string():
    raw = os.getenv("SESSION_STRING", "").strip()
    
    if not raw:
        print("⚠️  SESSION_STRING is empty")
        return ""
    
    # If it already starts with "1", it's already decoded
    if raw.startswith("1"):
        print("✅ Using SESSION_STRING (already decoded)")
        return raw
    
    # Try to decode from base64url
    try:
        # Add padding if needed
        padding = 4 - (len(raw) % 4)
        if padding and padding != 4:
            raw = raw + ("=" * padding)
        
        decoded = base64.b64decode(raw).decode('utf-8')
        print("✅ SESSION_STRING decoded from base64url")
        return decoded
    except Exception as e:
        print(f"❌ Failed to decode SESSION_STRING: {e}")
        return ""

SESSION_STRING = get_session_string()

# Khmer months
KH_MONTHS = ["","មករា","កុម្ភៈ","មីនា","មេសា","ឧសភា","មិថុនា",
             "កក្កដា","សីហា","កញ្ញា","តុលា","វិច្ឆិកា","ធ្នូ"]
EN_MONTHS = ["", "January", "February", "March", "April", "May", "June",
             "July", "August", "September", "October", "November", "December"]

# Bank message patterns
PATTERNS = [
    (r"បានទទួល.*?([\d,]+(?:\.\d+)?)\s*រៀល", "KHR"),
    (r"បានទទួល.*?([\d,]+(?:\.\d+)?)\s*ដុល្លារ", "USD"),
    (r"[៛₸]([\d,]+(?:\.\d+)?)\s*paid\s+by", "KHR"),
    (r"\$([\d,]+(?:\.\d+)?)\s*paid\s+by", "USD"),
    (r"([\d,]+(?:\.\d+)?)\s*KHR\s*paid\s+by", "KHR"),
    (r"received\s+\$?\s*([\d,]+(?:\.\d+)?)", "USD"),
]

BANK_KEYWORDS = [
    "បានទទួល", "រៀល", "ដុល្លារ", "STAND:", "ACLEDA", "KHQR",
    "paid by", "ABA PAY", "PayWay", "APV:", "Trx. ID", "៛", "₸"
]

DATA_FILE = "data.json"
DATA = {}

# ── Parsing ───────────────────────────────────────────────────────────────────
def parse_bank_message(text):
    for pattern, currency in PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if m:
            try:
                amount = float(m.group(1).replace(",", ""))
                if amount > 0:
                    return (amount, 0.0) if currency == "USD" else (0.0, amount)
            except:
                continue
    return 0.0, 0.0

def is_bank_message(text):
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in BANK_KEYWORDS)

# ── Storage ───────────────────────────────────────────────────────────────────
def load():
    global DATA
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                DATA = json.load(f)
        except:
            DATA = {}
    else:
        DATA = {}

def save():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(DATA, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Save error: {e}")

def record(chat_id, date_str, usd, khr):
    key = str(chat_id)
    if key not in DATA:
        DATA[key] = {}
    if date_str not in DATA[key]:
        DATA[key][date_str] = {"usd": 0.0, "khr": 0.0, "count": 0}
    
    DATA[key][date_str]["usd"] += usd
    DATA[key][date_str]["khr"] += khr
    DATA[key][date_str]["count"] += 1
    save()
    print(f"  💾 Saved! KHR={int(khr):,} USD={usd:.2f} | {date_str}")

def day_row(chat_id, date_str):
    return DATA.get(str(chat_id), {}).get(date_str, {"usd": 0.0, "khr": 0.0, "count": 0})

def month_rows(chat_id, year, month):
    txns = DATA.get(str(chat_id), {})
    rows = []
    days_in_month = calendar.monthrange(year, month)[1]
    for d in range(1, days_in_month + 1):
        key = f"{year}-{month:02d}-{d:02d}"
        v = txns.get(key, {"usd": 0.0, "khr": 0.0, "count": 0})
        rows.append((d, v["usd"], v["khr"], v["count"]))
    return rows

def week_rows(chat_id, start):
    txns = DATA.get(str(chat_id), {})
    rows = []
    for i in range(7):
        dt = start + timedelta(days=i)
        key = dt.strftime("%Y-%m-%d")
        v = txns.get(key, {"usd": 0.0, "khr": 0.0, "count": 0})
        rows.append((dt, v["usd"], v["khr"], v["count"]))
    return rows

# ── Reports ───────────────────────────────────────────────────────────────────
def rpt_day(chat_id, dt):
    v = day_row(chat_id, dt.strftime("%Y-%m-%d"))
    return (
        f"📅 ថ្ងៃទី {dt.strftime('%d/%m/%Y')}\n"
        f"{'─'*28}\n"
        f"💵 USD  : ${v['usd']:,.2f}\n"
        f"💴 KHR  : ៛{int(v['khr']):,}\n"
        f"🔢 ចំនួន : {v['count']} ប្រតិបត្តិការ"
    )

def rpt_week(chat_id, start):
    rows = week_rows(chat_id, start)
    end = start + timedelta(days=6)
    lines = [
        f"📊 ប្រចាំសប្តាហ៍",
        f"{start.strftime('%d/%m')} – {end.strftime('%d/%m/%Y')}",
        "",
        f"{'ថ្ងៃ':<12} {'USD':>8} {'KHR':>10} {'ចំ':>3}",
        "─"*36,
    ]
    t_u = t_k = t_c = 0
    for dt, u, k, c in rows:
        t_u += u
        t_k += k
        t_c += c
        lines.append(f"{dt.strftime('%a %d/%m'):<12} {u:>8.2f} {int(k):>10,} {c:>3}")
    lines += ["─"*36, f"{'សរុប':<12} {t_u:>8.2f} {int(t_k):>10,} {t_c:>3}"]
    return "```\n" + "\n".join(lines) + "\n```"

def rpt_month(chat_id, year, month):
    rows = month_rows(chat_id, year, month)
    lines = [
        f"📊 ប្រចាំខែ {KH_MONTHS[month]} {year}",
        "",
        f"{'ថ្ងៃ':>4} {'USD':>10} {'KHR':>10} {'ចំ':>4}",
        "─"*32,
    ]
    t_u = t_k = t_c = 0
    for d, u, k, c in rows:
        t_u += u
        t_k += k
        t_c += c
        lines.append(f"{d:>4} {u:>10.2f} {int(k):>10,} {c:>4}")
    lines += ["─"*32, f"{'សរុប':>4} {t_u:>10.2f} {int(t_k):>10,} {t_c:>4}"]
    return "```\n" + "\n".join(lines) + "\n```"

# ── Keyboards ─────────────────────────────────────────────────────────────────
def kb_main():
    return [
        [Button.inline("📅 ប្រចាំថ្ងៃ", b"m_daily"),
         Button.inline("📆 ប្រចាំសប្តាហ៍", b"m_week_0")],
        [Button.inline("🗓 ប្រចាំខែ", b"m_month_select"),
         Button.inline("❌ បិទ", b"m_close")],
    ]

def kb_daily(sel):
    today = datetime.now().date()
    row = []
    for i in range(3):
        d = today - timedelta(days=i)
        mark = "✅" if d == sel.date() else ""
        row.append(Button.inline(
            f"{mark}{d.strftime('%b %d')}",
            f"day_{d.strftime('%Y-%m-%d')}".encode()
        ))
    return [
        row,
        [Button.inline("📅 ថ្ងៃផ្សេងទៀត", b"day_pick"),
         Button.inline("🔙 ត្រឡប់ក្រោយ", b"back")],
    ]

def kb_day_select(year, month):
    days_in_month = calendar.monthrange(year, month)[1]
    buttons = []
    row = []
    for d in range(1, days_in_month + 1):
        row.append(Button.inline(
            str(d),
            f"day_{year}-{month:02d}-{d:02d}".encode()
        ))
        if len(row) == 7:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    prev_m, prev_y = (month - 1, year) if month > 1 else (12, year - 1)
    next_m, next_y = (month + 1, year) if month < 12 else (1, year + 1)
    buttons.append([
        Button.inline("⬅", f"day_cal_{prev_y}_{prev_m}".encode()),
        Button.inline(f"{KH_MONTHS[month]} {year}", f"m_year_{year}".encode()),
        Button.inline("➡", f"day_cal_{next_y}_{next_m}".encode())
    ])
    buttons.append([Button.inline("🔙 ត្រឡប់ក្រោយ", b"m_daily")])
    return buttons

def kb_week(offset):
    today = datetime.now()
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=offset)
    end = start + timedelta(days=6)
    nxt = max(0, offset - 1)
    return [
        [Button.inline(f"📌 {start.strftime('%d/%m')}–{end.strftime('%d/%m')}", b"noop")],
        [Button.inline("⬅ មុន", f"m_week_{offset+1}".encode()),
         Button.inline("ថ្ងៃនេះ", b"m_week_0"),
         Button.inline("➡ បន្ទាប់", f"m_week_{nxt}".encode())],
        [Button.inline("🔙 ត្រឡប់ក្រោយ", b"back")],
    ], start

def kb_month_select(year):
    buttons = []
    row = []
    for m in range(1, 13):
        row.append(Button.inline(EN_MONTHS[m], f"m_month_{year}_{m}".encode()))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        Button.inline(f"⬅ {year-1}", f"m_year_{year-1}".encode()),
        Button.inline(f"{year+1} ➡", f"m_year_{year+1}".encode())
    ])
    buttons.append([Button.inline("🔙 ត្រឡប់ក្រោយ", b"back")])
    return buttons

def kb_month_report(year, month):
    return [
        [Button.inline("📅 ជ្រើសរើសខែផ្សេង", f"m_year_{year}".encode())],
        [Button.inline("🔙 ត្រឡប់ក្រោយ", b"back")],
    ]

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    load()
    print(f"📂 Loaded data for {len(DATA)} chats")

    if SESSION_STRING:
        print("🔑 Using SESSION_STRING (cloud mode)")
        userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
        await userbot.start()
    elif PHONE:
        print("📱 Using phone login (PC mode)")
        userbot = TelegramClient("userbot_session", API_ID, API_HASH)
        await userbot.start(phone=PHONE)
    else:
        print("❌ No SESSION_STRING or PHONE configured!")
        return

    bot = TelegramClient(StringSession(), API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)

    print("✅ Userbot connected")
    print("✅ Bot connected")
    print("🤖 Reading ACLEDA & ABA messages 24/7...")
    print("─" * 50)

    @userbot.on(events.NewMessage())
    async def on_message(event):
        text = event.raw_text or ""
        if not text or not is_bank_message(text):
            return

        usd, khr = parse_bank_message(text)
        if usd == 0 and khr == 0:
            return

        chat_id = event.chat_id
        date_str = datetime.now().strftime("%Y-%m-%d")
        record(chat_id, date_str, usd, khr)

        parts = []
        if usd: parts.append(f"💵 ${usd:,.2f}")
        if khr: parts.append(f"💴 ៛{int(khr):,}")
        try:
            await event.reply("✅ បានកត់ត្រា: " + " | ".join(parts))
        except Exception as e:
            print(f"   Reply error: {e}")

    @bot.on(events.NewMessage(pattern="/start"))
    async def on_start(event):
        await event.reply(
            "👋 សូមស្វាគមន៍!\n\n"
            "🤖 Bot អានសារ ACLEDA & ABA ដោយស្វ័យប្រវត្តិ\n"
            "💰 រាប់ KHR និង USD ដោយស្វ័យប្រវត្តិ\n\n"
            "ប្រើ /menu ដើម្បីមើលសង្ខេប"
        )

    @bot.on(events.NewMessage(pattern="/menu"))
    async def on_menu(event):
        await event.reply("📋 សូមជ្រើសរើស:", buttons=kb_main())

    @bot.on(events.CallbackQuery())
    async def on_callback(event):
        await event.answer()
        data = event.data.decode()
        cid = event.chat_id
        now = datetime.now()

        try:
            if data == "back":
                await event.edit("📋 សូមជ្រើសរើស:", buttons=kb_main())
            elif data == "m_close":
                await event.delete()
            elif data == "noop":
                return
            elif data == "m_daily":
                await event.edit(rpt_day(cid, now), buttons=kb_daily(now))
            elif data.startswith("day_") and not data.startswith("day_cal_") and data != "day_pick":
                dt = datetime.strptime(data[4:], "%Y-%m-%d")
                await event.edit(rpt_day(cid, dt), buttons=kb_daily(dt))
            elif data == "day_pick":
                await event.edit(
                    f"📅 ជ្រើសរើសថ្ងៃ: **{KH_MONTHS[now.month]} {now.year}**",
                    buttons=kb_day_select(now.year, now.month),
                    parse_mode="md"
                )
            elif data.startswith("day_cal_"):
                _, _, y, m = data.split("_")
                year, month = int(y), int(m)
                await event.edit(
                    f"📅 ជ្រើសរើសថ្ងៃ: **{KH_MONTHS[month]} {year}**",
                    buttons=kb_day_select(year, month),
                    parse_mode="md"
                )
            elif data.startswith("m_week_"):
                offset = int(data.split("_")[2])
                kb, start = kb_week(offset)
                await event.edit(rpt_week(cid, start), buttons=kb, parse_mode="md")
            elif data == "m_month_select":
                year = now.year
                await event.edit(
                    f"ជ្រើសរើសខែ: **{year}**",
                    buttons=kb_month_select(year),
                    parse_mode="md"
                )
            elif data.startswith("m_year_"):
                year = int(data.split("_")[2])
                await event.edit(
                    f"ជ្រើសរើសខែ: **{year}**",
                    buttons=kb_month_select(year),
                    parse_mode="md"
                )
            elif data.startswith("m_month_"):
                parts = data.split("_")
                year = int(parts[2])
                month = int(parts[3])
                await event.edit(
                    rpt_month(cid, year, month),
                    buttons=kb_month_report(year, month),
                    parse_mode="md"
                )
        except Exception as e:
            err = str(e).lower()
            if "not modified" not in err and "message is not modified" not in err:
                print(f"Button error: {e}")

    await userbot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
