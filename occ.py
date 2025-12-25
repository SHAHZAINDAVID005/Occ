#!/usr/bin/env python3
import requests
import json
import re
import time
import logging
import threading
import os
import urllib3
from datetime import datetime
from telegram import Bot 
import asyncio 

# Kashe gargadin InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================== CONFIG ==================
EMAIL = "alijoiya658@gmail.com"
PASSWORD = "Zainjoiya21"

# Tabbatar ka yi amfani da Token din da kake gani a logs (8487752681)
BOT_TOKEN = "8421734960:AAE8JAdY7wPOSrACgWblJnM9q8zL8bHaO24"
CHAT_ID = "-1003243421314"
ADMIN_ID = "6190125375"

LOGIN_URL = "https://www.orangecarrier.com/login"
SOCKET_URL = "https://hub.orangecarrier.com/socket.io/"
LIVE_CALL_ENDPOINT = "https://www.orangecarrier.com/live/calls/lives"
SOUND_ENDPOINT = "https://www.orangecarrier.com/live/calls/sound"

DOWNLOAD_DIR = "downloads"
SEEN_FILE = "seen.json"
FAILED_FILE = "failed.json"
LASTCALL_FILE = "lastcall.json"
STATS_FILE = "stats.json"

POLLING_INTERVAL = 2 
TELEGRAM_POLL_TIMEOUT = 30 
RECONNECT_DELAY = 5 
# ============================================

# === LOGGING SETUP ===
# Mun saita shi ya nuna INFO kawai, sannan mun boye kuskuren wasu libraries
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
# ===========================================

COUNTRY_FLAGS = {
    'AF': '🇦🇫', 'AL': '🇦🇱', 'DZ': '🇩🇿', 'US': '🇺🇸', 'NG': '🇳🇬', 'GB': '🇬🇧', 'FR': '🇫🇷', 'DE': '🇩🇪', 'IN': '🇮🇳',
    'JP': '🇯🇵', 'CN': '🇨🇳', 'RU': '🇷🇺', 'BR': '🇧🇷', 'AR': '🇦🇷', 'MX': '🇲🇽', 'CA': '🇨🇦', 'AU': '🇦🇺', 'IT': '🇮🇹',
    'ES': '🇪🇸', 'SE': '🇸🇪', 'PK': '🇵🇰', 'BD': '🇧🇩', 'ID': '🇮🇩', 'EG': '🇪🇬', 'ZA': '🇿🇦', 'KE': '🇰🇪', 'GH': '🇬🇭'
}

def get_flag(country_code):
    return COUNTRY_FLAGS.get(country_code.upper(), '❓')

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except:
            return default
    return default

def save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except:
        pass

def mask_number(cli):
    str_cli = str(cli).replace("+", "")
    if len(str_cli) >= 7 and str_cli.isdigit():
        return f"{str_cli[:4]}****{str_cli[-3:]}"
    return str_cli

def create_caption(did_number, duration_sec, country, country_code):
    now = datetime.now().strftime("%I:%M:%S %p")
    masked_number = mask_number(did_number)
    flag = get_flag(country_code)
    caption = (
        f"🔥 <b>NEW CALL {country.upper()} {flag} RECEIVED</b> ✨\n"
        f"__________________________________\n"
        f"🌍 <b>Country:</b> {country} {flag}\n"
        f"📞 <b>DID Number:</b> +{masked_number}\n" 
        f"⏳ <b>Duration:</b> {duration_sec}s\n"
        f"⏰ <b>Time:</b> {now}"
    )
    return caption

def download_audio(session, call_id, uuid):
    if not uuid: return None
    audio_url = f"{SOUND_ENDPOINT}?id={call_id}&uuid={uuid}"
    filepath = os.path.join(DOWNLOAD_DIR, f"{call_id}-{uuid}.mp3")
    try:
        r = session.get(audio_url, stream=True, timeout=30, verify=False)
        r.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk: f.write(chunk)
        return filepath
    except:
        return None

async def process_command_async(bot, message):
    chat_id = message.chat_id
    user_id = message.from_user.id
    text = message.text
    if user_id != ADMIN_ID: return
    stats = load_json(STATS_FILE, {"success": 0, "failed": 0})
    if text == "/stats":
        msg = f"📊 <b>Bot Statistics</b>\n\n✅ Success: {stats['success']}\n❌ Failed: {stats['failed']}"
        await bot.send_message(chat_id, msg, parse_mode="HTML")

