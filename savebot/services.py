"""Navbat, obuna tekshiruvi, fayl yuborish va havolani qayta ishlashning to'liq jarayoni."""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import html
import logging
import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from aiogram import Bot
from aiogram.enums import ButtonStyle, ChatAction, ChatMemberStatus
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramEntityTooLarge,
    TelegramRetryAfter,
)
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
    ReplyParameters,
)

from .texts import progress_bar, t
from .config import Config
from .db import Database
from .downloader import (
    Downloader,
    DownloadError,
    Progress,
    is_public_url,
    normalize_url,
    platform_of,
    FATAL_CODES,
    Probe,
    is_audio_site,
    prefers_gallery,
    prepare_files,
    quality_name,
)

log = logging.getLogger(__name__)


@dataclass
class AppState:
    restart_requested: bool = False
    broadcasting: bool = False


# ----------------------------------------------------------------------------------
# Navbat
# ----------------------------------------------------------------------------------
class DownloadQueue:
    """Server bo'yicha umumiy cheklov (semaphore) + har bir foydalanuvchi uchun cheklov."""

    def __init__(self, parallel: int, per_user: int):
        self._sem = asyncio.Semaphore(parallel)
        self.parallel = parallel
        self.per_user = per_user
        self.waiting = 0
        self.active = 0
        self._users: dict[int, int] = {}
        # Havolani tekshirish (probe) — yengil, lekin baribir cheklaymiz
        self.probe_slots = asyncio.Semaphore(parallel * 2)

    def try_reserve(self, user_id: int) -> bool:
        if self._users.get(user_id, 0) >= self.per_user:
            return False
        self._users[user_id] = self._users.get(user_id, 0) + 1
        return True

    def release(self, user_id: int) -> None:
        left = self._users.get(user_id, 0) - 1
        if left > 0:
            self._users[user_id] = left
        else:
            self._users.pop(user_id, None)

    @property
    def busy(self) -> int:
        return sum(self._users.values())

    @asynccontextmanager
    async def slot(self, on_wait: Callable[[int], Awaitable[None]] | None = None):
        if self._sem.locked():
            self.waiting += 1
            try:
                if on_wait:
                    await on_wait(self.waiting)
                await self._sem.acquire()
            finally:
                self.waiting -= 1
        else:
            await self._sem.acquire()
        self.active += 1
        try:
            yield
        finally:
            self.active -= 1
            self._sem.release()


# ----------------------------------------------------------------------------------
# Majburiy obuna
# ----------------------------------------------------------------------------------
@dataclass
class Channel:
    chat_id: str  # @username yoki -100...
    link: str | None


def parse_channels(raw: tuple[str, ...]) -> list[Channel]:
    """Format: "@kanal" yoki "-1001234567890|https://t.me/+taklif_havolasi"."""
    result = []
    for item in raw:
        chat_id, _, link = item.partition("|")
        chat_id = chat_id.strip()
        link = link.strip() or (f"https://t.me/{chat_id.lstrip('@')}" if chat_id.startswith("@") else None)
        result.append(Channel(chat_id, link))
    return result


class SubscriptionChecker:
    def __init__(self, channels: list[Channel], ttl: int = 600):
        self.channels = channels
        self.ttl = ttl
        self._ok: dict[int, float] = {}

    async def missing(self, bot: Bot, user_id: int) -> list[Channel]:
        if not self.channels:
            return []
        if self._ok.get(user_id, 0) > time.monotonic():
            return []
        missing = []
        for ch in self.channels:
            try:
                member = await bot.get_chat_member(ch.chat_id, user_id)
            except TelegramAPIError as e:
                # Bot kanalda admin bo'lmasa — foydalanuvchini to'xtatib qo'ymaymiz
                log.warning("Obunani tekshirib bo'lmadi (%s): %s — bot kanalda adminmi?", ch.chat_id, e)
                continue
            status = member.status
            if status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED) or (
                status == ChatMemberStatus.RESTRICTED and not getattr(member, "is_member", True)
            ):
                missing.append(ch)
        if not missing:
            if len(self._ok) > 50_000:
                self._ok.clear()
            self._ok[user_id] = time.monotonic() + self.ttl
        return missing

    @staticmethod
    def keyboard(missing: list[Channel], lang: str) -> InlineKeyboardMarkup:
        many = len(missing) > 1
        rows = [
            [InlineKeyboardButton(text=t(lang, "BTN_CHANNEL") + (f" {i}" if many else ""),
                                  url=ch.link, style=ButtonStyle.PRIMARY)]
            for i, ch in enumerate(missing, 1)
            if ch.link
        ]
        rows.append([InlineKeyboardButton(text=t(lang, "BTN_CHECK_SUB"), callback_data="check_sub",
                                          style=ButtonStyle.SUCCESS)])
        return InlineKeyboardMarkup(inline_keyboard=rows)


