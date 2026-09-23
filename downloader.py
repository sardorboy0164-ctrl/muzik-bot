"""YouTube / Instagram (va boshqa manbalar) dan audio ajratish.

Barcha ish yt-dlp orqali olib boriladi. yt-dlp bloklovchi (blocking)
funksiya bo'lgani uchun uni bot.py ichida `asyncio.to_thread` da chaqiramiz.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from typing import Any, Callable, Optional

import yt_dlp
from yt_dlp.utils import DownloadError as YTDLPDownloadError

from config import AUDIO_QUALITY, COOKIES_FILE

log = logging.getLogger("muzik-top.downloader")

# Xabardan URL ajratib olish
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

HOST_HINTS: tuple[tuple[str, str], ...] = (
    ("youtu.be", "YouTube"),
    ("youtube.com", "YouTube"),
    ("instagram.com", "Instagram"),
    ("instagr.am", "Instagram"),
    ("tiktok.com", "TikTok"),
    ("vimeo.com", "Vimeo"),
    ("soundcloud.com", "SoundCloud"),
)

ProgressHook = Callable[[dict], None]


class DownloadError(Exception):
    """Foydalanuvchiga ko'rsatiladigan xatolik."""


def find_url(text: Optional[str]) -> Optional[str]:
    """Matn ichidan birinchi URL ni topadi."""
    if not text:
        return None
    match = URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(".,!?)\n\t")


def platform_of(url: str) -> str:
    """URL qaysi platformaga tegishli ekanini aniqlaydi."""
    low = url.lower()
    for host, name in HOST_HINTS:
        if host in low:
            return name
    return "Boshqa"


def is_supported(url: str) -> bool:
    """URL qo'llab-quvvatlanadigan platformadami?”"""
    return platform_of(url) != "Boshqa"


def _build_options(
    tmp_dir: str, progress: Optional[ProgressHook], client: Optional[str] = None
) -> dict:
    options: dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(tmp_dir, "media.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "ignoreerrors": False,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": AUDIO_QUALITY,
            }
        ],
    }
    if client:
        options["extractor_args"] = {"youtube": {"player_client": [client]}}
    if progress:
        options["progress_hooks"] = [progress]
    if COOKIES_FILE and os.path.isfile(COOKIES_FILE):
        options["cookiefile"] = COOKIES_FILE
        log.info("cookies.txt foydalanilmoqda: %s", COOKIES_FILE)
    return options


def _friendly_error(raw: str) -> str:
    """yt-dlp xatosini o'zbekcha, tushunarli xabarga aylantiradi."""
    low = raw.lower()
    text = re.sub(r"\s+", " ", raw).strip()

    if "unsupported url" in low:
        return "Bu havola qo'llab-quvvatlanmaydi. YouTube yoki Instagram linkini yuboring."
    if "private" in low or "private video" in low:
        return "Bu video yoki kanal yopiq (private) — uni olish mumkin emas."
    if "video unavailable" in low or "not available" in low:
        return "Video topilmadi yoki o'chirilgan bo'lishi mumkin."
    if "sign in" in low or "login" in low or "cookies" in low or "confirm your age" in low:
        return (
            "YouTube/Instagram kirishni talab qilayapti. "
            "`cookies.txt` faylini loyiha papkasiga qo'ying (README da tavsiflangan) "
            "yoki birozdan keyin qayta urinib ko'ring."
        )
    if "429" in low or "too many requests" in low:
        return "Server cheklovdan o'tdi — birozdan keyin qayta urinib ko'ring."
    if "timed out" in low or "timeout" in low or "network" in low:
        return "Internet yoki server sekin — qayta urinib ko'ring."
    if "ffmpeg" in low:
        return "Serverda ffmpeg o'rnatilmagan — admin bilan bog'laning."
    if "max downloads" in low:
        return "YouTube hozircha yuklashni vaqtincha cheklamoqda — keyinroq urinib ko'ring."

    return text[:300]


def _is_client_error(raw: str) -> bool:
    """YouTube "bot tekshiruvi" kabi xatolikmi?

    Bunday holatda boshqa player_client bilan qayta urinib ko'rish mumkin.
    """
    low = raw.lower()
    markers = (
        "sign in to confirm",
        "not a bot",
        "page needs to be reloaded",
        "requested format is not available",
        "http error 403",
        "http error 503",
        "confirm your age",
        "use --cookies",
    )
    return any(marker in low for marker in markers)


def _find_output(tmp_dir: str) -> Optional[str]:
    """yt-dlp yaratgan audio faylni topadi (mp3 afzallikda)."""
    files = [
        os.path.join(tmp_dir, name)
        for name in os.listdir(tmp_dir)
        if os.path.isfile(os.path.join(tmp_dir, name))
    ]
    if not files:
        return None
    mp3s = [f for f in files if f.lower().endswith(".mp3")]
    pool = mp3s or files
    return max(pool, key=os.path.getsize)


