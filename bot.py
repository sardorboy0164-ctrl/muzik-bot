"""Muzik Top — Telegram musiqa boti.

Foydalanuvchi YouTube yoki Instagram link yuboradi, bot shu videodan
musiqani (MP3) ajratib, jo'natadi.
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
import sys
import time
from typing import Any, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message

import config
import downloader

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
    "3️⃣ G'alati savol yoki istalgan matn yuborsang — baribir musiqa chiqadi 🎶\n\n"
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


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        f"Assalomu alaykum, <b>{html.escape(message.from_user.first_name)}</b>! 👋\n\n"
        + HELP_TEXT
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


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
        query = text[:200]
        status = await message.reply(
            f"🔍 «{html.escape(query)}» bo'yicha qidirilmoqda..."
        )

    updater = StatusUpdater(status)

    async with slot:
        if query:
            updater.set(
                f"🔍 «{html.escape(query)}» bo'yicha qidirilmoqda...", force=True
            )
            try:
                url, found_title = await asyncio.to_thread(
                    downloader.search_first, query
                )
            except downloader.DownloadError as exc:
                log.warning("Qidiruvda xatolik %s -> %s", query, exc)
                await updater.done(f"❌ {html.escape(str(exc))}")
                return
            except Exception as exc:  # noqa: BLE001
                log.exception("Qidiruvda kutilmagan xatolik: %s", query)
                await updater.done(
                    f"❌ Kutilmagan xatolik: {html.escape(str(exc))[:200]}"
                )
                return

            platform = "YouTube"
            updater.set(
                f"🎵 Topildi: <b>{html.escape(found_title)}</b>\n⏳ Yuklanmoqda...",
                force=True,
            )

        updater.set(f"⏳ <b>{platform}</b>: musiqa yuklanmoqda...", force=True)
        path: Optional[str] = None
        try:
            path, info = await asyncio.to_thread(
                downloader.download_audio, url, make_progress_hook(updater, platform)
            )
        except downloader.DownloadError as exc:
            log.warning("Yuklashda xatolik %s -> %s", url, exc)
            await updater.done(f"❌ {html.escape(str(exc))}")
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("Kutilmagan xatolik: %s", url)
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

            await updater.set("📤 Jo'natilmoqda...", force=True)
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


async def main() -> None:
    config.validate()
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    me = await bot.get_me()
    log.info("Muzik Top ishga tushdi: @%s (id=%s)", me.username, me.id)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