# ----------------------------------------------------------------------------------
# Yordamchilar
# ----------------------------------------------------------------------------------
def link_key(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode()).hexdigest()[:16]


def cache_key(kind: str, url: str) -> str:
    return f"{kind}:{normalize_url(url)}"


def shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]) + "…"


def make_caption(title: str, bot_username: str | None, show_title: bool = True) -> str:
    tail = f"📥 @{bot_username}" if bot_username else ""
    title = html.escape(shorten(title, 200), quote=False) if (show_title and title) else ""
    return "\n\n".join(x for x in (title, tail) if x)


def error_text(code: str, cfg: Config, lang: str) -> str:
    if code == "too_big":
        return t(lang, "ERR_TOO_BIG", max_mb=cfg.max_mb)
    if code == "too_long":
        return t(lang, "ERR_TOO_LONG", minutes=cfg.max_duration // 60)
    key = {"private": "ERR_PRIVATE", "unsupported": "ERR_UNSUPPORTED", "not_found": "ERR_NOT_FOUND",
           "live": "ERR_LIVE", "timeout": "ERR_TIMEOUT"}.get(code, "ERR_FAILED")
    return t(lang, key)


def mp3_keyboard(key: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=t(lang, "BTN_AUDIO"), callback_data=f"mp3:{key}", style=ButtonStyle.SUCCESS)]])


async def safe_edit(msg: Message | None, text: str, **kw) -> None:
    if msg is None:
        return
    with contextlib.suppress(TelegramAPIError):
        await msg.edit_text(text, **kw)


async def safe_delete(msg: Message | None) -> None:
    if msg is None:
        return
    with contextlib.suppress(TelegramAPIError):
        await msg.delete()


def _file_of(msg: Message) -> tuple[str, str] | None:
    if msg.video:
        return "video", msg.video.file_id
    if msg.photo:
        return "photo", msg.photo[-1].file_id
    if msg.audio:
        return "audio", msg.audio.file_id
    if msg.animation:
        return "animation", msg.animation.file_id
    if msg.document:
        return "document", msg.document.file_id
    if msg.voice:
        return "audio", msg.voice.file_id
    return None


# ----------------------------------------------------------------------------------
# Yuborish (yangi fayllar ham, keshdagi file_id lar ham bir xil yo'l bilan)
# ----------------------------------------------------------------------------------
@dataclass
class Outgoing:
    kind: str
    source: str | FSInputFile  # file_id yoki fayl
    width: int | None = None
    height: int | None = None
    duration: int | None = None


async def _retry(call: Callable[[], Awaitable], attempts: int = 3):
    for i in range(attempts):
        try:
            return await call()
        except TelegramRetryAfter as e:
            if i == attempts - 1:
                raise
            await asyncio.sleep(e.retry_after + 1)


