import os
import json
import time
import datetime
import requests
import random
import string
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import firebase_admin
from firebase_admin import credentials, firestore

# ============================================================
# TWIN PACK TELEGRAM 2-BOT MIMARISI + FIREBASE FIRESTORE ENTEGRASYONU
# ============================================================

# 1. SATIS BOTU (Public Musteri Magazasi) - YENI TOKEN
SALES_BOT_TOKEN = "8608754130:AAEOjVuLKNWusYjGoWTbSNBF3olQ-GiDb2c"

# 2. LOG & BILDIRIM BOTU (Private Admin Log Bot) - YENI TOKEN
LOG_BOT_TOKEN = "8821625181:AAEVrM7HQpsZCUgupAh1_PVrug4i0Dm3_u4"

# Sizin Sahsi Telegram Chat ID'niz
ADMIN_CHAT_ID = "7049176004"

# Binance TR Gercek USDT (TRC20) Cuzdan Adresiniz
USDT_TRC20_ADDRESS = "TENBpF97XR1KVdbso4sia9eVd1xwU11FZe"

USDT_RATE = 40.0
FLOOD_COOLDOWN_SEC = 10  # Musteri flood engelleyici (10 saniye bekleme kurali)

# ------------------------------------------------------------
# FIREBASE FIRESTORE BAGLANTISI (Hem Dosyayi hem Env Var Destekler)
# ------------------------------------------------------------
db = None
try:
    # 1. RENDER.COM GUVENLI ORTAM DEGISKENI (GitHub'a dosya yuklemeden calisma)
    env_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if env_json:
        try:
            sa_dict = json.loads(env_json)
            cred = credentials.Certificate(sa_dict)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("Firebase Firestore baglantisi Environment Variable ile kuruldu.")
        except Exception as ex_env:
            print(f"Env json parse hatasi: {ex_env}")

    # 2. LOKAL YEREL DOSYA (service-account.json)
    if db is None:
        sa_path = os.path.join(os.path.dirname(__file__), "license-tools", "service-account.json")
        if not os.path.exists(sa_path):
            sa_path = os.path.join(os.path.dirname(__file__), "service-account.json")
        
        if os.path.exists(sa_path):
            cred = credentials.Certificate(sa_path)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("Firebase Firestore baglantisi service-account.json dosyasi ile kuruldu.")
        else:
            print("UYARI: service-account.json veya FIREBASE_SERVICE_ACCOUNT bulunamadi!")
except Exception as e:
    print(f"Firebase baglanti hatasi: {e}")

def save_license_to_firebase(code, duration_days):
    """Lisans kodunu aninda Firebase Firestore sunucusuna kaydeder ki kullanici uygulamada aktif edebilsin"""
    if db is None:
        print(f"HATA: Firebase DB aktif degil, {code} kaydedilemedi!")
        return False
    try:
        col_name = "licenses_" + code[:2]
        doc_ref = db.collection(col_name).document(code)
        doc_ref.set({
            "code": code,
            "used": False,
            "durationDays": int(duration_days),
            "words_avrupa": [],
            "words_anadolu": []
        })
        print(f"SUCCESS: Lisans {code} ({duration_days} gun) Firestore '{col_name}' koleksiyonuna kaydedildi.")
        return True
    except Exception as e:
        print(f"Firestore lisans kayit hatasi ({code}): {e}")
        return False

notified_codes_memory = set()

def check_and_lock_paid_notification(code):
    """Hem RAM hem Firestore uzerinden %100 TEKIL BILDIRIM KILIDI koyar (Ust uste buton basimini kesin engeller)"""
    if code in notified_codes_memory:
        return False
    notified_codes_memory.add(code)
    
    if db is not None:
        try:
            lock_ref = db.collection("notified_paid_codes").document(code)
            doc = lock_ref.get()
            if doc.exists:
                return False
            lock_ref.set({"notifiedAt": firestore.SERVER_TIMESTAMP})
        except Exception as e:
            print(f"Lock check error: {e}")
            
    return True

