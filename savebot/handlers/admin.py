"""Admin panel (tugmalar bilan) va buyruqlar: /admin, /stats, /broadcast, /ban, /unban, /update."""
from __future__ import annotations

import asyncio
import contextlib
import html
import io
import logging
import sys
import time

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ButtonStyle
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import Config
from ..db import Database
from ..downloader import Downloader, versions
from ..middlewares import UserMiddleware
from ..services import AppState, DownloadQueue
from .user import ADMIN_BUTTON

log = logging.getLogger(__name__)


class IsAdmin(Filter):
    async def __call__(self, event: Message | CallbackQuery, config: Config) -> bool:
        return bool(event.from_user and event.from_user.id in config.admin_ids)


ADMIN_TITLE = "🛠 <b>Admin panel</b>\n\nKerakli bo'limni tanlang 👇"
BAN_HELP = (
    "🚫 <b>Ban / Unban</b>\n\n"
    "<code>/ban 123456789</code> — foydalanuvchini bloklash\n"
    "<code>/unban 123456789</code> — blokdan chiqarish\n\n"
    "<i>Foydalanuvchi ID sini @userinfobot orqali bilish mumkin.</i>"
)


def _btn(text: str, data: str, style: ButtonStyle | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data, style=style)


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("📊 Statistika", "adm:stats", ButtonStyle.PRIMARY)],
        [_btn("📢 Xabar yuborish", "adm:bc", ButtonStyle.SUCCESS)],
        [_btn("🍪 Cookies", "adm:ck", ButtonStyle.PRIMARY)],
        [_btn("🔄 yt-dlp yangilash", "adm:upd"), _btn("🚫 Ban / Unban", "adm:ban")],
    ])


def cookies_text(pool) -> str:
    lines = ["🍪 <b>Cookies</b>\n"]
    files = pool.status()
    if not files:
        lines.append("Hozircha cookies yo'q — bot anonim ishlayapti.")
    for f in files:
        parts = []
        for p in f["platforms"]:
            if p["alive"]:
                parts.append(f"✅ {p['platform']}")
            else:
                ago = ""
                if p["since"]:
                    mins = int((time.time() - p["since"]) // 60)
                    ago = f", {mins // 60} soat oldin" if mins >= 60 else f", {mins} daqiqa oldin"
                parts.append(f"❌ {p['platform']} ({html.escape(p['reason'][:60], quote=False)}{ago})")
        lines.append(f"<b>{html.escape(f['name'], quote=False)}</b>: " + (", ".join(parts) or "—"))
    lines.append(
        "\n<b>Yangi cookies qo'shish:</b> «Get cookies.txt LOCALLY» bilan eksport qilingan faylni "
        "Bloknotda oching, hammasini nusxalab (Ctrl+A, Ctrl+C) shu yerga yuboring.\n"
        "<i>Bir nechta Instagram akkaunti qo'shsangiz, bot ularni navbat bilan ishlatadi — "
        "bittasi bloklansa, keyingisiga o'tadi.</i>")
    return "\n".join(lines)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("⬅️ Orqaga", "adm:menu")]])


async def cmd_admin(message: Message) -> None:
    await message.answer(ADMIN_TITLE, reply_markup=admin_keyboard())


async def stats_text(db: Database, queue: DownloadQueue) -> str:
    s = await db.stats()
    top = "\n".join(f"  • {name}: {count}" for name, count in s["top_platforms"]) or "  —"
    v = versions()
    return (
        "📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{s['users']}</b> (bugun +{s['users_today']})\n"
        f"🟢 Faol: bugun {s['active_today']}, 7 kunda {s['active_week']}\n"
        f"🚫 Botni bloklagan: {s['blocked']} | ban: {s['banned']}\n\n"
        f"📥 Yuklashlar: jami <b>{s['dl_total']}</b>, bugun {s['dl_today']} "
        f"(keshdan {s['cache_today']}, xato {s['fail_today']})\n"
        f"⚙️ Hozir: {queue.active}/{queue.parallel} yuklanmoqda, {queue.waiting} navbatda\n\n"
        f"🏆 7 kunlik top platformalar:\n{top}\n\n"
        f"🔧 yt-dlp {v['yt-dlp']}, gallery-dl {v['gallery-dl']}"
    )


async def cmd_stats(message: Message, db: Database, queue: DownloadQueue) -> None:
    await message.answer(await stats_text(db, queue))