async def send_media(
    bot: Bot,
    chat_id: int,
    items: list[Outgoing],
    caption: str,
    reply_to: int | None = None,
    markup: InlineKeyboardMarkup | None = None,
    audio_title: str | None = None,
    performer: str | None = None,
) -> list[tuple[str, str]]:
    """Fayllarni yuboradi: rasm/video bir nechta bo'lsa — albom (10 tadan), qolganlari alohida.

    Qaytaradi: [(turi, file_id), ...] — keshga yozish uchun.
    """
    reply = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
    timeout = 1800  # katta fayllarni (Local Bot API bilan 2 GB gacha) yuklash uchun
    sent: list[tuple[str, str]] = []
    caption_used = False

    def take_caption() -> str | None:
        nonlocal caption_used
        if caption_used or not caption:
            return None
        caption_used = True
        return caption

    visual = [i for i in items if i.kind in ("photo", "video")]
    others = [i for i in items if i.kind not in ("photo", "video")]

    if len(visual) >= 2:
        for start in range(0, len(visual), 10):
            chunk = visual[start:start + 10]
            if len(chunk) == 1:  # albomda kamida 2 ta element bo'lishi kerak
                others.insert(0, chunk[0])
                continue
            media = []
            for item in chunk:
                cap = take_caption()
                if item.kind == "photo":
                    media.append(InputMediaPhoto(media=item.source, caption=cap))
                else:
                    media.append(InputMediaVideo(
                        media=item.source, caption=cap, width=item.width, height=item.height,
                        duration=item.duration, supports_streaming=True,
                    ))
            msgs = await _retry(lambda: bot.send_media_group(
                chat_id, media, reply_parameters=reply, request_timeout=timeout))
            sent += [f for f in map(_file_of, msgs) if f]
    else:
        others = visual + others

    single = len(items) == 1
    for item in others:
        common = dict(caption=take_caption(), reply_parameters=reply, request_timeout=timeout,
                      reply_markup=markup if single else None)
        if item.kind == "video":
            call = lambda: bot.send_video(  # noqa: E731
                chat_id, item.source, width=item.width, height=item.height,
                duration=item.duration, supports_streaming=True, **common)
        elif item.kind == "photo":
            call = lambda: bot.send_photo(chat_id, item.source, **common)  # noqa: E731
        elif item.kind == "audio":
            call = lambda: bot.send_audio(  # noqa: E731
                chat_id, item.source, title=(audio_title or None) and audio_title[:64],
                performer=(performer or None) and performer[:64], **common)
        elif item.kind == "animation":
            call = lambda: bot.send_animation(chat_id, item.source, **common)  # noqa: E731
        else:
            call = lambda: bot.send_document(chat_id, item.source, **common)  # noqa: E731
        msg = await _retry(call)
        if f := _file_of(msg):
            sent.append(f)
    return sent


# ----------------------------------------------------------------------------------
# Havolani qayta ishlashning to'liq jarayoni
# ----------------------------------------------------------------------------------
@dataclass
class Deps:
    bot: Bot
    cfg: Config
    db: Database
    downloader: Downloader
    queue: DownloadQueue


async def _progress_ticker(status: Message, progress: Progress, lang: str) -> None:
    last = None
    while True:
        await asyncio.sleep(3)
        if progress.stage == "process":
            text = t(lang, "PROCESSING")
        elif progress.percent is not None:
            text = t(lang, "PROGRESS", bar=progress_bar(progress.percent), percent=progress.percent)
        else:
            continue
        if text != last:
            await safe_edit(status, text)
            last = text


