"""Oddiy foydalanuvchi uchun handlerlar."""
from __future__ import annotations

import html
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ButtonStyle
from aiogram.filters import Command, CommandStart, Filter
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from ..config import Config
from ..db import Database
from ..downloader import find_url, is_known_platform
from ..middlewares import UserMiddleware
from ..services import Deps, ProbeCache, SubscriptionChecker, deliver, handle_link
from ..texts import LANGS, all_variants, t

log = logging.getLogger(__name__)


def extract_url(message: Message) -> str | None:
    """Matn, izoh (caption) va yashirin havolalardan (text_link) URL topadi."""
    text = message.text or message.caption
    for entity in message.entities or message.caption_entities or []:
        if entity.type == "text_link" and entity.url:
            return find_url(entity.url)
        if entity.type == "url" and text:
            return find_url(entity.extract_from(text))
    return find_url(text)


class HasLink(Filter):
    async def __call__(self, message: Message) -> bool | dict:
        url = extract_url(message)
        return {"url": url} if url else False


# ---------------- klaviaturalar ----------------
def menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """Pastdagi doimiy menyu."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "MENU_LANG"), style=ButtonStyle.PRIMARY),
                   KeyboardButton(text=t(lang, "MENU_HELP"), style=ButtonStyle.SUCCESS)]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="https://...",
    )


def lang_keyboard(current: str | None = None) -> InlineKeyboardMarkup:
    rows = []
    for code, title in LANGS.items():
        selected = code == current
        rows.append([InlineKeyboardButton(
            text=f"{title}  ✓" if selected else title,
            callback_data=f"lang:{code}",
            style=ButtonStyle.SUCCESS if selected else ButtonStyle.PRIMARY,
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


CHOOSE_LANG_ALL = "🌐 Tilni tanlang · Выберите язык · Choose language"


# ---------------- yordamchilar ----------------
def _greeting_name(first_name: str | None) -> str:
    name = (first_name or "").strip()
    if not any(ch.isalnum() for ch in name):  # ism o'rniga "." yoki faqat emoji bo'lsa
        return ""
    return f", <b>{html.escape(name[:40], quote=False)}</b>"


async def _send_start(message: Message, lang: str) -> None:
    await message.answer(t(lang, "START", name=_greeting_name(message.from_user.first_name)),
                         reply_markup=menu_keyboard(lang))


async def _subscribed(bot: Bot, subs: SubscriptionChecker, chat_type: str, user_id: int,
                      answer, lang: str) -> bool:
    if chat_type != "private" or not subs.channels:
        return True
    missing = await subs.missing(bot, user_id)
    if missing:
        await answer(t(lang, "SUBSCRIBE"), reply_markup=subs.keyboard(missing, lang))
        return False
    return True


# ---------------- buyruqlar ----------------
async def cmd_start(message: Message, bot: Bot, subs: SubscriptionChecker, lang: str,
                    lang_chosen: bool) -> None:
    if not lang_chosen:
        # Birinchi marta — avval til so'raymiz
        await message.answer(CHOOSE_LANG_ALL, reply_markup=lang_keyboard())
        return
    await _send_start(message, lang)
    await _subscribed(bot, subs, message.chat.type, message.from_user.id, message.answer, lang)


async def cmd_help(message: Message, config: Config, lang: str) -> None:
    text = t(lang, "HELP", max_mb=config.max_mb)
    if config.contact:
        text += "\n" + t(lang, "CONTACT_LINE", contact=config.contact)
    markup = menu_keyboard(lang) if message.chat.type == "private" else None
    await message.answer(text, reply_markup=markup)


async def cmd_lang(message: Message, lang: str) -> None:
    await message.answer(t(lang, "CHOOSE_LANG"), reply_markup=lang_keyboard(lang))


async def on_lang(cb: CallbackQuery, bot: Bot, db: Database, user_mw: UserMiddleware,
                  subs: SubscriptionChecker, lang_chosen: bool) -> None:
    code = cb.data.split(":", 1)[1]
    if code not in LANGS:
        await cb.answer()
        return
    await db.set_lang(cb.from_user.id, code)
    user_mw.remember_lang(cb.from_user.id, code)
    await cb.answer(t(code, "LANG_SET"))
    if cb.message:
        try:
            await cb.message.edit_text(t(code, "LANG_SET"))
        except Exception:  # noqa: BLE001 — xabar eski bo'lsa ham davom etamiz
            pass
        if not lang_chosen and cb.message.chat.type == "private":
            # Birinchi tanlov — salomlashamiz
            await bot.send_message(
                cb.message.chat.id,
                t(code, "START", name=_greeting_name(cb.from_user.first_name)),
                reply_markup=menu_keyboard(code),
            )
            await _subscribed(bot, subs, "private", cb.from_user.id, cb.message.answer, code)
        else:
            # Menyu tugmalari yangi tilda bo'lishi uchun
            await bot.send_message(cb.message.chat.id, t(code, "SEND_LINK"),
                                   reply_markup=menu_keyboard(code))


async def on_check_sub(cb: CallbackQuery, bot: Bot, subs: SubscriptionChecker, lang: str) -> None:
    missing = await subs.missing(bot, cb.from_user.id)
    if missing:
        await cb.answer(t(lang, "SUB_NOT_YET"), show_alert=True)
        return
    await cb.answer()
    await cb.message.edit_text(t(lang, "SUB_OK"))


# ---------------- havolalar ----------------
async def on_link(message: Message, url: str, deps: Deps, subs: SubscriptionChecker,
                  probes: ProbeCache, lang: str) -> None:
    if message.chat.type != "private" and not is_known_platform(url):
        return  # guruhlarda har qanday havolaga (yangiliklar va h.k.) javob bermaymiz
    if not await _subscribed(deps.bot, subs, message.chat.type, message.from_user.id,
                             message.answer, lang):
        return
    await handle_link(deps, probes, chat_id=message.chat.id, user_id=message.from_user.id,
                      url=url, reply_to=message.message_id, lang=lang)


async def on_format(cb: CallbackQuery, deps: Deps, subs: SubscriptionChecker, lang: str) -> None:
    """fmt:a:KEY — MP3, fmt:v:KEY — video (avtomatik sifat), q:720:KEY — tanlangan sifat."""
    prefix, code, key = cb.data.split(":", 2)
    quality = int(code) if prefix == "q" and code.isdigit() else None
    url = await deps.db.link_get(key)
    if not url or not cb.message:
        await cb.answer(t(lang, "LINK_EXPIRED"), show_alert=True)
        return
    if not await _subscribed(deps.bot, subs, cb.message.chat.type, cb.from_user.id,
                             cb.message.answer, lang):
        await cb.answer()
        return
    await cb.answer()
    original = cb.message.reply_to_message
    await deliver(deps, chat_id=cb.message.chat.id, user_id=cb.from_user.id, url=url,
                  kind="audio" if code == "a" else "video", quality=quality,
                  reply_to=original.message_id if original else None,
                  status=cb.message, lang=lang)


async def on_mp3(cb: CallbackQuery, deps: Deps, subs: SubscriptionChecker, lang: str) -> None:
    key = cb.data.split(":", 1)[1]
    url = await deps.db.link_get(key)
    if not url or not cb.message:
        await cb.answer(t(lang, "LINK_EXPIRED"), show_alert=True)
        return
    if not await _subscribed(deps.bot, subs, cb.message.chat.type, cb.from_user.id,
                             cb.message.answer, lang):
        await cb.answer()
        return
    await cb.answer(t(lang, "AUDIO_PREPARING"))
    await deliver(deps, chat_id=cb.message.chat.id, user_id=cb.from_user.id, url=url,
                  kind="audio", reply_to=cb.message.message_id, lang=lang)


async def on_text(message: Message, lang: str) -> None:
    await message.answer(t(lang, "SEND_LINK"), reply_markup=menu_keyboard(lang))


def get_router() -> Router:
    router = Router(name="user")
    private = F.chat.type == "private"
    router.message.register(cmd_start, CommandStart(), private)
    router.message.register(cmd_help, Command("help"))
    router.message.register(cmd_help, private, F.text.in_(all_variants("MENU_HELP")))
    router.message.register(cmd_lang, Command("lang"))
    router.message.register(cmd_lang, private, F.text.in_(all_variants("MENU_LANG")))
    router.callback_query.register(on_lang, F.data.startswith("lang:"))
    router.callback_query.register(on_check_sub, F.data == "check_sub")
    router.message.register(on_link, HasLink())
    router.callback_query.register(on_format, F.data.startswith("fmt:") | F.data.startswith("q:"))
    router.callback_query.register(on_mp3, F.data.startswith("mp3:"))
    router.message.register(on_text, private, F.text)
    return router
