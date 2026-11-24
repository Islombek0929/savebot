"""Oddiy foydalanuvchi uchun handlerlar."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, Filter
from aiogram.types import CallbackQuery, Message

from .. import texts
from ..config import Config
from ..downloader import find_url, is_audio_site, is_known_platform, wants_format_choice
from ..services import Deps, SubscriptionChecker, deliver, format_keyboard, link_key

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


def _with_contact(text: str, cfg: Config) -> str:
    return text + (texts.CONTACT_LINE.format(contact=cfg.contact) if cfg.contact else "")


async def cmd_start(message: Message, config: Config, bot: Bot, subs: SubscriptionChecker) -> None:
    await message.answer(texts.START.format(
        name=(message.from_user.first_name or "do'st").replace("<", "").replace(">", ""),
        max_mb=config.max_mb,
    ))
    missing = await subs.missing(bot, message.from_user.id)
    if missing:
        await message.answer(texts.SUBSCRIBE, reply_markup=subs.keyboard(missing))


async def cmd_help(message: Message, config: Config) -> None:
    await message.answer(_with_contact(texts.HELP.format(max_mb=config.max_mb), config))


async def on_check_sub(cb: CallbackQuery, bot: Bot, subs: SubscriptionChecker) -> None:
    missing = await subs.missing(bot, cb.from_user.id)
    if missing:
        await cb.answer(texts.SUB_NOT_YET, show_alert=True)
        return
    await cb.answer()
    await cb.message.edit_text(texts.SUB_OK)


async def _subscribed(bot: Bot, subs: SubscriptionChecker, chat_type: str, user_id: int,
                      answer) -> bool:
    if chat_type != "private" or not subs.channels:
        return True
    missing = await subs.missing(bot, user_id)
    if missing:
        await answer(texts.SUBSCRIBE, reply_markup=subs.keyboard(missing))
        return False
    return True


async def on_link(message: Message, url: str, deps: Deps, subs: SubscriptionChecker) -> None:
    if message.chat.type != "private" and not is_known_platform(url):
        return  # guruhlarda har qanday havolaga (yangiliklar va h.k.) javob bermaymiz
    if not await _subscribed(deps.bot, subs, message.chat.type, message.from_user.id, message.answer):
        return
    if wants_format_choice(url):
        key = link_key(url)
        await deps.db.link_put(key, url)
        await message.reply(texts.CHOOSE_FORMAT, reply_markup=format_keyboard(key))
        return
    kind = "audio" if is_audio_site(url) else "video"
    await deliver(deps, chat_id=message.chat.id, user_id=message.from_user.id, url=url,
                  kind=kind, reply_to=message.message_id)


async def on_format(cb: CallbackQuery, deps: Deps, subs: SubscriptionChecker) -> None:
    _, code, key = cb.data.split(":", 2)
    url = await deps.db.link_get(key)
    if not url or not cb.message:
        await cb.answer(texts.LINK_EXPIRED, show_alert=True)
        return
    if not await _subscribed(deps.bot, subs, cb.message.chat.type, cb.from_user.id,
                             cb.message.answer):
        await cb.answer()
        return
    await cb.answer()
    original = cb.message.reply_to_message
    await deliver(deps, chat_id=cb.message.chat.id, user_id=cb.from_user.id, url=url,
                  kind="audio" if code == "a" else "video",
                  reply_to=original.message_id if original else None,
                  status=cb.message)


async def on_mp3(cb: CallbackQuery, deps: Deps, subs: SubscriptionChecker) -> None:
    key = cb.data.split(":", 1)[1]
    url = await deps.db.link_get(key)
    if not url or not cb.message:
        await cb.answer(texts.LINK_EXPIRED, show_alert=True)
        return
    if not await _subscribed(deps.bot, subs, cb.message.chat.type, cb.from_user.id,
                             cb.message.answer):
        await cb.answer()
        return
    await cb.answer("🎵 MP3 tayyorlanmoqda...")
    await deliver(deps, chat_id=cb.message.chat.id, user_id=cb.from_user.id, url=url,
                  kind="audio", reply_to=cb.message.message_id)


async def on_text(message: Message) -> None:
    await message.answer(texts.SEND_LINK)


def get_router() -> Router:
    router = Router(name="user")
    router.message.register(cmd_start, CommandStart(), F.chat.type == "private")
    router.message.register(cmd_help, Command("help"))
    router.callback_query.register(on_check_sub, F.data == "check_sub")
    router.message.register(on_link, HasLink())
    router.callback_query.register(on_format, F.data.startswith("fmt:"))
    router.callback_query.register(on_mp3, F.data.startswith("mp3:"))
    router.message.register(on_text, F.chat.type == "private", F.text)
    return router
