import os
import random
import re
import json
import logging
import threading
from functools import wraps

import telebot
from faker import Faker
from PIL import Image, ImageDraw, ImageFont

# --- Konfigurasi Bot & Umum ---
TELEGRAM_BOT_TOKEN = "8283460062:AAEeHKAySmtKhoatbzlRJYhUPHiytZ6OHPo" # Ganti dengan token Anda
ADMIN_ID = 7680006005 # Ganti dengan ID admin Anda
MEMBERS_FILE = "members.json"
RESULT_DIR = "result" # Folder untuk menyimpan hasil gambar sementara

# --- Konfigurasi Generator Gambar Lokal ---
FONT_PATH = "PlayfairDisplay-VariableFont_wght.ttf"
IMAGE_PATH = "mentahan.jpg"
FONT_SIZE = 50
TEXT_COLOR = "#051d40"
CENTER_X = 675
POS_Y = 200
NAME_BG_WIDTH = 900    # Lebar area yang dibersihkan untuk nama
NAME_BG_HEIGHT = 140   # Tinggi area yang dibersihkan untuk nama

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Inisialisasi Faker untuk nama Indonesia
fake = Faker("id_ID")

# --- Manajemen Member & Anti-Spam ---
def load_members():
    if not os.path.exists(MEMBERS_FILE): return set()
    try:
        with open(MEMBERS_FILE, 'r') as f: return set(json.load(f))
    except (json.JSONDecodeError, FileNotFoundError): return set()

def save_members(member_ids):
    with open(MEMBERS_FILE, 'w') as f: json.dump(list(member_ids), f, indent=4)

MEMBER_IDS = load_members()
user_tasks = set()

# --- Inisialisasi Bot ---
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# --- Decorators untuk Hak Akses ---
def admin_required(func):
    @wraps(func)
    def wrapper(message):
        if message.from_user.id != ADMIN_ID:
            bot.reply_to(message, "🚫 Perintah ini hanya untuk Admin.")
            return
        return func(message)
    return wrapper

def member_required(func):
    @wraps(func)
    def wrapper(message):
        if message.from_user.id != ADMIN_ID and message.from_user.id not in MEMBER_IDS:
            bot.reply_to(message, "🚫 Anda tidak memiliki akses untuk menggunakan bot ini.")
            return
        return func(message)
    return wrapper

# --- Fungsi Logika Inti ---
def clean_name(name: str) -> str:
    """Membersihkan nama dari gelar dan karakter yang tidak diinginkan."""
    name = re.sub(r"[.,]", "", name)
    name = re.sub(r"\b(Drs?|Ir|H|Prof|S|M|Bapak|Ibu)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip()
    return name

def generate_image_local(first_name: str, last_name: str, user_id: int) -> str | None:
    """
    Membuat gambar secara lokal dengan nama yang diberikan.
    Mengembalikan path file jika berhasil, None jika gagal.
    """
    full_name = f"{first_name} {last_name}"
    logger.info(f"[LOKAL] Merender nama: {full_name} untuk user {user_id}")

    try:
        if not os.path.exists(FONT_PATH):
            raise FileNotFoundError(f"Font tidak ditemukan: {FONT_PATH}")
        if not os.path.exists(IMAGE_PATH):
            raise FileNotFoundError(f"Gambar template tidak ditemukan: {IMAGE_PATH}")
        
        os.makedirs(RESULT_DIR, exist_ok=True)

        base = Image.open(IMAGE_PATH).convert("RGB")
        draw = ImageDraw.Draw(base)
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)

        # Bersihkan area nama dengan kotak tetap agar teks lama tidak tersisa
        bg_left = CENTER_X - (NAME_BG_WIDTH / 2)
        bg_top = POS_Y - (NAME_BG_HEIGHT / 2)
        bg_right = CENTER_X + (NAME_BG_WIDTH / 2)
        bg_bottom = POS_Y + (NAME_BG_HEIGHT / 2)
        draw.rectangle([bg_left, bg_top, bg_right, bg_bottom], fill="white")

        # Hitung posisi agar teks berada di tengah
        text_bbox = draw.textbbox((0, 0), full_name, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        x = CENTER_X - (text_width / 2)
        y = POS_Y

        # Tulis teks nama
        draw.text((x, y), full_name, font=font, fill=TEXT_COLOR)

        # Simpan hasil dengan nama file unik
        output_name = f"{user_id}_hasil.jpg"
        output_path = os.path.join(RESULT_DIR, output_name)
        base.save(output_path, format="JPEG", quality=95)
        logger.info(f"[LOKAL] Gambar tersimpan di: {output_path}")
        return output_path

    except FileNotFoundError as e:
        logger.error(f"Error file tidak ditemukan saat generate gambar: {e}")
        return None
    except Exception as e:
        logger.error(f"Error umum saat generate gambar: {e}")
        return None

# --- Fungsi Worker untuk Thread ---
def process_generation_task(message, processing_message):
    user_id = message.from_user.id
    output_image_path = None  # Inisialisasi path gambar

    try:
        # 1. **PERUBAHAN DI SINI**: Generate nama sampai panjang totalnya 13 karakter
        logger.info(f"Mencari nama dengan panjang 13 karakter untuk user {user_id}...")
        while True:
            # Generate nama acak baru
            full_name_candidate = clean_name(fake.name())
            parts = full_name_candidate.split()
            
            # Pastikan nama memiliki setidaknya dua bagian (depan & belakang)
            if len(parts) >= 2:
                firstName = parts[0]
                lastName = parts[-1]
                
                # Cek apakah panjang gabungan (nama_depan + spasi + nama_belakang) tepat 13
                if len(firstName) + len(lastName) + 1 == 13:
                    logger.info(f"Nama ditemukan: '{firstName} {lastName}'")
                    break # Keluar dari loop jika panjangnya sudah sesuai

        # 2. Panggil fungsi generator gambar lokal
        output_image_path = generate_image_local(firstName, lastName, user_id)
        if not output_image_path:
            bot.edit_message_text("Gagal membuat gambar. Pastikan file font dan template ada.",
                                  chat_id=processing_message.chat.id, message_id=processing_message.message_id)
            return

        # 3. Generate data tambahan
        dob = fake.date_of_birth(minimum_age=18, maximum_age=25)
        dob_str = dob.strftime("%d %B %Y")
        
        email_fn = re.sub(r'\s+', '', firstName).lower()
        email_ln = re.sub(r'\s+', '', lastName).lower()
        random_num = random.randint(100, 999)
        email = f"{email_fn}.{email_ln}{random_num}@pnj.ac.id"
        
        caption = (
            f"👤 Nama Depan: <code>{firstName}</code>\n"
            f"👤 Nama Belakang: <code>{lastName}</code>\n"
            f"🏨 Universitas / Perguruan Tinggi : <code>Universitas Islam Indonesia</code>\n\n"
            f"🎂 Tanggal Lahir:\n<code>{dob_str}</code>\n\n"
            f"📧 Alamat Email:\n<code>{email}</code>"
        )

        # 4. Kirim hasil
        with open(output_image_path, 'rb') as photo:
            bot.send_photo(message.chat.id, photo=photo, caption=caption, parse_mode='HTML')
        
        bot.delete_message(chat_id=processing_message.chat.id, message_id=processing_message.message_id)

    except Exception as e:
        logger.error(f"Terjadi error pada thread /generate untuk user {user_id}: {e}")
        bot.edit_message_text("Oops! Terjadi kesalahan internal saat memproses permintaan Anda.",
                              chat_id=processing_message.chat.id, message_id=processing_message.message_id)
    finally:
        # Hapus file gambar yang sudah dibuat untuk menghemat ruang
        if output_image_path and os.path.exists(output_image_path):
            try:
                os.remove(output_image_path)
                logger.info(f"File sementara {output_image_path} telah dihapus.")
            except OSError as e:
                logger.error(f"Gagal menghapus file {output_image_path}: {e}")
        
        # Hapus user dari daftar tugas yang sedang berjalan
        if user_id in user_tasks:
            user_tasks.remove(user_id)
        logger.info(f"Tugas /generate untuk user {user_id} selesai.")


# --- Handler Perintah Bot (Tidak berubah) ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message,
        f"Halo, <b>{message.from_user.first_name}</b>!\n"
        "Saya adalah bot generator. Ketik /generate untuk memulai.",
        parse_mode='HTML'
    )

