"""Ovozli xabardan musiqani aniqlash (Shazam uslubida)."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

log = logging.getLogger("muzik-top.recognizer")

# shazamio ixtiyoriy bog'liqlik — o'rnatilmasa ham botning qolgan qismi ishlaydi
try:  # pragma: no cover - muhitga bog'liq
    from shazamio import Shazam

    AVAILABLE = True
except Exception:  # noqa: BLE001
    Shazam = None  # type: ignore[assignment]
    AVAILABLE = False

MIN_DURATION = 5  # sekund — shuncha qisqa ovozda musiqa aniqlanmaydi
CLIP_DURATION = 15  # Shazam tahlil qiladigan qism uzunligi (sekund)
SAMPLE_RATE = 16000
BITRATE = "64k"


class RecognitionError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xatolik."""


def _extract_clip(source: str, destination: str, start: int = 0) -> None:
    """Ovozdan Shazam uchun mos qisqa MP3 klip ajratadi."""
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if start:
        cmd += ["-ss", str(start)]
    cmd += [
        "-i", source,
        "-t", str(CLIP_DURATION),
        "-ac", "1",
        "-ar", str(SAMPLE_RATE),
        "-b:a", BITRATE,
        destination,
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)


async def recognize(source: str, duration: int = 0) -> Optional[tuple[str, str]]:
    """Ovoz faylidan musiqani aniqlaydi.

    Args:
        source: Telegram'dan yuklab olingan ovoz fayli (oga/mp3/m4a/...).
        duration: Ovoz uzunligi (sekund).

    Returns:
        (sarlavha, ijrochi) yoki topilmagan bo'lsa None.
    """
    if not AVAILABLE:
        raise RecognitionError(
            "Ovozni tanish moduli o'rnatilmagan — `setup.sh` ni ishga tushiring "
            "yoki `pip install shazamio` buyrug'ini bajarig."
        )
    if not shutil.which("ffmpeg"):
        raise RecognitionError("Serverda ffmpeg yo'q — ovozni tahlil qilib bo'lmaydi.")
    if duration and duration < MIN_DURATION:
        raise RecognitionError(
            f"Ovoz juda qisqa — kamida {MIN_DURATION} soniya musiqa yuboring."
        )

    # Uzun ovozdan o'rtadan klip olamiz (musiqa odatda o'rtada bo'ladi)
    start = 0
    if duration and duration > CLIP_DURATION:
        start = (duration - CLIP_DURATION) // 2

    with tempfile.TemporaryDirectory(prefix="shazam_") as tmp:
        clip = os.path.join(tmp, "clip.mp3")
        try:
            await asyncio.to_thread(_extract_clip, source, clip, start)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            log.warning("Kliplashda xatolik: %s", exc)
            raise RecognitionError("Ovozni o'qib bo'lmadi — qaytadan yuboring.") from exc

        try:
            result = await Shazam().recognize(clip)
        except Exception as exc:  # noqa: BLE001
            log.warning("Shazam xatosi: %s", exc)
            raise RecognitionError("Musiqani tanib bo'lmadi — boshqasini urinib ko'ring.") from exc

    track = (result or {}).get("track") or {}
    title = str(track.get("title") or "").strip()
    artist = str(track.get("subtitle") or "").strip()

    if not title:
        return None
    return title, artist or "Noma'lum ijrochi"
