"""Loyiha sozlamalari — .env faylidagi qiymatlarni o'qiydi."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Telegram bot tokeni (BotFathers'dan olinadi)
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

# Bir vaqtda nechta yuklanishga ruxsat (serverni yormaslik uchun)
MAX_CONCURRENT: int = int(os.getenv("MAX_CONCURRENT", "3"))

# Instagram uchun cookie fayli (majburiy emas, lekin yopiq kontent uchun kerak)
COOKIES_FILE: str = os.getenv("COOKIES_FILE", "cookies.txt").strip()

# Telegram bot uchun fayl chegarasi ~50 MB
MAX_FILESIZE: int = 49 * 1024 * 1024

# MP3 sifati (kbps)
AUDIO_QUALITY: str = os.getenv("AUDIO_QUALITY", "192").strip()

APP_NAME: str = "Muzik Top"
APP_VERSION: str = "1.0.0"


def validate() -> None:
    """Token mavjudligini tekshiradi, aks holda xato beradi."""
    if not BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN topilmadi!\n"
            "1) .env.example faylini .env ga nusxalang:  cp .env.example .env\n"
            "2) .env ichiga BOT_TOKEN=123456:ABC-DEF... yozing\n"
            "3) Tokenni @BotFathers'dan oling."
        )