async def on_admin_button(cb: CallbackQuery, db: Database, queue: DownloadQueue,
                          app_state: AppState, dispatcher: Dispatcher,
                          downloader: Downloader) -> None:
    action = cb.data.split(":", 1)[1]
    await cb.answer()
    msg = cb.message
    if action == "menu":
        app_state.awaiting_broadcast.discard(cb.from_user.id)
        app_state.awaiting_cookies.discard(cb.from_user.id)
        await msg.edit_text(ADMIN_TITLE, reply_markup=admin_keyboard())
    elif action == "stats":
        refresh = InlineKeyboardMarkup(inline_keyboard=[
            [_btn("🔄 Yangilash", "adm:stats", ButtonStyle.PRIMARY), _btn("⬅️ Orqaga", "adm:menu")]])
        try:
            await msg.edit_text(await stats_text(db, queue), reply_markup=refresh)
        except TelegramAPIError:  # "message is not modified"
            pass
    elif action == "bc":
        if app_state.broadcasting:
            await msg.edit_text("⏳ Oldingi tarqatish hali tugamadi.", reply_markup=back_keyboard())
            return
        app_state.awaiting_broadcast.add(cb.from_user.id)
        count = len(await db.broadcast_ids())
        await msg.edit_text(
            f"📢 <b>Xabar yuborish</b> ({count} ta foydalanuvchi)\n\n"
            "Hammaga yubormoqchi bo'lgan xabarni shu yerga yuboring — matn, rasm, video, "
            "tugmali post, nima bo'lsa ham. Keyin tasdiqlaysiz.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                _btn("❌ Bekor qilish", "adm:menu", ButtonStyle.DANGER)]]),
        )
    elif action == "ban":
        await msg.edit_text(BAN_HELP, reply_markup=back_keyboard())
    elif action == "ck":
        app_state.awaiting_cookies.add(cb.from_user.id)
        try:
            await msg.edit_text(cookies_text(downloader.pool), reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[_btn("🔄 Yangilash", "adm:ck", ButtonStyle.PRIMARY),
                                  _btn("⬅️ Orqaga", "adm:menu")]]))
        except TelegramAPIError:  # "message is not modified"
            pass
    elif action == "upd":
        await msg.edit_text(
            "🔄 yt-dlp va gallery-dl eng yangi versiyaga yangilanadi va bot qayta ishga tushadi "
            "(faol yuklashlar tugashi kutiladi).\n\nDavom etilsinmi?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                _btn("✅ Ha, yangilash", "adm:upd_yes", ButtonStyle.SUCCESS),
                _btn("⬅️ Orqaga", "adm:menu")]]),
        )
    elif action == "upd_yes":
        await msg.edit_reply_markup(reply_markup=None)
        await _do_update(msg, app_state, queue, dispatcher)


class CookiesInput(Filter):
    """Admin «🍪 Cookies» ni bosgan bo'lsa, yoki matn cookies fayli sarlavhasi bilan boshlansa."""

    async def __call__(self, message: Message, app_state: AppState) -> bool:
        text = (message.text or "").lstrip()
        if text.startswith(("# Netscape HTTP Cookie File", "# HTTP Cookie File")):
            return True
        uid = message.from_user.id if message.from_user else None
        return uid in app_state.awaiting_cookies and (bool(message.text) or bool(message.document))


async def on_cookies_input(message: Message, bot: Bot, downloader: Downloader,
                           app_state: AppState) -> None:
    text = message.text or ""
    if message.document:
        if (message.document.file_size or 0) > 1_000_000:
            await message.answer("❌ Fayl juda katta — cookies fayli odatda bir necha KB bo'ladi.")
            return
        try:
            buf = io.BytesIO()
            await bot.download(message.document, destination=buf)
            text = buf.getvalue().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001 — Local Bot API'da fayl o'qilmasligi mumkin
            log.info("Cookies faylini yuklab bo'lmadi: %s", e)
            await message.answer("❌ Faylni o'qib bo'lmadi. Uni Bloknotda ochib, matnini nusxalab yuboring.")
            return
    try:
        name, platforms = downloader.pool.save_upload(text)
    except ValueError as e:
        await message.answer(f"❌ {html.escape(str(e), quote=False)}")
        return
    finally:
        with contextlib.suppress(TelegramAPIError):
            await message.delete()  # chatda maxfiy sessiya qolmasin
    app_state.awaiting_cookies.discard(message.from_user.id)
    await message.answer(
        f"✅ Saqlandi: <b>{name}</b> ({', '.join(platforms)}). Darhol ishlatiladi, qayta ishga "
        "tushirish shart emas.\n\n" + cookies_text(downloader.pool),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_btn("⬅️ Admin panel", "adm:menu")]]),
    )


class AwaitingBroadcast(Filter):
    async def __call__(self, message: Message, app_state: AppState) -> bool:
        return bool(message.from_user and message.from_user.id in app_state.awaiting_broadcast)


async def on_broadcast_source(message: Message, db: Database, app_state: AppState) -> None:
    """Admin «Xabar yuborish» ni bosgandan keyin yuborgan xabar — tasdiq so'raymiz."""
    app_state.awaiting_broadcast.discard(message.from_user.id)
    await _ask_broadcast_confirm(message, message.message_id, db)


async def _ask_broadcast_confirm(message: Message, source_id: int, db: Database) -> None:
    count = len(await db.broadcast_ids())
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        _btn(f"✅ Ha, {count} kishiga", f"bc:yes:{source_id}", ButtonStyle.SUCCESS),
        _btn("❌ Bekor", "bc:no", ButtonStyle.DANGER),
    ]])
    await message.answer(f"Yuqoridagi xabar {count} ta foydalanuvchiga yuborilsinmi?", reply_markup=kb)


