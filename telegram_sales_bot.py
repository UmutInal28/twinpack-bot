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
# ============================================================

# 1. SATIS BOTU (Public Müşteri Mağazası)
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

pending_orders = {}
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

def send_log_message(text):
    url = f"https://api.telegram.org/bot{LOG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        r = session.post(url, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        print(f"Send log message error: {e}")
        return None

def main_menu():
    keyboard = {
        "inline_keyboard": [
            [{"text": "🥉 1 Haftalik (1.000 TL / ~25 USDT)", "callback_data": "buy_pkg_1w"}],
            [{"text": "🥈 1 Aylik (3.000 TL / ~75 USDT)", "callback_data": "buy_pkg_1m"}],
            [{"text": "🥇 2 Aylik (5.000 TL / ~125 USDT)", "callback_data": "buy_pkg_2m"}],
            [{"text": "💎 3 Aylik (7.000 TL / ~175 USDT)", "callback_data": "buy_pkg_3m"}],
            [{"text": "👑 6 Aylik (10.000 TL / ~250 USDT)", "callback_data": "buy_pkg_6m"}],
            [{"text": "🏆 1 Yillik (15.000 TL / ~375 USDT)", "callback_data": "buy_pkg_1y"}],
            [{"text": "🚀 Sinirsiz Lisans (25.000 TL / ~625 USDT)", "callback_data": "buy_pkg_unlim"}],
            [{"text": "📞 Canli Destek / Iletisim", "url": "https://t.me/TwinPackSatis"}]
        ]
    }
    return keyboard

# ============================================================
# TRON BLOCKCHAIN OTOMATIK ODEME TESPIT MOTORU
# ============================================================
def blockchain_auto_checker():
    print("⛓️ TRON Blockchain Otomatik Kripto Odeme Denetleyicisi Calisiyor...")
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
                                
                                target_chat_id = order["chat_id"]
                                code = order["code"]
                                pkg_name = order["pkg_name"]
                                username = order["username"]
                                
                                # 1. MUSTERIYE OTOMATIK KOD TESLIM ET (Satis Botundan)
                                success_msg = (
                                    f"🎉 <b>KRIPTO ODEMENIZ BLOCKCHAIN UZERINDEN ANINDA ONAYLANDI!</b>\n\n"
                                    f"📦 <b>Paket:</b> {pkg_name}\n"
                                    f"💵 <b>Alinan Tutar:</b> {usdt_received} USDT\n"
                                    f"🔑 <b>Lisans Kodunuz:</b> <code>{code}</code>\n\n"
                                    "<b>📱 KULLANIM ADIMLARI:</b>\n"
                                    "1. Twin Pack uygulamasini acin.\n"
                                    f"2. Lisans Kodu alanina <code>{code}</code> yapistirin ve <b>Aktif Et</b> butonuna basin.\n"
                                    "3. Otomatik hizli sisteminiz kullanima hazirdir!"
                                )
                                send_sales_message(target_chat_id, success_msg)
                                
                                # 2. SADECE SIZE OZEL LOG BOTUNA SATIS BILDIRIMI GONDER
                                log_msg = (
                                    f"🚀 <b>%100 OTOMATIK KRIPTO SATISI GERCEKLESTI!</b>\n\n"
                                    f"👤 <b>Musteri:</b> @{username}\n"
                                    f"📦 <b>Paket:</b> {pkg_name}\n"
                                    f"💵 <b>Gelen Tutar:</b> {usdt_received} USDT\n"
                                    f"🔑 <b>Uretilen ve Teslim Edilen Kod:</b> <code>{code}</code>\n"
                                    f"🔗 <b>TX Hash:</b> <code>{tx_hash}</code>"
                                )
                                send_log_message(log_msg)
                                
                                del pending_orders[usdt_received]

        except Exception as e:
            print(f"Blockchain check error: {e}")
            
        time.sleep(20)

def process_updates():
    offset = 0
    print("🤖 Twin Pack %100 Otomatik Satis Botu Aktif...")
    
    t = threading.Thread(target=blockchain_auto_checker, daemon=True)
    t.start()
    
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
                                    f"<b>👋 Merhaba @{username}! Twin Pack Kripto Otomatik Lisans Magazasina Hos Geldiniz.</b>\n\n"
                                    "Ihtiyaciniza uygun lisans paketini asagidan secerek <b>USDT (TRC20) Kripto ile odemenizi gonderin.</b>\n\n"
                                    "🤖 <i>Siz parayi gonderdiginiz an Blockchain sistemi odemeyi otomatik algilar ve siz hic beklemeden lisans kodunuzu ekraniniza dusurur!</i>"
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
                                    
                                    pending_orders[usdt_amount] = {
                                        "chat_id": chat_id,
                                        "code": code,
                                        "pkg_name": pkg["name"],
                                        "username": username
                                    }
                                    
                                    pay_msg = (
                                        f"<b>🛒 SECILEN PAKET: {pkg['name']}</b>\n"
                                        f"💰 <b>Gonderilecek Tam Tutar:</b> <code>{usdt_amount}</code> USDT\n\n"
                                        "-------------------------------------------\n"
                                        "🌐 <b>USDT (TRC20) ODEME ADRESINIZ:</b>\n"
                                        f"<code>{USDT_TRC20_ADDRESS}</code>\n"
                                        "(Kopyalamak icin adresin uzerine dokunun)\n\n"
                                        "⚡ <b>%100 Otomatik Sistem:</b> Parayi gonderdiginiz an Blokzincir sistemi 15 saniyede algilar ve kodunuzu otomatik teslim eder!\n"
                                        "-------------------------------------------\n"
                                        f"🔑 <b>Rezerve Edilen Kodunuz:</b> <code>{code}</code>"
                                    )
                                    
                                    confirm_kb = {
                                        "inline_keyboard": [
                                            [{"text": "🔄 Odeme Bekleniyor (Otomatik Kontrol Ediliyor...)", "callback_data": "waiting"}],
                                            [{"text": "🔙 Ana Menuye Don", "callback_data": "back_to_menu"}]
                                        ]
                                    }
                                    send_sales_message(chat_id, pay_msg, confirm_kb)

                            elif cb_data == "back_to_menu":
                                send_sales_message(chat_id, "<b>Ana Menu:</b>", main_menu())

        except Exception as e:
            print(f"Loop error: {e}")
            
        time.sleep(3)

if __name__ == "__main__":
    process_updates()
