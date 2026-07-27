import os
import json
import time
import datetime
import requests
import random
import string
import threading

# ============================================================
# TWIN PACK TELEGRAM 2-BOT MIMARISI
# OTOMATIK BLOCKCHAIN + MANUEL TEK TUS ONAY SISTEMI
# ============================================================

# 1. SATIS BOTU (Public Musteri Magazasi)
SALES_BOT_TOKEN = "8608754130:AAHG2twApEYgiLWP3tBrqG6NQz27dHZDZEw"

# 2. LOG & BILDIRIM BOTU (Private Admin Log Bot)
LOG_BOT_TOKEN = "8821625181:AAFYLo2uDzV46ZHR0vdcVeNOBPF0q0QLkKw"

# Sizin Sahsi Telegram Chat ID'niz
ADMIN_CHAT_ID = "7049176004"

# Binance TR Gercek USDT (TRC20) Cuzdan Adresiniz
USDT_TRC20_ADDRESS = "TENBpF97XR1KVdbso4sia9eVd1xwU11FZe"

USDT_RATE = 40.0

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
    "pkg_unlim": {"name": "Sinirsiz Lisans", "price_tl": 25000, "days": 36500}
}

# Bekleyen Siparisler: {usdt_amount: order_info} (Blockchain icin)
pending_orders = {}
# Bekleyen Manuel Onaylar: {code: order_info} (Admin tek tus onay icin)
pending_approvals = {}
processed_tx_hashes = set()

def generate_license_code():
    part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    part3 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{part1}-{part2}-{part3}"

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
            [{"text": "\U0001f949 1 Haftalik (1.000 TL / ~25 USDT)", "callback_data": "buy_pkg_1w"}],
            [{"text": "\U0001f948 1 Aylik (3.000 TL / ~75 USDT)", "callback_data": "buy_pkg_1m"}],
            [{"text": "\U0001f947 2 Aylik (5.000 TL / ~125 USDT)", "callback_data": "buy_pkg_2m"}],
            [{"text": "\U0001f48e 3 Aylik (7.000 TL / ~175 USDT)", "callback_data": "buy_pkg_3m"}],
            [{"text": "\U0001f451 6 Aylik (10.000 TL / ~250 USDT)", "callback_data": "buy_pkg_6m"}],
            [{"text": "\U0001f3c6 1 Yillik (15.000 TL / ~375 USDT)", "callback_data": "buy_pkg_1y"}],
            [{"text": "\U0001f680 Sinirsiz Lisans (25.000 TL / ~625 USDT)", "callback_data": "buy_pkg_unlim"}],
            [{"text": "\U0001f4de Canli Destek / Iletisim", "url": "https://t.me/TwinPackSatis"}]
        ]
    }
    return keyboard

def deliver_license_to_customer(target_chat_id, code, pkg_name, usdt_amount, username, source="OTOMATIK"):
    """Musteriye lisans kodunu teslim et ve admine bildir"""
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
    send_log_message(log_msg)

# ============================================================
# TRON BLOCKCHAIN OTOMATIK ODEME TESPIT MOTORU
# ============================================================
def blockchain_auto_checker():
    print("\u26d3\ufe0f TRON Blockchain Otomatik Kripto Odeme Denetleyicisi Calisiyor...")
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
                                # Manuel onay havuzundan da kaldir
                                pending_approvals.pop(code, None)
                                
                                deliver_license_to_customer(
                                    order["chat_id"], code, order["pkg_name"],
                                    usdt_received, order["username"], "BLOCKCHAIN OTOMATIK"
                                )
                                del pending_orders[usdt_received]

        except Exception as e:
            print(f"Blockchain check error: {e}")
            
        time.sleep(20)

