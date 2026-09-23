#!/usr/bin/env bash
# Muzik Top — to'liq o'rnatish skripti (Shazam bilan ovozni tanish ham)
set -euo pipefail
cd "$(dirname "$0")"

echo "▶ Python venv yaratilmoqda..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip >/dev/null

echo "▶ Asosiy bog'liqliklar o'rnatilmoqda (aiogram, yt-dlp)..."
pip install -r requirements.txt

echo "▶ Shazam (ovozdan musiqa aniqlash) o'rnatilmoqda..."
if pip install "shazamio==0.8.1"; then
    echo "  ✓ shazamio o'rnatildi"
else
    # sabab: shazamio 0.8.1 shazamio-core==1.1.2 ni talab qiladi, ammo ba'zi
    # Python versiyalarida (masalan 3.14) shu core uchun tayyor wheel yo'q.
    echo "  → standart o'rnatish muvaffaqiyatsiz, mos usul bilan o'rnatilmoqda..."
    pip install --no-deps "shazamio==0.8.1"
    pip install "shazamio-core>=1.1.2" "numpy>=2.2.2" aiohttp pydub \
        dataclass-factory aiofiles anyio aiohttp-retry pydantic
    pip install audioop-lts 2>/dev/null || true   # Python >= 3.13 uchun
    echo "  ✓ shazamio (--no-deps) o'rnatildi"
fi

echo
echo "✅ Tayyor! Keyingi qadamlar:"
echo "   1) cp .env.example .env   (ichiga BOT_TOKEN yozing)"
echo "   2) source .venv/bin/activate"
echo "   3) python bot.py"