# ------------------------------------------------------------
# HTTP PROXY & PAKETLER
# ------------------------------------------------------------
PROXIES = None
if os.path.exists("/etc/pythonanywhere") or "PYTHONANYWHERE_DOMAIN" in os.environ:
    PROXIES = {
        "http": "http://proxy.server:3128",
        "https": "http://proxy.server:3128"
    }

session = requests.Session()
if PROXIES:
    session.proxies.update(PROXIES)
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})

PACKAGES = {
    "pkg_1w": {"name": "1 Haftalik Lisans", "price_tl": 1000, "days": 7},
    "pkg_1m": {"name": "1 Aylik Lisans", "price_tl": 3000, "days": 30},
    "pkg_2m": {"name": "2 Aylik Lisans", "price_tl": 5000, "days": 60},
    "pkg_3m": {"name": "3 Aylik Lisans", "price_tl": 7000, "days": 90},
    "pkg_6m": {"name": "6 Aylik Lisans", "price_tl": 10000, "days": 180},
    "pkg_1y": {"name": "1 Yillik Lisans", "price_tl": 15000, "days": 365},
    "pkg_unlim": {"name": "Sinirsiz Lisans", "price_tl": 25000, "days": -1}
}

pending_orders = {}
pending_approvals = {}
processed_tx_hashes = set()
processed_sales_update_ids = set()
processed_admin_update_ids = set()
user_last_click = {}  # {chat_id: timestamp} (Anti-Flood Korumasi)

def get_unique_usdt_amount(base_price_tl):
    """Ayni anda ayni paketi alan 2 kisi karismasin diye minik sent farki olusturur (25.00 USDT, 25.01 USDT vb.)"""
    base_usdt = round(base_price_tl / USDT_RATE, 2)
    offset_cents = 0.00
    while round(base_usdt + offset_cents, 2) in pending_orders:
        offset_cents += 0.01
    return round(base_usdt + offset_cents, 2)

# RENDER WEB SERVICE PORT BINDING
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - Twin Pack Sales Bot is Running")

def start_health_server():
    try:
        port = int(os.environ.get("PORT", 10000))
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        print(f"Health check server listening on port {port}...")
        server.serve_forever()
    except Exception as e:
        print(f"Health server error: {e}")

def generate_license_code():
    part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    part3 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{part1}-{part2}-{part3}"

def answer_sales_callback(callback_query_id, text=None, show_alert=False):
    url = f"https://api.telegram.org/bot{SALES_BOT_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    if show_alert:
        payload["show_alert"] = True
    try:
        session.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"answer_sales_callback error: {e}")

def answer_log_callback(callback_query_id, text=None, show_alert=False):
    url = f"https://api.telegram.org/bot{LOG_BOT_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    if show_alert:
        payload["show_alert"] = True
    try:
        session.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"answer_log_callback error: {e}")