class OrangeCarrier:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        self.bot = Bot(BOT_TOKEN) 
        self.sid = None
        self.last_update_id = 0 
        self.seen_calls = load_json(SEEN_FILE, [])
        self.stats = load_json(STATS_FILE, {"success": 0, "failed": 0})
        self.failed_calls = load_json(FAILED_FILE, [])
        self.running = True

    def login(self):
        try:
            r = self.session.get(LOGIN_URL, timeout=30, verify=False)
            token = re.search(r'name="_token" value="([^"]+)"', r.text)
            if not token: return False
            csrf = token.group(1)
            payload = {"_token": csrf, "email": EMAIL, "password": PASSWORD}
            r2 = self.session.post(LOGIN_URL, data=payload, allow_redirects=False, timeout=30, verify=False)
            if r2.status_code in (200, 302):
                logging.info("✅ Login successful")
                return True
            return False
        except:
            return False
            
    def socket_handshake(self):
        try:
            r = self.session.get(SOCKET_URL, params={"EIO": "4", "transport": "polling"}, timeout=30, verify=False) 
            data = json.loads(r.text[1:])
            self.sid = data["sid"]
            logging.info(f"✅ Socket SID: {self.sid}")
            return True
        except:
            return False

    def join_room(self):
        try:
            params = {"EIO": "4", "transport": "polling", "sid": self.sid}
            self.session.post(SOCKET_URL, params=params, data="40", verify=False)
            join_msg = (f'42["join_user_room",{{"room":"user:{EMAIL}:orange:internal"}}]')
            self.session.post(SOCKET_URL, params=params, data=join_msg, verify=False)
            logging.info("✅ Joined user room")
        except:
            pass

    def send_pong(self):
        try:
            self.session.post(SOCKET_URL, params={"EIO": "4", "transport": "polling", "sid": self.sid}, data="3", verify=False)
            logging.info("🏓 PONG") # Mun maida shi INFO don ka gani
        except:
            pass
            
    def _fetch_live_call_details(self, call_id):
        try:
            r = self.session.post(LIVE_CALL_ENDPOINT, data={"id": call_id}, timeout=10, verify=False)
            if r.status_code == 200: return r.json() 
        except:
            return None

    async def telegram_command_poller_async(self): 
        while self.running:
            try:
                updates = await self.bot.get_updates(offset=self.last_update_id + 1, timeout=TELEGRAM_POLL_TIMEOUT)
                for update in updates:
                    if update.message and update.message.text:
                        await process_command_async(self.bot, update.message) 
                    self.last_update_id = max(self.last_update_id, update.update_id)
            except:
                await asyncio.sleep(RECONNECT_DELAY)
            await asyncio.sleep(1) 
            
    def telegram_command_poller_wrapper(self):
        asyncio.run(self.telegram_command_poller_async())

    def poll(self):
        try:
            r = self.session.get(SOCKET_URL, params={"EIO": "4", "transport": "polling", "sid": self.sid}, timeout=30, verify=False)
            content = r.text.strip()
            if content == "2":
                self.send_pong()
                return True
            for part in content.split('\n'):
                if part.startswith("42"):
                    payload = json.loads(part[2:])
                    event, data = payload[0], payload[1]
                    if event == "new_call":
                        threading.Thread(target=self.process_new_call, args=(data.get("id"), data.get("did"), data.get("uuid"), data.get("country"), data.get("country_code")), daemon=True).start()
            return True
        except:
            return False

    def process_new_call(self, call_id, did_number, uuid, country, country_code):
        if call_id in self.seen_calls: return
        logging.info(f"📞 New Call: {country} ({did_number})")
        
        # Sako na farko
        async def send_initial():
            return await self.bot.send_message(chat_id=CHAT_ID, text=f"🟢 <b>Call Ending Soon...</b>\n🌍 {country} {get_flag(country_code)}", parse_mode="HTML")
        
        init_msg = None
        try: init_msg = asyncio.run(send_initial())
        except: pass

        duration = 0
        call_ended = False
        start_wait = time.time()
        while not call_ended and (time.time() - start_wait) < 180:
            call_data = self._fetch_live_call_details(call_id)
            if call_data and call_data.get("duration", 0) > 0:
                duration = call_data["duration"]
                call_ended = True
                break
            time.sleep(2) 
        
        self.seen_calls.append(call_id)
        save_json(SEEN_FILE, self.seen_calls)

        if duration > 0:
            if init_msg:
                try: asyncio.run(self.bot.delete_message(chat_id=CHAT_ID, message_id=init_msg.message_id))
                except: pass
            
            audio_path = download_audio(self.session, call_id, uuid)
            caption = create_caption(did_number, duration, country, country_code)
            async def send_final():
                if audio_path:
                    with open(audio_path, "rb") as af: await self.bot.send_audio(chat_id=CHAT_ID, audio=af, caption=caption, parse_mode="HTML")
                else: await self.bot.send_message(chat_id=CHAT_ID, text=caption, parse_mode="HTML")
            asyncio.run(send_final())
            self.stats["success"] += 1
        else:
            self.stats["failed"] += 1
        save_json(STATS_FILE, self.stats)

    def start(self):
        if not self.login(): return
        self.socket_handshake()
        self.join_room()
        threading.Thread(target=self.telegram_command_poller_wrapper, daemon=True).start()
        logging.info("🚀 Monitor Active...")
        while self.running:
            if not self.poll():
                time.sleep(RECONNECT_DELAY)
                self.socket_handshake()
                self.join_room()
            time.sleep(POLLING_INTERVAL)

if __name__ == "__main__":
    if not os.path.exists(DOWNLOAD_DIR): os.makedirs(DOWNLOAD_DIR)
    try: OrangeCarrier().start()
    except KeyboardInterrupt: logging.info("Stopped.")
