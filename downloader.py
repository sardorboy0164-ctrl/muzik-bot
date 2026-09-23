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
import time
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


# Bir so'rov bo'yicha nechta variantni ko'rib chiqamiz (birinchi video
# ochilmasa — ikkinchisiga o'tamiz)
SEARCH_LIMIT = 5
SEARCH_ATTEMPTS = 3
SEARCH_RETRY_DELAY = 2.0


def _clean_query(query: str) -> str:
    """So'rovni qidiruvga yaroq qilib tozalaydi (tinish belgilari olib tashlanadi)."""
    cleaned = re.sub(r"[^\w\s'\-]", " ", query, flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip()


# Savol so'zlari — ularni olib tashlash qidiruvni aniqroq qiladi
_QUESTION_WORDS = {
    "nima", "nima?", "uchun", "kerak", "kerakmi", "qanday", "qandoq", "qale",
    "bormi", "bor", "yoq", "ha", "ham", "va", "yoki", "bu", "shu", "meni",
    "sizni", "bizni", "qilib", "ayt", "ayting", "gapir", "how", "why", "what",
    "is", "are", "the", "a", "an", "to", "for", "of", "and", "or",
}


def _query_variants(query: str) -> list[str]:
    """Uzun savol/g'alati matnni qisqartirib, qidiruv variantlari yaratadi."""
    base = _clean_query(query)
    if not base:
        return []

    words = base.split()

    # 1) Oxiridagi savol so'zlarini tashlab qoldiramiz: "ertalabki gimnastika
    #    nima uchun kerak" -> "ertalabki gimnastika"
    trimmed = list(words)
    while len(trimmed) > 2 and trimmed[-1].lower().strip("?!.,") in _QUESTION_WORDS:
        trimmed.pop()
    trimmed_text = " ".join(trimmed)

    variants = [trimmed_text, base]
    if len(words) > 5:
        variants.append(" ".join(words[:5]))
    if len(words) > 4:
        variants.append(" ".join(words[:4]))
    if len(words) > 2:
        variants.append(" ".join(words[:2]))

    seen: set[str] = set()
    unique: list[str] = []
    for variant in variants:
        cleaned = variant.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return unique[:4]


def search_candidates(query: str, limit: int = SEARCH_LIMIT) -> list[tuple[str, str]]:
    """So'rov bo'yicha YouTube natijalarini ro'yxat qilib qaytaradi.

    Returns:
        [(video_url, sarlavha), ...] — eng mos natijadan boshlab.
    """
    variants = _query_variants(query)
    if not variants:
        raise DownloadError("Bo'sh so'rov — qo'shiq nomi yoki savol yozing.")

    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "skip_download": True,
        "socket_timeout": 20,
        "default_search": "ytsearch",
        # Natijalarni yig'ishda bitta yopiq video butun qidiruvni
        # yiqitmasligi uchun
        "ignoreerrors": True,
        "extract_flat": "in_playlist",
    }

    last_error: Optional[Exception] = None

    # YouTube vaqtincha bo'sh natija qaytarsa — bir necha marotaba takrorlaymiz
    for attempt in range(SEARCH_ATTEMPTS):
        for variant in variants:
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    data = ydl.extract_info(f"ytsearch{limit}:{variant}", download=False)
            except YTDLPDownloadError as exc:
                last_error = exc
                continue
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue

            results: list[tuple[str, str]] = []
            for entry in [e for e in (data or {}).get("entries") or [] if e]:
                link = entry.get("webpage_url") or ""
                if not link and entry.get("id"):
                    link = f"https://www.youtube.com/watch?v={entry['id']}"
                if link:
                    title = str(entry.get("title") or variant).strip()
                    results.append((link, title))

            if results:
                log.info("Qidiruv '%s' -> %d ta natija", variant, len(results))
                return results

        if attempt < SEARCH_ATTEMPTS - 1:
            log.info("Qidiruv bo'sh qaytdi, %.0f sekunddan keyin takrorlaymiz", SEARCH_RETRY_DELAY)
            time.sleep(SEARCH_RETRY_DELAY)

    if last_error is not None:
        raise DownloadError(_friendly_error(str(last_error)))
    raise DownloadError(
        "Hech narsa topilmadi — boshqa nom bilan urinib ko'ring "
        "yoki birozdan keyin qayta yuboring."
    )


def search_first(query: str) -> tuple[str, str]:
    """So'rov bo'yicha YouTube'dan birinchi natijani topadi.

    Returns:
        (video_url, sarlavha)
    """
    return search_candidates(query, limit=1)[0]


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