def send_sales_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{SALES_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = session.post(url, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        print(f"Send sales message error: {e}")
        return None

def send_log_message(text, reply_markup=None):
    url = f"https://api.telegram.org/bot{LOG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = session.post(url, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        print(f"Send log message error: {e}")
        return None

def main_menu():
    keyboard = {
        "inline_keyboard": [
            [{"text": "\U0001f949 1 Haftalik (1.000 TL / ~25 USDT)", "callback_data": "buy#pkg_1w"}],
            [{"text": "\U0001f948 1 Aylik (3.000 TL / ~75 USDT)", "callback_data": "buy#pkg_1m"}],
            [{"text": "\U0001f947 2 Aylik (5.000 TL / ~125 USDT)", "callback_data": "buy#pkg_2m"}],
            [{"text": "\U0001f48e 3 Aylik (7.000 TL / ~175 USDT)", "callback_data": "buy#pkg_3m"}],
            [{"text": "\U0001f451 6 Aylik (10.000 TL / ~250 USDT)", "callback_data": "buy#pkg_6m"}],
            [{"text": "\U0001f3c6 1 Yillik (15.000 TL / ~375 USDT)", "callback_data": "buy#pkg_1y"}],
            [{"text": "\U0001f680 Sinirsiz Lisans (25.000 TL / ~625 USDT)", "callback_data": "buy#pkg_unlim"}],
            [{"text": "\U0001f4de Canli Destek / Iletisim", "url": "https://t.me/TwinPackSatis"}]
        ]
    }
    return keyboard

def deliver_license_to_customer(target_chat_id, code, pkg_name, usdt_amount, username, duration_days=30, source="OTOMATIK"):
    """Musteriye lisans kodunu teslim et, Firebase Firestore'a kaydet ve admine bildir"""
    
    # 1. KODU FIREBASE FIRESTORE SUNUCUSUNA YAZ (Uygulamada aninda aktif olsun)
    save_license_to_firebase(code, duration_days)

    # 2. Musteriye Lisans Kodunu gonder
    success_msg = (
        f"\U0001f389 <b>KRIPTO ODEMENIZ ONAYLANDI! LISANSINIZ AKTIF!</b>\n\n"
        f"\U0001f4e6 <b>Paket:</b> {pkg_name}\n"
        f"\U0001f4b5 <b>Tutar:</b> {usdt_amount} USDT\n"
        f"\U0001f511 <b>Lisans Kodunuz:</b> <code>{code}</code>\n\n"
        "<b>\U0001f4f1 KULLANIM ADIMLARI:</b>\n"
        "1. Twin Pack uygulamasini acin.\n"
        f"2. Lisans Kodu alanina <code>{code}</code> yapistirin ve <b>Aktif Et</b> butonuna basin.\n"
        "3. Otomatik hizli sisteminiz kullanima hazirdir!"
    )
    send_sales_message(target_chat_id, success_msg)
    
    log_msg = (
        f"\U0001f680 <b>{source} SATIS TAMAMLANDI!</b>\n\n"
        f"\U0001f464 <b>Musteri:</b> @{username}\n"
        f"\U0001f4e6 <b>Paket:</b> {pkg_name}\n"
        f"\U0001f4b5 <b>Tutar:</b> {usdt_amount} USDT\n"
        f"\U0001f511 <b>Teslim Edilen Kod:</b> <code>{code}</code>\n"
        f"\U0001f552 <b>Zaman:</b> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_log_msg_resp = send_log_message(log_msg)
    print(f"Log msg result: {send_log_msg_resp}")

# ============================================================
# TRON BLOCKCHAIN OTOMATIK ODEME TESPIT MOTORU
# ============================================================
def blockchain_auto_checker():
    print("TRON Blockchain Otomatik Kripto Odeme Denetleyicisi Calisiyor...")
    while True:
        try:
            url = f"https://api.trongrid.io/v1/accounts/{USDT_TRC20_ADDRESS}/transactions/trc20?limit=10"
            r = session.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if "data" in data:
                    for tx in data["data"]:
                        tx_hash = tx.get("transaction_id", "")
                        to_addr = tx.get("to", "")
                        amount_str = tx.get("value", "0")
                        decimals = int(tx.get("token_info", {}).get("decimals", 6))
                        
                        if to_addr == USDT_TRC20_ADDRESS and tx_hash not in processed_tx_hashes:
                            usdt_received = round(float(amount_str) / (10 ** decimals), 2)
                            
                            if usdt_received in pending_orders:
                                order = pending_orders[usdt_received]
                                processed_tx_hashes.add(tx_hash)
                                
                                code = order["code"]
                                pkg_days = order.get("duration_days", 30)
                                pending_approvals.pop(code, None)
                                
                                deliver_license_to_customer(
                                    order["chat_id"], code, order["pkg_name"],
                                    usdt_received, order["username"], pkg_days, "BLOCKCHAIN OTOMATIK"
                                )
                                del pending_orders[usdt_received]

        except Exception as e:
            print(f"Blockchain check error: {e}")
            
        time.sleep(20)

# ============================================================
# LOG BOT ADMIN ONAY DINLEYICISI (Manuel Tek Tus Onay)
# ============================================================
def extract_pkg_and_code(cb_data):
    matched_pkg_key = None
    for k in PACKAGES.keys():
        if k in cb_data:
            matched_pkg_key = k
            break
            
    if not matched_pkg_key:
        matched_pkg_key = "pkg_1m"
        
    raw_after_pkg = cb_data
    if "#" + matched_pkg_key + "#" in cb_data:
        raw_after_pkg = cb_data.split("#" + matched_pkg_key + "#")[-1]
    elif "_" + matched_pkg_key + "_" in cb_data:
        raw_after_pkg = cb_data.split("_" + matched_pkg_key + "_")[-1]
    else:
        parts = cb_data.replace("#", "_").split("_")
        raw_after_pkg = parts[-1]
        
    for p_id in ["1w_", "1m_", "2m_", "3m_", "6m_", "1y_", "unlim_"]:
        if raw_after_pkg.startswith(p_id):
            raw_after_pkg = raw_after_pkg.replace(p_id, "")
            
    return matched_pkg_key, raw_after_pkg.strip()

def admin_approval_listener():
    print("Admin Manuel Onay Dinleyicisi Aktif...")
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{LOG_BOT_TOKEN}/getUpdates?offset={offset}&timeout=0"
            r = session.get(url, timeout=8)
            if r.status_code == 200:
                data = r.json()
                if "result" in data:
                    for update in data["result"]:
                        up_id = update.get("update_id")
                        offset = max(offset, up_id + 1)
                        
                        if up_id in processed_admin_update_ids:
                            continue
                        processed_admin_update_ids.add(up_id)
                        
                        if "callback_query" in update:
                            cb = update["callback_query"]
                            cb_id = cb.get("id")
                            if cb_id:
                                answer_log_callback(cb_id, "Islem alindi...")

                            cb_data = cb.get("data", "")
                            
                            if cb_data.startswith("approve#") or cb_data.startswith("approve_"):
                                pkg_key, code = extract_pkg_and_code(cb_data)
                                
                                target_chat_id = "1066847598"
                                parts = cb_data.replace("#", "_").split("_")
                                if len(parts) >= 2 and parts[1].isdigit():
                                    target_chat_id = parts[1]
                                    
                                pkg = PACKAGES.get(pkg_key, {})
                                pkg_days = pkg.get("days", 30)
                                usdt_amount = round(pkg.get("price_tl", 0) / USDT_RATE, 2)
                                
                                order = pending_approvals.get(code, {})
                                username = order.get("username", "Kullanici")
                                pkg_name = pkg.get("name", "Lisans Paketi")
                                
                                deliver_license_to_customer(
                                    target_chat_id, code, pkg_name,
                                    usdt_amount, username, pkg_days, "MANUEL ADMIN ONAY"
                                )
                                
                                pending_approvals.pop(code, None)
                                pending_orders.pop(usdt_amount, None)
                                send_log_message(f"\u2705 <code>{code}</code> kodlu lisans Firebase'e eklendi ve musterisine teslim edildi!")
                                        
                            elif cb_data.startswith("reject#") or cb_data.startswith("reject_"):
                                pkg_key, code = extract_pkg_and_code(cb_data)
                                target_chat_id = "1066847598"
                                parts = cb_data.replace("#", "_").split("_")
                                if len(parts) >= 2 and parts[1].isdigit():
                                    target_chat_id = parts[1]
                                    
                                send_sales_message(target_chat_id, "\u274c <b>Odemeniz dogrulanamadi.</b>\nLutfen dogru tutari gonderdiginizden emin olun veya destek hattimizla iletisime gecin.")
                                pending_approvals.pop(code, None)
                                send_log_message(f"\u274c <code>{code}</code> kodlu siparis reddedildi.")

        except Exception as e:
            print(f"Admin listener error: {e}")
            
        time.sleep(3)

# ============================================================
# SATIS BOTU MUSTERI DINLEYICISI
# ============================================================
def process_updates():
    offset = 0
    print("Twin Pack 100% Otomatik Satis Botu Aktif...")
    
    t_health = threading.Thread(target=start_health_server, daemon=True)
    t_health.start()

    t1 = threading.Thread(target=blockchain_auto_checker, daemon=True)
    t1.start()
    
    t2 = threading.Thread(target=admin_approval_listener, daemon=True)
    t2.start()
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{SALES_BOT_TOKEN}/getUpdates?offset={offset}&timeout=0"
            r = session.get(url, timeout=8)
            if r.status_code == 200:
                data = r.json()
                if "result" in data:
                    for update in data["result"]:
                        up_id = update.get("update_id")
                        offset = max(offset, up_id + 1)
                        
                        if up_id in processed_sales_update_ids:
                            continue
                        processed_sales_update_ids.add(up_id)
                        
                        if "message" in update:
                            msg = update["message"]
                            chat_id = str(msg["chat"]["id"])
                            text = msg.get("text", "")
                            username = msg.get("from", {}).get("username", "Kullanici")
                            
                            if text == "/start" or text == "/satinal":
                                welcome_msg = (
                                    f"<b>\U0001f44b Merhaba @{username}! Twin Pack Kripto Otomatik Lisans Magazasina Hos Geldiniz.</b>\n\n"
                                    "Ihtiyaciniza uygun lisans paketini asagidan secerek <b>USDT (TRC20) Kripto ile odemenizi gonderin.</b>\n\n"
                                    "\U0001f916 <i>Blockchain sistemi odemeyi otomatik algilar ve lisans kodunuzu saniyeler icinde teslim eder!</i>\n\n"
                                    "\u2b07\ufe0f <b>KOPYALANABILIR USDT (TRC20) CUZDAN ADRESINIZ:</b>"
                                )
                                send_sales_message(chat_id, welcome_msg, main_menu())
                                # Kopyalanabilir tekil cuzdan adresi mesaji
                                send_sales_message(chat_id, f"<code>{USDT_TRC20_ADDRESS}</code>")

                        elif "callback_query" in update:
                            cb = update["callback_query"]
                            cb_id = cb.get("id")
                            chat_id = str(cb["message"]["chat"]["id"])
                            cb_data = cb.get("data", "")
                            username = cb.get("from", {}).get("username", "Kullanici")
                            
                            # 10 SANIYELIK MUSTERI FLOOD ENGELLEYICI (COOLDOWN KONTROLU)
                            now = time.time()
                            last_click = user_last_click.get(chat_id, 0)
                            if (now - last_click) < FLOOD_COOLDOWN_SEC:
                                remaining_sec = int(FLOOD_COOLDOWN_SEC - (now - last_click))
                                if cb_id:
                                    answer_sales_callback(cb_id, f"\u26a0\ufe0f Lutfen yeni secim yapabilmek icin {remaining_sec} saniye bekleyin!", show_alert=True)
                                continue
                            
                            user_last_click[chat_id] = now
                            if cb_id:
                                answer_sales_callback(cb_id, "Isleminiz alindi...")

                            if cb_data.startswith("buy#") or cb_data.startswith("buy_"):
                                pkg_key, _ = extract_pkg_and_code(cb_data)
                                if pkg_key in PACKAGES:
                                    pkg = PACKAGES[pkg_key]
                                    price_tl = pkg["price_tl"]
                                    usdt_amount = get_unique_usdt_amount(price_tl)
                                    code = generate_license_code()
                                    duration_days = pkg["days"]
                                    
                                    pending_orders[usdt_amount] = {
                                        "chat_id": chat_id,
                                        "code": code,
                                        "pkg_name": pkg["name"],
                                        "username": username,
                                        "duration_days": duration_days
                                    }
                                    
                                    pending_approvals[code] = {
                                        "chat_id": chat_id,
                                        "pkg_name": pkg["name"],
                                        "username": username,
                                        "usdt_amount": usdt_amount,
                                        "pkg_key": pkg_key,
                                        "duration_days": duration_days
                                    }
                                    
                                    pay_msg1 = (
                                        f"<b>\U0001f6d2 SECILEN PAKET: {pkg['name']}</b>\n"
                                        f"\U0001f4b0 <b>Gonderilecek Tam Tutar:</b> <code>{usdt_amount}</code> USDT ({price_tl} TL)\n\n"
                                        "\U0001f310 <b>USDT (TRC20) ODEME ADRESINIZ (Dokunarak Kopyalayin):</b>"
                                    )
                                    send_sales_message(chat_id, pay_msg1)
                                    
                                    # TEK TIKLA %100 PANOTA KOPYALANABILIR CUZDAN ADRESI MESAJI
                                    send_sales_message(chat_id, f"<code>{USDT_TRC20_ADDRESS}</code>")
                                    
                                    pay_msg2 = (
                                        f"\U0001f511 <b>Rezerve Edilen Kodunuz:</b> <code>{code}</code>\n\n"
                                        "\u26a1 <b>%100 Otomatik Sistem:</b> Parayi gonderdiginiz an Blokzincir sistemi 15 saniyede algilar ve kodunuzu otomatik teslim eder!"
                                    )
                                    
                                    confirm_kb = {
                                        "inline_keyboard": [
                                            [{"text": "\u2705 ODEMEYI GONDERDIM (ONAYA GONDER)", "callback_data": f"paid#{pkg_key}#{code}"}],
                                            [{"text": "\U0001f504 Odeme Bekleniyor (Otomatik Kontrol)", "callback_data": "waiting"}],
                                            [{"text": "\U0001f519 Ana Menuye Don", "callback_data": "back_to_menu"}]
                                        ]
                                    }
                                    send_sales_message(chat_id, pay_msg2, confirm_kb)
                                    
                            elif cb_data.startswith("paid#") or cb_data.startswith("paid_"):
                                pkg_key, code = extract_pkg_and_code(cb_data)
                                
                                # RAM + FIREBASE KİLİDİ (ÇİFT BİLDİRİMİ KESİN ENGELLER)
                                if not check_and_lock_paid_notification(code):
                                    continue
                                
                                order = pending_approvals.get(code, {})
                                usdt_amount = order.get("usdt_amount")
                                if not usdt_amount:
                                    pkg = PACKAGES.get(pkg_key, {})
                                    usdt_amount = round(pkg.get("price_tl", 0) / USDT_RATE, 2)
                                price_tl = PACKAGES.get(pkg_key, {}).get("price_tl", 0)
                                pkg_name = PACKAGES.get(pkg_key, {}).get("name", "Lisans Paketi")
                                
                                send_sales_message(chat_id, f"\u2705 <b>Odeme bildiriminiz alindi!</b>\nLisans kodunuz (<code>{code}</code>) kontrol edildikten hemen sonra aktif olacaktir.\n\n\u23f3 <i>Blockchain otomatik kontrol de devam ediyor...</i>")
                                
                                admin_msg = (
                                    f"\U0001f4b0 <b>YENI ODEME BILDIRIMI!</b>\n\n"
                                    f"\U0001f464 <b>Musteri:</b> @{username} (ID: <code>{chat_id}</code>)\n"
                                    f"\U0001f4e6 <b>Paket:</b> {pkg_name}\n"
                                    f"\U0001f4b5 <b>Beklenen Tutar:</b> {usdt_amount} USDT ({price_tl} TL)\n"
                                    f"\U0001f511 <b>Uretilen Kod:</b> <code>{code}</code>\n\n"
                                    f"\u2b07\ufe0f Cuzdan bakiyenizi kontrol edip odeme geldiyse <b>ONAYLA</b> tusuna basin."
                                )
                                
                                admin_kb = {
                                    "inline_keyboard": [
                                        [{"text": f"\u2705 ONAYLA VE KODU TESLIM ET ({code})", "callback_data": f"approve#{chat_id}#{pkg_key}#{code}"}],
                                        [{"text": f"\u274c REDDET", "callback_data": f"reject#{chat_id}#{code}"}]
                                    ]
                                }
                                send_log_resp = send_log_message(admin_msg, admin_kb)
                                print(f"Admin log send response: {send_log_resp}")

                            elif cb_data == "back_to_menu":
                                send_sales_message(chat_id, "<b>Ana Menu:</b>", main_menu())

        except Exception as e:
            print(f"Loop error: {e}")
            
        time.sleep(3)

if __name__ == "__main__":
    process_updates()