def _extract_info(data: Optional[dict]) -> Optional[dict]:
    """Playlist javobidan bitta video ma'lumotini ajratadi."""
    if not data:
        return None
    entries = data.get("entries")
    if entries:
        entries = [e for e in entries if e]
        return entries[0] if entries else None
    return data


# YouTube'da "bot tekshiruvi" (sign in to confirm you're not a bot")
# uchun alternativ player_client lar — biri ishlamasa keyingisiga o'tamiz.
YOUTUBE_CLIENTS: tuple[str, ...] = ("android", "web", "tv", "ios", "mweb")


def download_audio(
    url: str,
    progress: Optional[ProgressHook] = None,
) -> tuple[str, dict[str, Any]]:
    """Audio faylni yuklab oladi va (yo'l, metadata) qaytaradi.

    YouTube bloklovchi xatolik bersa — avtomatik ravishda boshqa
    player_client bilan qayta uriniladi (cookies shart emas).

    Qaytarilgan fayl `tmp_dir` ichida joylashgan — uni o'chirish
    mas'uliyati chaqiruvchida (bot.py).
    """
    is_youtube = "youtu" in url.lower()
    clients: tuple[Optional[str], ...] = YOUTUBE_CLIENTS if is_youtube else (None,)
    last_error: Optional[DownloadError] = None

    for index, client in enumerate(clients):
        is_last = index == len(clients) - 1
        tmp_dir = tempfile.mkdtemp(prefix="muzik_top_")
        options = _build_options(tmp_dir, progress, client)

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                raw_info = ydl.extract_info(url, download=True)
        except YTDLPDownloadError as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            last_error = DownloadError(_friendly_error(str(exc)))
            if _is_client_error(str(exc)) and not is_last:
                log.info("player_client=%s ishlamadi, keyingisini sinaymiz", client)
                continue
            raise last_error from exc
        except Exception as exc:  # noqa: BLE001 - xatolikni o'zbekchaga chiqaramiz
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise DownloadError(_friendly_error(str(exc))) from exc

        info = _extract_info(raw_info)
        if info is None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            last_error = DownloadError("Videoma'lumotni olib bo'lmadi.")
            if not is_last:
                continue
            raise last_error

        path = _find_output(tmp_dir)
        if not path:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            last_error = DownloadError("Audio faylni yaratib bo'lmadi.")
            if not is_last:
                log.info("player_client=%s audio yaratmadi, keyingisini sinaymiz", client)
                continue
            raise last_error

        if client:
            log.info("Muvaffaqiyatli player_client=%s", client)
        return path, info

    raise last_error or DownloadError("Audio faylni yuklab bo'lmadi.")


def cleanup(path: str) -> None:
    """Yuklab olingan fayl va uning papkasini o'chiradi."""
    try:
        folder = os.path.dirname(path)
        shutil.rmtree(folder, ignore_errors=True)
    except OSError as exc:
        log.warning("Tozalashda xatolik: %s", exc)


def search_first(query: str) -> tuple[str, str]:
    """So'rov bo'yicha YouTube'dan birinchi natijani topadi.

    Returns:
        (video_url, sarlavha)
    """
    cleaned = re.sub(r"\s+", " ", query).strip()
    if not cleaned:
        raise DownloadError("Bo'sh so'rov.")

    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "skip_download": True,
        "socket_timeout": 20,
        "default_search": "ytsearch",
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            data = ydl.extract_info(f"ytsearch1:{cleaned}", download=False)
    except YTDLPDownloadError as exc:
        raise DownloadError(_friendly_error(str(exc))) from exc
    except Exception as exc:  # noqa: BLE001
        raise DownloadError(_friendly_error(str(exc))) from exc

    entries = [e for e in (data or {}).get("entries") or [] if e]
    if not entries:
        raise DownloadError("Hech narsa topilmadi — boshqa nom bilan urinib ko'ring.")

    first = entries[0]
    link = first.get("webpage_url") or ""
    if not link and first.get("id"):
        link = f"https://www.youtube.com/watch?v={first['id']}"
    if not link:
        raise DownloadError("Topilgan video havolasini olib bo'lmadi.")

    title = str(first.get("title") or cleaned).strip()
    return link, title


def track_title(info: dict) -> str:
    """Audio uchun sarlavha."""
    for key in ("track", "title", "fulltitle"):
        value = info.get(key)
        if value:
            return str(value).strip()
    return "Noma'lum audio"


def track_artist(info: dict) -> str:
    """Audio uchun ijrochi."""
    for key in ("artist", "creator", "uploader", "channel"):
        value = info.get(key)
        if value:
            return str(value).strip()
    return "Noma'lum ijrochi"