# ============================================================
# LOG BOT ADMIN ONAY DINLEYICISI (Manuel Tek Tus Onay)
# ============================================================
def admin_approval_listener():
    print("\U0001f6e1\ufe0f Admin Manuel Onay Dinleyicisi Aktif...")
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{LOG_BOT_TOKEN}/getUpdates?offset={offset}&timeout=0"
            r = session.get(url, timeout=8)
            if r.status_code == 200:
                data = r.json()
                if "result" in data:
                    for update in data["result"]:
                        offset = update["update_id"] + 1
                        
                        if "callback_query" in update:
                            cb = update["callback_query"]
                            cb_data = cb.get("data", "")
                            
                            # MANUEL ONAY: approve_CHATID_PKGKEY_CODE
                            if cb_data.startswith("approve_"):
                                parts = cb_data.split("_", 3)
                                if len(parts) == 4:
                                    target_chat_id = parts[1]
                                    pkg_key = parts[2]
                                    code = parts[3]
                                    
                                    if code in pending_approvals:
                                        order = pending_approvals[code]
                                        pkg = PACKAGES.get(pkg_key, {})
                                        usdt_amount = round(pkg.get("price_tl", 0) / USDT_RATE, 2)
                                        
                                        deliver_license_to_customer(
                                            target_chat_id, code, order["pkg_name"],
                                            usdt_amount, order["username"], "MANUEL ADMIN ONAY"
                                        )
                                        
                                        # Havuzlardan temizle
                                        del pending_approvals[code]
                                        pending_orders.pop(usdt_amount, None)
                                    else:
                                        send_log_message(f"\u26a0\ufe0f <code>{code}</code> kodlu siparis zaten onaylandi veya bulunamadi.")
                                        
                            elif cb_data.startswith("reject_"):
                                parts = cb_data.split("_", 2)
                                if len(parts) == 3:
                                    target_chat_id = parts[1]
                                    code = parts[2]
                                    
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
    print("\U0001f916 Twin Pack %100 Otomatik Satis Botu Aktif...")
    
    # Arka plan threadleri baslat
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
                        offset = update["update_id"] + 1
                        
                        if "message" in update:
                            msg = update["message"]
                            chat_id = str(msg["chat"]["id"])
                            text = msg.get("text", "")
                            username = msg.get("from", {}).get("username", "Kullanici")
                            
                            if text == "/start" or text == "/satinal":
                                welcome_msg = (
                                    f"<b>\U0001f44b Merhaba @{username}! Twin Pack Kripto Otomatik Lisans Magazasina Hos Geldiniz.</b>\n\n"
                                    "Ihtiyaciniza uygun lisans paketini asagidan secerek <b>USDT (TRC20) Kripto ile odemenizi gonderin.</b>\n\n"
                                    "\U0001f916 <i>Blockchain sistemi odemeyi otomatik algilar ve lisans kodunuzu saniyeler icinde teslim eder!</i>"
                                )
                                send_sales_message(chat_id, welcome_msg, main_menu())

                        elif "callback_query" in update:
                            cb = update["callback_query"]
                            chat_id = str(cb["message"]["chat"]["id"])
                            cb_data = cb.get("data", "")
                            username = cb.get("from", {}).get("username", "Kullanici")
                            
                            if cb_data.startswith("buy_"):
                                pkg_key = cb_data.replace("buy_", "")
                                if pkg_key in PACKAGES:
                                    pkg = PACKAGES[pkg_key]
                                    price_tl = pkg["price_tl"]
                                    usdt_amount = round(price_tl / USDT_RATE, 2)
                                    code = generate_license_code()
                                    
                                    # Blockchain otomatik takip havuzuna ekle
                                    pending_orders[usdt_amount] = {
                                        "chat_id": chat_id,
                                        "code": code,
                                        "pkg_name": pkg["name"],
                                        "username": username
                                    }
                                    
                                    # Manuel onay havuzuna da ekle
                                    pending_approvals[code] = {
                                        "chat_id": chat_id,
                                        "pkg_name": pkg["name"],
                                        "username": username,
                                        "usdt_amount": usdt_amount,
                                        "pkg_key": pkg_key
                                    }
                                    
                                    pay_msg = (
                                        f"<b>\U0001f6d2 SECILEN PAKET: {pkg['name']}</b>\n"
                                        f"\U0001f4b0 <b>Gonderilecek Tam Tutar:</b> <code>{usdt_amount}</code> USDT\n\n"
                                        "-------------------------------------------\n"
                                        "\U0001f310 <b>USDT (TRC20) ODEME ADRESINIZ:</b>\n"
                                        f"<code>{USDT_TRC20_ADDRESS}</code>\n"
                                        "(Kopyalamak icin adresin uzerine dokunun)\n\n"
                                        "\u26a1 <b>%100 Otomatik Sistem:</b> Parayi gonderdiginiz an Blokzincir sistemi 15 saniyede algilar ve kodunuzu otomatik teslim eder!\n"
                                        "-------------------------------------------\n"
                                        f"\U0001f511 <b>Rezerve Edilen Kodunuz:</b> <code>{code}</code>"
                                    )
                                    
                                    confirm_kb = {
                                        "inline_keyboard": [
                                            [{"text": "\u2705 ODEMEYI GONDERDIM (ONAYA GONDER)", "callback_data": f"paid_{pkg_key}_{code}"}],
                                            [{"text": "\U0001f504 Odeme Bekleniyor (Otomatik Kontrol)", "callback_data": "waiting"}],
                                            [{"text": "\U0001f519 Ana Menuye Don", "callback_data": "back_to_menu"}]
                                        ]
                                    }
                                    send_sales_message(chat_id, pay_msg, confirm_kb)
                                    
                            elif cb_data.startswith("paid_"):
                                # Musteri "Odemeyi Gonderdim" dedi -> Admine tek tus onay gonder
                                parts = cb_data.split("_", 2)
                                if len(parts) == 3:
                                    pkg_key = parts[1]
                                    code = parts[2]
                                    
                                    send_sales_message(chat_id, f"\u2705 <b>Odeme bildiriminiz alindi!</b>\nLisans kodunuz (<code>{code}</code>) kontrol edildikten hemen sonra aktif olacaktir.\n\n\u23f3 <i>Blockchain otomatik kontrol de devam ediyor...</i>")
                                    
                                    pkg = PACKAGES.get(pkg_key, {})
                                    usdt_amount = round(pkg.get("price_tl", 0) / USDT_RATE, 2)
                                    
                                    # ADMINE LOG BOTU UZERINDEN TEK TUS ONAY GONDER
                                    admin_msg = (
                                        f"\U0001f4b0 <b>YENI ODEME BILDIRIMI!</b>\n\n"
                                        f"\U0001f464 <b>Musteri:</b> @{username} (ID: <code>{chat_id}</code>)\n"
                                        f"\U0001f4e6 <b>Paket:</b> {pkg.get('name')}\n"
                                        f"\U0001f4b5 <b>Beklenen Tutar:</b> {usdt_amount} USDT ({pkg.get('price_tl')} TL)\n"
                                        f"\U0001f511 <b>Uretilen Kod:</b> <code>{code}</code>\n\n"
                                        f"\u2b07\ufe0f Cuzdan bakiyenizi kontrol edip odeme geldiyse <b>ONAYLA</b> tusuna basin."
                                    )
                                    
                                    admin_kb = {
                                        "inline_keyboard": [
                                            [{"text": f"\u2705 ONAYLA VE KODU TESLIM ET ({code})", "callback_data": f"approve_{chat_id}_{pkg_key}_{code}"}],
                                            [{"text": f"\u274c REDDET ({code})", "callback_data": f"reject_{chat_id}_{code}"}]
                                        ]
                                    }
                                    send_log_message(admin_msg, admin_kb)

                            elif cb_data == "back_to_menu":
                                send_sales_message(chat_id, "<b>Ana Menu:</b>", main_menu())

        except Exception as e:
            print(f"Loop error: {e}")
            
        time.sleep(3)

if __name__ == "__main__":
    process_updates()
