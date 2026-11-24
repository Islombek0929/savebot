"""Middleware'lar: foydalanuvchini ro'yxatga olish, ban va flood'dan himoya."""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from .db import Database
from .texts import guess_lang


class UserMiddleware(BaseMiddleware):
    """Ban qilinganlarni o'tkazmaydi, shaxsiy chatdagi foydalanuvchilarni bazaga yozadi
    va juda tez-tez xabar yuboruvchilarni (flood) cheklaydi."""

    def __init__(self, db: Database, banned: set[int], admin_ids: frozenset[int],
                 rate: int = 8, per_seconds: float = 10.0):
        self.db = db
        self.banned = banned
        self.admin_ids = admin_ids
        self.rate = rate
        self.per_seconds = per_seconds
        self._touched: dict[int, float] = {}
        self._hits: dict[int, list[float]] = {}
        # user_id -> tanlangan til (None — hali tanlamagan)
        self._langs: dict[int, str | None] = {}

    def remember_lang(self, user_id: int, lang: str) -> None:
        self._langs[user_id] = lang

    async def _lang(self, user) -> tuple[str, bool]:
        if user.id not in self._langs:
            if len(self._langs) > 100_000:
                self._langs.clear()
            self._langs[user.id] = await self.db.get_lang(user.id)
        chosen = self._langs[user.id]
        return (chosen or guess_lang(user.language_code)), chosen is not None

    def _flooding(self, user_id: int) -> bool:
        now = time.monotonic()
        hits = [t for t in self._hits.get(user_id, []) if now - t < self.per_seconds]
        hits.append(now)
        self._hits[user_id] = hits
        if len(self._hits) > 20_000:
            self._hits = {k: v for k, v in self._hits.items() if now - v[-1] < self.per_seconds}
        return len(hits) > self.rate

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.is_bot:
            return await handler(event, data)
        if user.id in self.banned:
            if isinstance(event, CallbackQuery):
                await event.answer()
            return None

        chat = data.get("event_chat")
        private = chat is not None and chat.type == "private"
        if private:
            now = time.monotonic()
            last = self._touched.get(user.id)
            if last is None or now - last > 300:  # monotonic() kichik bo'lishi mumkin (yangi yongan server)
                self._touched[user.id] = now
                await self.db.touch_user(user.id, user.first_name, user.username)

        if user.id not in self.admin_ids and isinstance(event, Message) and self._flooding(user.id):
            return None
        data["lang"], data["lang_chosen"] = await self._lang(user)
        data["is_admin"] = user.id in self.admin_ids
        return await handler(event, data)
