"""Admin buyruqlari: /admin, /stats, /broadcast, /ban, /unban, /update."""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import Config
from ..db import Database
from ..downloader import versions
from ..middlewares import UserMiddleware
from ..services import AppState, DownloadQueue

log = logging.getLogger(__name__)


class IsAdmin(Filter):
    async def __call__(self, event: Message | CallbackQuery, config: Config) -> bool:
        return bool(event.from_user and event.from_user.id in config.admin_ids)


ADMIN_HELP = (
    "🛠 <b>Admin panel</b>\n\n"
    "/stats — statistika\n"
    "/broadcast — xabarga <i>reply</i> qilib yozing: hammaga yuboriladi\n"
    "/ban <code>ID</code> — foydalanuvchini bloklash\n"
    "/unban <code>ID</code> — blokdan chiqarish\n"
    "/update — yt-dlp va gallery-dl ni yangilash (bot qayta ishga tushadi)"
)


async def cmd_admin(message: Message) -> None:
    await message.answer(ADMIN_HELP)


async def cmd_stats(message: Message, db: Database, queue: DownloadQueue) -> None:
    s = await db.stats()
    top = "\n".join(f"  • {name}: {count}" for name, count in s["top_platforms"]) or "  —"
    v = versions()
    await message.answer(
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
    count = len(await db.broadcast_ids())
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"✅ Ha, {count} kishiga", callback_data=f"bc:yes:{src.message_id}"),
        InlineKeyboardButton(text="❌ Bekor", callback_data="bc:no"),
    ]])
    await message.answer(f"Xabar {count} ta foydalanuvchiga yuborilsinmi?", reply_markup=kb)


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
    router.message.register(cmd_stats, Command("stats"))
    router.message.register(cmd_ban, Command("ban", "unban"))
    router.message.register(cmd_broadcast, Command("broadcast"))
    router.callback_query.register(on_broadcast, F.data.startswith("bc:"))
    router.message.register(cmd_update, Command("update"))
    return router