async def cmd_ban(message: Message, command: CommandObject, db: Database,
                  user_mw: UserMiddleware) -> None:
    if not command.args or not command.args.strip().lstrip("-").isdigit():
        await message.answer(f"Foydalanish: /{command.command} <code>USER_ID</code>")
        return
    user_id = int(command.args.strip())
    ban = command.command == "ban"
    found = await db.set_banned(user_id, ban)
    if ban:
        user_mw.banned.add(user_id)
    else:
        user_mw.banned.discard(user_id)
    note = "" if found else " (bazada hali yo'q edi)"
    await message.answer(f"{'🚫 Bloklandi' if ban else '✅ Blokdan chiqarildi'}: <code>{user_id}</code>{note}")


# ---------------- broadcast ----------------
async def cmd_broadcast(message: Message, db: Database, app_state: AppState) -> None:
    src = message.reply_to_message
    if not src:
        await message.answer("Yubormoqchi bo'lgan xabarga <b>reply</b> qilib /broadcast yozing.")
        return
    if app_state.broadcasting:
        await message.answer("⏳ Oldingi tarqatish hali tugamadi.")
        return
    await _ask_broadcast_confirm(message, src.message_id, db)


async def on_broadcast(cb: CallbackQuery, bot: Bot, db: Database, app_state: AppState) -> None:
    parts = cb.data.split(":")
    if parts[1] != "yes":
        await cb.message.edit_text("Bekor qilindi.")
        return
    if app_state.broadcasting:
        await cb.answer("Tarqatish allaqachon ketmoqda", show_alert=True)
        return
    await cb.answer()
    app_state.broadcasting = True
    await cb.message.edit_text("📤 Tarqatish boshlandi...")
    asyncio.create_task(
        _broadcast(bot, db, app_state, cb.message.chat.id, int(parts[2]), cb.message)
    )


async def _broadcast(bot: Bot, db: Database, app_state: AppState, from_chat: int, message_id: int,
                     report: Message) -> None:
    ok = failed = blocked = 0
    try:
        ids = await db.broadcast_ids()
        for i, user_id in enumerate(ids, 1):
            for _ in range(3):
                try:
                    await bot.copy_message(user_id, from_chat, message_id)
                    ok += 1
                    break
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after + 1)
                except TelegramForbiddenError:
                    blocked += 1
                    await db.set_blocked(user_id)
                    break
                except TelegramAPIError:
                    failed += 1
                    break
            await asyncio.sleep(0.05)  # ~20 xabar/soniya — Telegram limiti 30
            if i % 500 == 0:
                try:
                    await report.edit_text(f"📤 Yuborilmoqda: {i}/{len(ids)}")
                except TelegramAPIError:
                    pass
    finally:
        app_state.broadcasting = False
    try:
        await report.edit_text(
            f"✅ Tarqatish tugadi.\nYuborildi: {ok}\nBotni bloklagan: {blocked}\nXato: {failed}"
        )
    except TelegramAPIError:
        pass


# ---------------- update ----------------
async def cmd_update(message: Message, app_state: AppState, queue: DownloadQueue,
                     dispatcher: Dispatcher) -> None:
    await _do_update(message, app_state, queue, dispatcher)


async def _do_update(message: Message, app_state: AppState, queue: DownloadQueue,
                     dispatcher: Dispatcher) -> None:
    before = versions()
    msg = await message.answer("🔄 Yangilanmoqda...")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pip", "install", "-q", "-U", "--no-cache-dir",
        "yt-dlp[default]", "gallery-dl",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        await msg.edit_text(f"❌ Yangilab bo'lmadi:\n<code>{out.decode(errors='replace')[-1500:]}</code>")
        return
    await msg.edit_text(
        f"✅ O'rnatildi. Avval: yt-dlp {before['yt-dlp']}, gallery-dl {before['gallery-dl']}.\n"
        "♻️ Faol yuklashlar tugagach bot qayta ishga tushadi (yangi versiya shunda yuklanadi)."
    )
    for _ in range(300):  # 5 daqiqagacha kutamiz
        if queue.busy == 0:
            break
        await asyncio.sleep(1)
    app_state.restart_requested = True
    await dispatcher.stop_polling()


def get_router() -> Router:
    router = Router(name="admin")
    router.message.filter(IsAdmin())
    router.callback_query.filter(IsAdmin())
    router.message.register(cmd_admin, Command("admin"))
    router.message.register(cmd_admin, F.chat.type == "private", F.text == ADMIN_BUTTON)
    router.callback_query.register(on_admin_button, F.data.startswith("adm:"))
    router.message.register(on_cookies_input, F.chat.type == "private", CookiesInput())
    # «Xabar yuborish» bosilgandan keyingi xabar (buyruqlardan tashqari)
    router.message.register(on_broadcast_source, F.chat.type == "private", AwaitingBroadcast(),
                            ~F.text.startswith("/"))
    router.message.register(cmd_stats, Command("stats"))
    router.message.register(cmd_ban, Command("ban", "unban"))
    router.message.register(cmd_broadcast, Command("broadcast"))
    router.callback_query.register(on_broadcast, F.data.startswith("bc:"))
    router.message.register(cmd_update, Command("update"))
    return router
