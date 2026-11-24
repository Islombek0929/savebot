"""Ishga tushirish: python -m savebot"""
from __future__ import annotations

import asyncio
import contextlib
import glob
import logging
import os
import shutil
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from .config import Config, load_config
from .db import Database
from .downloader import Downloader, versions
from .handlers import admin, user
from .middlewares import UserMiddleware
from .texts import DEFAULT_LANG, LANGS, t
from .services import (
    AppState,
    Deps,
    DownloadQueue,
    ProbeCache,
    SubscriptionChecker,
    parse_channels,
)

log = logging.getLogger("savebot")


async def build(cfg: Config, bot: Bot, db: Database) -> Dispatcher:
    """Dispatcher'ni barcha bog'liqliklari bilan yig'adi (testlarda ham ishlatiladi)."""
    queue = DownloadQueue(cfg.max_parallel, cfg.per_user_limit)
    downloader = Downloader(cfg)
    user_mw = UserMiddleware(db, await db.banned_ids(), cfg.admin_ids)
    dp = Dispatcher(
        config=cfg,
        db=db,
        queue=queue,
        downloader=downloader,
        subs=SubscriptionChecker(parse_channels(cfg.required_channels)),
        app_state=AppState(),
        probes=ProbeCache(),
        user_mw=user_mw,
        deps=Deps(bot=bot, cfg=cfg, db=db, downloader=downloader, queue=queue),
    )
    dp.message.outer_middleware(user_mw)
    dp.callback_query.outer_middleware(user_mw)
    dp.include_routers(admin.get_router(), user.get_router())
    return dp


async def _setup_admin_commands(bot: Bot, cfg: Config) -> None:
    """Adminlarning «Menu» ro'yxatida admin buyruqlari ham ko'rinadi."""
    commands = [
        BotCommand(command="start", description="Boshlash"),
        BotCommand(command="admin", description="🛠 Admin panel"),
        BotCommand(command="stats", description="📊 Statistika"),
        BotCommand(command="lang", description="Tilni o'zgartirish"),
        BotCommand(command="help", description="Yordam"),
    ]
    for admin_id in cfg.admin_ids:
        try:
            await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:  # noqa: BLE001
            log.warning("Admin %s uchun menyu o'rnatilmadi (botga /start yozganmi?): %s", admin_id, e)


async def _setup_profile(bot: Bot) -> None:
    """Buyruqlar menyusi va bot ta'rifi — 3 tilda (Telegram ilovasi tiliga qarab ko'rinadi)."""
    for code in LANGS:
        language_code = None if code == DEFAULT_LANG else code  # standart — o'zbekcha
        try:
            await bot.set_my_commands(
                [BotCommand(command="start", description=t(code, "CMD_START")),
                 BotCommand(command="help", description=t(code, "CMD_HELP")),
                 BotCommand(command="lang", description=t(code, "CMD_LANG"))],
                scope=BotCommandScopeAllPrivateChats(),
                language_code=language_code,
            )
            await bot.set_my_description(t(code, "BOT_DESCRIPTION"), language_code=language_code)
            await bot.set_my_short_description(t(code, "BOT_SHORT"), language_code=language_code)
        except Exception as e:  # noqa: BLE001 — profilni sozlay olmasak ham bot ishlayveradi
            log.warning("Bot profilini sozlab bo'lmadi (%s): %s", code, e)


async def _housekeeping(db: Database, cfg: Config) -> None:
    while True:
        with contextlib.suppress(Exception):
            await db.cleanup(cfg.cache_days)
        await asyncio.sleep(6 * 3600)


async def main() -> bool:
    cfg = load_config()
    os.makedirs(cfg.tmp_dir, exist_ok=True)
    for leftover in glob.glob(os.path.join(cfg.tmp_dir, "dl_*")):  # oldingi ishdan qolgan fayllar
        shutil.rmtree(leftover, ignore_errors=True)
    for leftover in glob.glob(os.path.join(cfg.tmp_dir, "ck_*.txt")):
        os.remove(leftover)
    if not shutil.which("ffmpeg"):
        log.warning("ffmpeg topilmadi! Video+audio birlashmaydi va MP3 ishlamaydi.")

    session_kw: dict = {"timeout": 600}  # katta fayllarni yuklash uchun uzun timeout
    if cfg.local_api_url:
        session_kw["api"] = TelegramAPIServer.from_base(cfg.local_api_url, is_local=True)
    session = AiohttpSession(**session_kw)
    bot = Bot(cfg.bot_token, session=session,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML,
                                           link_preview_is_disabled=True))
    db = Database(cfg.db_path)
    housekeeping: asyncio.Task | None = None
    try:
        await db.connect()
        dp = await build(cfg, bot, db)
        me = await bot.me()
        await _setup_profile(bot)
        await _setup_admin_commands(bot, cfg)
        if cfg.cookies:
            log.info("Cookies ulangan: %s", cfg.cookies)
        else:
            log.info("Cookies yo'q (%s) — Instagram tez-tez login so'rashi mumkin", cfg.cookies_file)
        if cfg.admin_ids:
            log.info("Adminlar: %s", ", ".join(map(str, sorted(cfg.admin_ids))))
        else:
            log.warning("ADMIN_IDS bo'sh — admin panel hech kimda ko'rinmaydi (.env ni tekshiring)")
        housekeeping = asyncio.create_task(_housekeeping(db, cfg))
        v = versions()
        log.info("@%s ishga tushdi | limit %s MB | parallel %s | yt-dlp %s | gallery-dl %s",
                 me.username, cfg.max_mb, cfg.max_parallel, v["yt-dlp"], v["gallery-dl"])
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        return dp["app_state"].restart_requested
    finally:
        if housekeeping:
            housekeeping.cancel()
        await db.close()
        await bot.session.close()


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    restart = asyncio.run(main())
    if restart:
        log.info("Qayta ishga tushirilmoqda...")
        os.execv(sys.executable, [sys.executable, "-m", "savebot"])


if __name__ == "__main__":
    run()
