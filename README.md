# 🎵 Muzik Top

**Muzik Top** — Telegram boti. U YouTube yoki Instagram'dan video havolasini qabul qilib, undan musiqani (MP3) ajratib jo'natadi.

---

## ✨ Imkoniyatlar

- 📺 **YouTube / YouTube Music** — video yoki playlist havolasidan MP3 olish
- 📸 **Instagram** — Reels va postlardan audio ajratish
- 🎧 Qo'shimcha ravishda **TikTok, SoundCloud, Vimeo** havolalari ham ishlaydi
- ⚡️ Parallel yuklash (bir vaqtda nechta bo'lsa)
- 🌐 Butunlay o'zbekcha interfeys

---

## 🛠 O'rnatish

Kerakli dasturlar: **Python 3.10+** va **ffmpeg**.

```bash
# 1) Repozitoriyani olish
git clone https://github.com/sardorboy0164-ctrl/muzik-bot.git
cd muzik-bot

# 2) Virtual muhit yaratish
python3 -m venv .venv
source .venv/bin/activate

# 3) Bog'liqliklarni o'rnatish
pip install -r requirements.txt

# 4) Sozlamalarni kiritish
cp .env.example .env
```

`.env` faylini tahrirlang:

```env
BOT_TOKEN=123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxx
```

Tokenni [@BotFathers](https://t.me/BotFathers) dan olish mumkin → `/newbot`.

---

## 🚀 Ishga tushirish

```bash
source .venv/bin/activate
python bot.py
```

---

## 📸 Instagram uchun cookies.txt (majburiy emas)

Instagram ko'pinchi kirishni talab qiladi. Bunday holatda:

1. Brauzeringizga **Get cookies.txt** kengaytmasini o'rnatng
2. `instagram.com` ga kiring va cookie'larni eksport qiling
3. Faylni loyiha papkasiga **`cookies.txt`** nomi bilan saqlang
4. Botni qayta ishga tushiring

> Cookie fayl `.gitignore` ichida — u GitHub'ga hech qachon push bo'lmaydi.

---

## 🐳 Docker bilan ishga tushirish

```bash
docker build -t muzik-top .
docker run --env-file .env --name muzik-top muzik-top
```

---

## 📁 Loyiha tuzilishi

```
muzik-bot/
├── bot.py           # Telegram bot mantig'i (aiogram 3)
├── downloader.py    # yt-dlp orqali audio yuklash
├── config.py        # .env sozlamalari
├── requirements.txt # bog'liqliklar
├── .env.example     # namuna sozlama
└── README.md        # hujjat
```

---

## ⚠️ Eslatma

Bot faqat shaxsiy va o'quv maqsadlarida ishlatiladi. Mualliflik huquqi
buvchi kontentni noqonuniy tarqatish uchun javobgarlik foydalanuvchi zimmasida.

---

## 📄 Litsenziya

MIT