@bot.message_handler(commands=['generate'])
@member_required
def send_generated_data(message):
    user_id = message.from_user.id
    if user_id in user_tasks:
        bot.reply_to(message, "⏳ Permintaan Anda sebelumnya masih diproses, harap tunggu.")
        return

    user_tasks.add(user_id)
    logger.info(f"Memulai tugas /generate untuk user {user_id}.")
    processing_message = bot.reply_to(message, "Sedang memproses, mohon tunggu... ⏳")
    
    thread = threading.Thread(target=process_generation_task, args=(message, processing_message))
    thread.start()

# --- Handler Perintah Admin (Tidak berubah) ---
@bot.message_handler(commands=['listid'])
@admin_required
def list_members(message):
    if not MEMBER_IDS:
        bot.reply_to(message, "Belum ada member yang terdaftar.")
        return
    id_list_str = "\n".join(f"• <code>{id}</code>" for id in MEMBER_IDS)
    bot.reply_to(message, f"<b>Daftar Member Terdaftar:</b>\n{id_list_str}", parse_mode='HTML')

@bot.message_handler(commands=['add'])
@admin_required
def add_member(message):
    try:
        chat_id_to_add = int(message.text.split()[1])
        if chat_id_to_add in MEMBER_IDS:
            bot.reply_to(message, f"✅ Member <code>{chat_id_to_add}</code> sudah terdaftar.", parse_mode='HTML')
        else:
            MEMBER_IDS.add(chat_id_to_add)
            save_members(MEMBER_IDS)
            bot.reply_to(message, f"👍 Member <code>{chat_id_to_add}</code> berhasil ditambahkan.", parse_mode='HTML')
    except (IndexError, ValueError):
        bot.reply_to(message, "Format salah. Gunakan: <code>/add [chat_id]</code>", parse_mode='HTML')

@bot.message_handler(commands=['delete'])
@admin_required
def delete_member(message):
    try:
        chat_id_to_delete = int(message.text.split()[1])
        if chat_id_to_delete in MEMBER_IDS:
            MEMBER_IDS.remove(chat_id_to_delete)
            save_members(MEMBER_IDS)
            bot.reply_to(message, f"🗑️ Member <code>{chat_id_to_delete}</code> berhasil dihapus.", parse_mode='HTML')
        else:
            bot.reply_to(message, f"❌ Member <code>{chat_id_to_delete}</code> tidak ditemukan.", parse_mode='HTML')
    except (IndexError, ValueError):
        bot.reply_to(message, "Format salah. Gunakan: <code>/delete [chat_id]</code>", parse_mode='HTML')

# --- Menjalankan Bot ---
if __name__ == '__main__':
    print("Bot sedang berjalan menggunakan generator gambar lokal...")
    bot.polling(none_stop=True)
