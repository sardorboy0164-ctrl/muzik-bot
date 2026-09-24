"""Muzik Top — Telegram musiqa boti.

Foydalanuvchi:
  • YouTube/Instagram link yuboradi  → videodan MP3 ajratib beradi
  • Qo'shiq nomini yoki savol yozadi → YouTube'da topib MP3 beradi
  • Ovozli xabar yuboradi            → musiqani tanib, MP3 beradi (Shazam)
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
import sys
import tempfile
import time
from typing import Any, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message

import config
import downloader
import recognizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("muzik-top")

router = Router()
slot = asyncio.Semaphore(config.MAX_CONCURRENT)

HELP_TEXT = (
    "🎧 <b>Muzik Top</b> — video linkidan musiqa olib beruvchi bot.\n\n"
    "<b>Qanday ishlaydi:</b>\n"
    "1️⃣ YouTube yoki Instagram'dan video havolasini yuboring\n"
    "2️⃣ Yoki shunchaki qo'shiq nomini yoz — bot musiqani topib beradi\n"
    "3️⃣ G'alati savol yoki istalgan matn yuborsang — baribir musiqa chiqadi 🎶\n"
    "4️⃣ 🎤 <b>Ovozli xabar yuborsang</b> — bot musiqani tanib, MP3 qilib "
    "jo'natadi (Shazam kabi)\n\n"
    "<b>Qo'llab-quvvatlanadi:</b> YouTube, YouTube Music, Instagram, "
    "TikTok, SoundCloud\n\n"
    "🔹 /start — boshlash\n"
    "🔹 /help — yordam"
)


class StatusUpdater:
    """Holat xabarini igna (thread) xavfsiz yangilaydi."""

    def __init__(self, message: Message) -> None:
        self._message = message
        self._loop = asyncio.get_running_loop()
        self._last_time = 0.0
        self._last_text = ""

    async def _edit(self, text: str) -> None:
        if text == self._last_text:
            return
        try:
            await self._message.edit_text(text)
            self._last_text = text
        except Exception:  # noqa: BLE001 - xabar o'zgarmagan bo'lsa jim o'tamiz
            pass

    def set(self, text: str, *, force: bool = False) -> None:
        """Har qanday thread'dan chaqirsa bo'ladi."""
        now = time.monotonic()
        if not force and now - self._last_time < 2.0:
            return
        self._last_time = now
        asyncio.run_coroutine_threadsafe(self._edit(text), self._loop)

    async def done(self, text: str) -> None:
        self._last_text = ""
        try:
            await self._message.edit_text(text)
        except Exception:  # noqa: BLE001
            pass

    async def delete(self) -> None:
        try:
            await self._message.delete()
        except Exception:  # noqa: BLE001
            pass


def make_progress_hook(status: StatusUpdater, platform: str):
    """yt-dlp progress hook'i — foiz va tezlikni ko'rsatadi."""

    def hook(data: dict[str, Any]) -> None:
        state = data.get("status")
        if state == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            if total:
                percent = done * 100 / total
                speed = data.get("speed")
                eta = data.get("eta")
                speed_txt = f"{speed / 1024 / 1024:.1f} MB/s" if speed else "—"
                eta_txt = f"{int(eta)} sek" if eta else "—"
                status.set(
                    f"⬇️ <b>{platform}</b> dan yuklanmoqda...\n"
                    f"Progress: {percent:.0f}%\n"
                    f"Tezlik: {speed_txt} | Qolgan: {eta_txt}"
                )
            else:
                status.set(f"⬇️ <b>{platform}</b> dan yuklanmoqda...")
        elif state == "finished":
            status.set("⚙️ MP3 ko'rinishiga o'tkazilmoqda...", force=True)

    return hook


async def deliver_music(
    message: Message,
    updater: StatusUpdater,
    *,
    url: Optional[str] = None,
    query: Optional[str] = None,
    platform: str = "YouTube",
) -> None:
    """Musiqani yuklab Telegram'ga jo'natadi (query yoki tayyor URL bo'yicha)."""
    path: Optional[str] = None
    info: dict = {}

    try:
        if query:
            candidates = await asyncio.to_thread(downloader.search_candidates, query)
            if not candidates:
                raise downloader.DownloadError(
                    "Hech narsa topilmadi — boshqa nom bilan urinib ko'ring."
                )

            # Topilgan variantlarni birin-ketin yuklashga urinamiz:
            # birinchi video ochilmasa — keyingisiga o'tamiz.
            last_error: Optional[Exception] = None
            for candidate_url, candidate_title in candidates:
                updater.set(
                    f"🎵 Topildi: <b>{html.escape(candidate_title)}</b>\n"
                    "⏳ Yuklanmoqda...",
                    force=True,
                )
                try:
                    path, info = await asyncio.to_thread(
                        downloader.download_audio,
                        candidate_url,
                        make_progress_hook(updater, platform),
                    )
                    url = candidate_url
                    break
                except downloader.DownloadError as exc:
                    last_error = exc
                    log.info("Variant yuklanmadi %s -> %s", candidate_url, exc)

            if path is None:
                raise last_error or downloader.DownloadError(
                    "Musiqani yuklab bo'lmadi — boshqasini urinib ko'ring."
                )
        else:
            updater.set(f"⏳ <b>{platform}</b>: musiqa yuklanmoqda...", force=True)
            path, info = await asyncio.to_thread(
                downloader.download_audio, url, make_progress_hook(updater, platform)
            )
    except downloader.DownloadError as exc:
        log.warning("Yuklashda xatolik %s -> %s", url or query, exc)
        await updater.done(f"❌ {html.escape(str(exc))}")
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("Kutilmagan xatolik: %s", url or query)
        await updater.done(f"❌ Kutilmagan xatolik: {html.escape(str(exc))[:200]}")
        return

    try:
        size = os.path.getsize(path)
        if size > config.MAX_FILESIZE:
            await updater.done(
                "❌ Fayl juda katta (> 50 MB) — Telegram buni qabul qilmaydi."
            )
            return

        title = downloader.track_title(info)
        artist = downloader.track_artist(info)
        duration = info.get("duration") or None
        if duration:
            duration = int(duration)

        updater.set("📤 Jo'natilmoqda...", force=True)
        await message.answer_audio(
            audio=FSInputFile(path),
            caption=f"🎵 {html.escape(title)}\n👤 {html.escape(artist)}\n\n"
            f"Manba: <b>{html.escape(platform)}</b>",
            performer=artist[:255],
            title=title[:255],
            duration=duration,
            reply_to_message_id=message.message_id,
        )
        await updater.delete()
        log.info("Jo'natildi: %s — %s", title, platform)
    except Exception as exc:  # noqa: BLE001
        log.exception("Jo'natishda xatolik")
        await updater.done(f"❌ Jo'natib bo'lmadi: {html.escape(str(exc))[:200]}")
    finally:
        if path:
            downloader.cleanup(path)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        f"Assalomu alaykum, <b>{html.escape(message.from_user.first_name)}</b>! 👋\n\n"
        + HELP_TEXT
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(F.voice | F.audio)
async def on_voice(message: Message, bot: Bot) -> None:
    """Ovozli xabar → musiqani aniqlash (Shazam) → MP3 jo'natish."""
    media = message.voice or message.audio
    if media is None:
        return

    duration = int(media.duration or 0)
    status = await message.reply("🔎 Ovoz tahlil qilinmoqda...")
    updater = StatusUpdater(status)

    async with slot:
        updater.set(
            "🔎 Ovoz tahlil qilinmoqda... (5-10 soniya musiqa yaxshi taniladi)",
            force=True,
        )

        with tempfile.TemporaryDirectory(prefix="voice_") as tmp:
            extension = ".oga" if message.voice else os.path.splitext(media.file_name or "")[1]
            source = os.path.join(tmp, f"voice{extension or '.oga'}")

            try:
                file = await bot.get_file(media.file_id)
                await bot.download_file(file.file_path, destination=source)
            except Exception as exc:  # noqa: BLE001
                log.warning("Ovozni olishda xatolik: %s", exc)
                await updater.done(f"❌ Ovozni olib bo'lmadi: {html.escape(str(exc))[:150]}")
                return

            try:
                found = await recognizer.recognize(source, duration)
            except recognizer.RecognitionError as exc:
                await updater.done(f"❌ {html.escape(str(exc))}")
                return
            except Exception as exc:  # noqa: BLE001
                log.exception("Tanishda kutilmagan xatolik")
                await updater.done(f"❌ Tanib bo'lmadi: {html.escape(str(exc))[:150]}")
                return

            if not found:
                await updater.done(
                    "❌ Bu ovozdan musiqa aniqlanmadi.\n"
                    "Musiqali qismini (kamida 5-10 soniya) yuboring — "
                    "ataylab qo'ying va ovozli xabar yuboring."
                )
                return

            title, artist = found
            log.info("Tanildi: %s — %s", title, artist)
            updater.set(
                f"🎯 Topildi: <b>{html.escape(artist)} — {html.escape(title)}</b>\n"
                "🔍 YouTube'da qidirilmoqda...",
                force=True,
            )
            await deliver_music(
                message,
                updater,
                query=f"{artist} {title}",
                platform="YouTube",
            )


@router.message(F.text)
async def on_text(message: Message) -> None:
    text = (message.text or "").strip()

    if text.startswith("/"):
        await message.answer("Noma'lum buyruq — /help ni bosing.")
        return

    url = downloader.find_url(text)

    if url and not downloader.is_supported(url):
        platform = downloader.platform_of(url)
        await message.answer(
            f"Bu platforma hozircha qo'llab-quvvatlanmaydi: <b>{html.escape(platform)}</b>\n"
            "YouTube yoki Instagram linkini yuboring."
        )
        return

    query: Optional[str] = None
    if url:
        platform = downloader.platform_of(url)
        status = await message.reply(f"⏳ <b>{platform}</b>: tayyorlanmoqda...")
    else:
        # Link emas — qo'shiq nomi, g'alati savol yoki istalgan matn:
        # shuni YouTube'da qidirib, birinchi natijadan musiqa chiqaramiz.
        platform = "YouTube"
        query = text[:200]
        status = await message.reply(
            f"🔍 «{html.escape(query)}» bo'yicha qidirilmoqda..."
        )

    updater = StatusUpdater(status)

    if query:
        updater.set(f"🔍 «{html.escape(query)}» bo'yicha qidirilmoqda...", force=True)

    async with slot:
        await deliver_music(message, updater, url=url, query=query, platform=platform)


async def main() -> None:
    config.validate()
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    me = await bot.get_me()
    log.info(
        "Muzik Top ishga tushdi: @%s (id=%s) | Shazam: %s",
        me.username,
        me.id,
        "yoqilgan" if recognizer.AVAILABLE else "o'rnatilmagan",
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