async def deliver(
    d: Deps,
    *,
    chat_id: int,
    user_id: int,
    url: str,
    kind: str,
    reply_to: int | None,
    status: Message | None = None,
    quality: int | None = None,
    info: dict | None = None,
    ytdlp_error: DownloadError | None = None,
    lang: str = "uz",
) -> bool:
    """Havolani yuklab, foydalanuvchiga yuboradi. Muvaffaqiyatli bo'lsa True.

    quality — tanlangan sifat (360/720/1080/1440...), None bo'lsa avtomatik."""
    platform = platform_of(url)
    me = await d.bot.me()

    async def fail(text: str) -> None:
        if status:
            await safe_edit(status, text)
        else:
            reply = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
            with contextlib.suppress(TelegramAPIError):
                await d.bot.send_message(chat_id, text, reply_parameters=reply)

    if not await is_public_url(url):
        await fail(t(lang, "ERR_UNSUPPORTED"))
        return False

    key = link_key(url)
    await d.db.link_put(key, url)
    markup_for_single = mp3_keyboard(key, lang) if kind == "video" else None

    # 1) Kesh: shu havola avval yuklangan bo'lsa — darhol yuboramiz
    ckey = cache_key(f"video{quality}" if kind == "video" and quality else kind, url)
    cached = await d.db.cache_get(ckey, d.cfg.cache_days)
    if cached:
        items = [Outgoing(k, fid) for k, fid in cached.items]
        markup = markup_for_single if len(items) == 1 and items[0].kind == "video" else None
        try:
            await send_media(d.bot, chat_id, items, make_caption(cached.title, me.username),
                             reply_to, markup)
            await safe_delete(status)
            await d.db.log_download(user_id, platform, kind, True, from_cache=True)
            return True
        except TelegramBadRequest as e:
            log.info("Keshdagi file_id yaroqsiz, qayta yuklaymiz: %s", e)
            await d.db.cache_delete(ckey)

    # 2) Navbat
    if not d.queue.try_reserve(user_id):
        await fail(t(lang, "TOO_MANY"))
        return False

    workdir = tempfile.mkdtemp(prefix="dl_", dir=d.cfg.tmp_dir)
    ticker: asyncio.Task | None = None
    ok = False
    try:
        if status:
            await safe_edit(status, t(lang, "STARTING"))
        else:
            reply = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
            status = await d.bot.send_message(chat_id, t(lang, "STARTING"), reply_parameters=reply)

        progress = Progress()
        async with d.queue.slot(on_wait=lambda pos: safe_edit(status, t(lang, "QUEUED", pos=pos))):
            await safe_edit(status, t(lang, "STARTING"))
            with contextlib.suppress(TelegramAPIError):
                await d.bot.send_chat_action(
                    chat_id, ChatAction.UPLOAD_VOICE if kind == "audio" else ChatAction.UPLOAD_VIDEO)
            ticker = asyncio.create_task(_progress_ticker(status, progress, lang))
            result = await asyncio.wait_for(
                d.downloader.download(url, kind, workdir, progress, quality=quality,
                                      info=info, ytdlp_error=ytdlp_error),
                timeout=d.cfg.download_timeout + 120,
            )
            files = await prepare_files(result, d.cfg.max_bytes)
            ticker.cancel()
        if not files:
            raise DownloadError("too_big")

        await safe_edit(status, t(lang, "UPLOADING"))
        items = [Outgoing(f.kind, FSInputFile(f.path), f.width, f.height, f.duration) for f in files]
        single_video = len(items) == 1 and items[0].kind == "video"
        sent = await send_media(
            d.bot, chat_id, items, make_caption(result.title, me.username), reply_to,
            markup_for_single if single_video else None,
            audio_title=result.title, performer=result.performer,
        )
        if sent:
            await d.db.cache_set(ckey, sent, result.title)
        await safe_delete(status)
        ok = True
    except DownloadError as e:
        log.info("Yuklanmadi [%s] %s: %s", e.code, url, e.detail[:200])
        await fail(error_text(e.code, d.cfg, lang))
    except asyncio.TimeoutError:
        log.warning("Vaqt tugadi: %s", url)
        await fail(t(lang, "ERR_TIMEOUT"))
    except TelegramEntityTooLarge:
        await fail(error_text("too_big", d.cfg, lang))
    except Exception:
        log.exception("Kutilmagan xato: %s", url)
        await fail(t(lang, "ERR_UNEXPECTED"))
    finally:
        if ticker:
            ticker.cancel()
        d.queue.release(user_id)
        shutil.rmtree(workdir, ignore_errors=True)
    with contextlib.suppress(Exception):
        await d.db.log_download(user_id, platform, kind, ok)
    return ok


# ----------------------------------------------------------------------------------
# Sifat tanlash
# ----------------------------------------------------------------------------------
class ProbeCache:
    """Sifatlar ro'yxatini qisqa muddat eslab qoladi (bir xil havolani qayta tekshirmaslik uchun)."""

    def __init__(self, ttl: int = 1800, limit: int = 2000):
        self.ttl = ttl
        self.limit = limit
        self._data: dict[str, tuple[float, Probe]] = {}

    def get(self, url: str) -> Probe | None:
        item = self._data.get(normalize_url(url))
        if item and item[0] > time.monotonic():
            return item[1]
        return None

    def put(self, url: str, probe: Probe) -> None:
        if len(self._data) >= self.limit:
            now = time.monotonic()
            self._data = {k: v for k, v in self._data.items() if v[0] > now}
            if len(self._data) >= self.limit:
                self._data.clear()
        # Og'ir "info" ni saqlamaymiz — faqat sifatlar va nomi
        light = Probe(info={}, title=probe.title, duration=probe.duration, options=probe.options)
        self._data[normalize_url(url)] = (time.monotonic() + self.ttl, light)


def _mb(size: int | None) -> str:
    if not size:
        return ""
    mb = size / 1024 / 1024
    return f" · {mb:.0f} MB" if mb >= 10 else f" · {mb:.1f} MB"


