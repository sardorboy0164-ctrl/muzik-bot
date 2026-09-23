# 🎵 Muzik Top

**Muzik Top** — Telegram boti. U YouTube yoki Instagram'dan video havolasini qabul qilib, undan musiqani (MP3) ajratib jo'natadi.

---

## ✨ Imkoniyatlar

- 📺 **YouTube / YouTube Music** — video yoki playlist havolasidan MP3 olish
- 📸 **Instagram** — Reels va postlardan audio ajratish
- 🎧 Qo'shimcha ravishda **TikTok, SoundCloud, Vimeo** havolalari ham ishlaydi
- 🎤 **Ovozli xabar (Shazam)** — ovozli xabar yuborsangiz, bot musiqani tanib, MP3 qilib jo'natadi
- 🔎 **Qidiruv** — link emas, shunchaki qo'shiq nomini yozsangiz ham musiqa topiladi
- 💬 G'alati savol yoki istalgan matn yuborsangiz — baribir mos musiqa chiqadi
- ⚡️ Parallel yuklash (bir vaqtda nechta bo'lsa)
- 🌐 Butunlay o'zbekcha interfeys

---

## 🛠 O'rnatish

Kerakli dasturlar: **Python 3.10+** va **ffmpeg**.

```bash
# 1) Repozitoriyani olish
git clone https://github.com/sardorboy0164-ctrl/muzik-bot.git
cd muzik-bot

# 2) Hammasini bir yo'la o'rnatish (venv + bog'liqliklar + Shazam)
./setup.sh

# 3) Sozlamalarni kiritish
cp .env.example .env
```

> Agar `./setup.sh` ishlamasa — qo'lda:
> `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

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

## 🎤 Ovozli xabardan musiqa aniqlash (Shazam)

Telefoningizdan **qo'shiqni kuylab yoki audio yozib**, ovozli xabar yuboring —
bot uni Shazam'dan topadi va MP3 ko'rinishida jo'natadi:

```
👤 [🎤 ovozli xabar]
🤖 🔎 Ovoz tahlil qilinmoqda...
🤖 🎯 Topildi: Ed Sheeran — Shape of You
🤖 🔍 YouTube'da qidirilmoqda...
🤖 🎵 Ed Sheeran - Shape of You  → MP3
```

**Muhim:**
- Ovoz kamida **5-10 soniya** bo'lishi kerak (15 soniya o'rtasidan olinadi)
- Musiqa **Shazam bazasida** bo'lishi shart — notanirgan yoki o'z yozuvingiz
  bo'lsa, bot "aniqlanmadi" deb javob beradi
- Modul `shazamio` — `./setup.sh` uni o'rnatib beradi

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
├── downloader.py    # yt-dlp orqali audio yuklash + qidiruv
├── recognizer.py    # Ovozdan musiqa aniqlash (Shazam / shazamio)
├── config.py        # .env sozlamalari
├── setup.sh         # to'liq o'rnatish skripti
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