def _duration(sec: float | None) -> str:
    if not sec:
        return ""
    sec = int(sec)
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def quality_picker(probe: Probe, key: str, cfg: Config, lang: str = "uz") -> tuple[str, InlineKeyboardMarkup]:
    """Sifat tanlash xabari: sig'adiganlari tugma, sig'maydiganlari izohda."""
    fits = [o for o in probe.options if not o.size or o.size <= cfg.max_bytes]
    too_big = [o for o in probe.options if o.size and o.size > cfg.max_bytes]

    # Video sifatlari — ko'k, MP3 — yashil (Telegram rangli tugmalari)
    buttons = [InlineKeyboardButton(text=f"📹 {quality_name(o.label)}{_mb(o.size)}",
                                    callback_data=f"q:{o.label}:{key}", style=ButtonStyle.PRIMARY)
               for o in fits]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    mp3_size = int(probe.duration * 192_000 / 8) if probe.duration else None
    rows.append([InlineKeyboardButton(text=f"{t(lang, 'BTN_AUDIO')}{_mb(mp3_size)}",
                                      callback_data=f"fmt:a:{key}", style=ButtonStyle.SUCCESS)])

    lines = []
    if probe.title:
        lines.append(f"🎬 <b>{html.escape(shorten(probe.title, 150), quote=False)}</b>")
    if probe.duration:
        lines.append(f"⏱ {_duration(probe.duration)}")
    lines.append("")
    lines.append(t(lang, "CHOOSE_QUALITY"))
    if too_big:
        names = ", ".join(quality_name(o.label) for o in too_big)
        lines.append(t(lang, "QUALITY_TOO_BIG", names=names, max_mb=cfg.max_mb))
    return "\n".join(lines).strip(), InlineKeyboardMarkup(inline_keyboard=rows)


async def handle_link(d: Deps, probes: ProbeCache, *, chat_id: int, user_id: int, url: str,
                      reply_to: int | None, lang: str = "uz") -> None:
    """Yangi havola: kerak bo'lsa sifat tanlovini ko'rsatadi, aks holda darhol yuklaydi."""
    common = dict(chat_id=chat_id, user_id=user_id, url=url, reply_to=reply_to, lang=lang)
    if is_audio_site(url):
        await deliver(d, kind="audio", **common)
        return
    if not d.cfg.ask_quality or prefers_gallery(url):
        await deliver(d, kind="video", **common)
        return
    if not await is_public_url(url):
        await deliver(d, kind="video", **common)  # deliver o'zi xato xabarini yuboradi
        return
    # Avval yuklangan (bitta sifatli) havola — keshdan darhol
    if await d.db.cache_get(cache_key("video", url), d.cfg.cache_days):
        await deliver(d, kind="video", **common)
        return

    key = link_key(url)
    await d.db.link_put(key, url)
    probe = probes.get(url)
    status = None
    if probe is None:
        reply = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
        status = await d.bot.send_message(chat_id, t(lang, "CHECKING"), reply_parameters=reply)
        try:
            async with d.queue.probe_slots:
                probe = await asyncio.wait_for(d.downloader.probe(url), timeout=120)
        except DownloadError as e:
            if e.code in FATAL_CODES:
                await safe_edit(status, error_text(e.code, d.cfg, lang))
                return
            # yt-dlp tanimadi — rasm bo'lishi mumkin, gallery-dl bilan urinamiz
            await deliver(d, kind="video", status=status, ytdlp_error=e, **common)
            return
        except asyncio.TimeoutError:
            await safe_edit(status, t(lang, "ERR_TIMEOUT"))
            return
        except Exception:
            log.exception("Probe xatosi: %s", url)
            await safe_edit(status, t(lang, "ERR_UNEXPECTED"))
            return

    if len(probe.options) < 2:
        # Tanlash uchun variant yo'q (TikTok, karusel, rasm...) — darhol yuklaymiz
        await deliver(d, kind="video", status=status, info=probe.info or None, **common)
        return

    probes.put(url, probe)
    text, markup = quality_picker(probe, key, d.cfg, lang)
    if status:
        await safe_edit(status, text, reply_markup=markup)
    else:
        reply = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
        await d.bot.send_message(chat_id, text, reply_markup=markup, reply_parameters=reply)
