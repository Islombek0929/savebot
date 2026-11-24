"""SQLite ma'lumotlar bazasi: foydalanuvchilar, statistika, fayl keshi va havolalar."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    first_name  TEXT,
    username    TEXT,
    joined_at   INTEGER NOT NULL,
    last_seen   INTEGER NOT NULL,
    is_banned   INTEGER NOT NULL DEFAULT 0,
    is_blocked  INTEGER NOT NULL DEFAULT 0,
    downloads   INTEGER NOT NULL DEFAULT 0,
    lang        TEXT
);
CREATE TABLE IF NOT EXISTS downloads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    platform    TEXT NOT NULL,
    kind        TEXT NOT NULL,
    ok          INTEGER NOT NULL,
    from_cache  INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_downloads_created ON downloads(created_at);
CREATE TABLE IF NOT EXISTS cache (
    key         TEXT PRIMARY KEY,
    items       TEXT NOT NULL,
    title       TEXT,
    created_at  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS links (
    key         TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    created_at  INTEGER NOT NULL
);
"""


@dataclass
class CachedMedia:
    items: list[tuple[str, str]]  # [(turi, file_id), ...]; turi: video/audio/photo/document
    title: str


def _day_start(now: float | None = None) -> int:
    t = time.localtime(now or time.time())
    return int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1)))


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA synchronous=NORMAL")
        await self.conn.executescript(SCHEMA)
        # Eski bazalarni yangilash (migratsiya)
        async with self.conn.execute("PRAGMA table_info(users)") as cur:
            columns = {row[1] for row in await cur.fetchall()}
        if "lang" not in columns:
            await self.conn.execute("ALTER TABLE users ADD COLUMN lang TEXT")
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()
            self.conn = None

    # ---------- foydalanuvchilar ----------
    async def touch_user(self, user_id: int, first_name: str | None, username: str | None) -> None:
        now = int(time.time())
        await self.conn.execute(
            """INSERT INTO users (id, first_name, username, joined_at, last_seen)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET first_name=excluded.first_name,
                   username=excluded.username, last_seen=excluded.last_seen, is_blocked=0""",
            (user_id, first_name, username, now, now),
        )
        await self.conn.commit()

    async def get_lang(self, user_id: int) -> str | None:
        async with self.conn.execute("SELECT lang FROM users WHERE id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def set_lang(self, user_id: int, lang: str) -> None:
        now = int(time.time())
        await self.conn.execute(
            """INSERT INTO users (id, joined_at, last_seen, lang) VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET lang=excluded.lang""",
            (user_id, now, now, lang),
        )
        await self.conn.commit()

    async def is_banned(self, user_id: int) -> bool:
        async with self.conn.execute("SELECT is_banned FROM users WHERE id=?", (user_id,)) as cur:
            row = await cur.fetchone()
        return bool(row and row[0])

    async def banned_ids(self) -> set[int]:
        async with self.conn.execute("SELECT id FROM users WHERE is_banned=1") as cur:
            return {r[0] for r in await cur.fetchall()}

    async def set_banned(self, user_id: int, banned: bool) -> bool:
        cur = await self.conn.execute(
            "UPDATE users SET is_banned=? WHERE id=?", (int(banned), user_id)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def set_blocked(self, user_id: int) -> None:
        await self.conn.execute("UPDATE users SET is_blocked=1 WHERE id=?", (user_id,))
        await self.conn.commit()

    async def broadcast_ids(self) -> list[int]:
        async with self.conn.execute(
            "SELECT id FROM users WHERE is_blocked=0 AND is_banned=0 ORDER BY id"
        ) as cur:
            return [r[0] for r in await cur.fetchall()]

    # ---------- statistika ----------
    async def log_download(
        self, user_id: int, platform: str, kind: str, ok: bool, from_cache: bool = False
    ) -> None:
        await self.conn.execute(
            "INSERT INTO downloads (user_id, platform, kind, ok, from_cache, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, platform, kind, int(ok), int(from_cache), int(time.time())),
        )
        if ok:
            await self.conn.execute("UPDATE users SET downloads=downloads+1 WHERE id=?", (user_id,))
        await self.conn.commit()

    async def stats(self) -> dict:
        today = _day_start()
        week = today - 6 * 86400

        async def one(sql: str, *args) -> int:
            async with self.conn.execute(sql, args) as cur:
                row = await cur.fetchone()
            return int(row[0] or 0)

        async with self.conn.execute(
            "SELECT platform, COUNT(*) c FROM downloads WHERE created_at>=? AND ok=1"
            " GROUP BY platform ORDER BY c DESC LIMIT 7",
            (week,),
        ) as cur:
            top = [(r[0], r[1]) for r in await cur.fetchall()]

        return {
            "users": await one("SELECT COUNT(*) FROM users"),
            "users_today": await one("SELECT COUNT(*) FROM users WHERE joined_at>=?", today),
            "active_today": await one("SELECT COUNT(*) FROM users WHERE last_seen>=?", today),
            "active_week": await one("SELECT COUNT(*) FROM users WHERE last_seen>=?", week),
            "blocked": await one("SELECT COUNT(*) FROM users WHERE is_blocked=1"),
            "banned": await one("SELECT COUNT(*) FROM users WHERE is_banned=1"),
            "dl_total": await one("SELECT COUNT(*) FROM downloads WHERE ok=1"),
            "dl_today": await one(
                "SELECT COUNT(*) FROM downloads WHERE ok=1 AND created_at>=?", today
            ),
            "fail_today": await one(
                "SELECT COUNT(*) FROM downloads WHERE ok=0 AND created_at>=?", today
            ),
            "cache_today": await one(
                "SELECT COUNT(*) FROM downloads WHERE from_cache=1 AND created_at>=?", today
            ),
            "top_platforms": top,
        }

    # ---------- fayl keshi (Telegram file_id) ----------
    async def cache_get(self, key: str, max_age_days: int) -> CachedMedia | None:
        async with self.conn.execute(
            "SELECT items, title, created_at FROM cache WHERE key=?", (key,)
        ) as cur:
            row = await cur.fetchone()
        if not row or row[2] < time.time() - max_age_days * 86400:
            return None
        return CachedMedia(items=[tuple(i) for i in json.loads(row[0])], title=row[1] or "")

    async def cache_set(self, key: str, items: list[tuple[str, str]], title: str) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO cache (key, items, title, created_at) VALUES (?, ?, ?, ?)",
            (key, json.dumps(items), title, int(time.time())),
        )
        await self.conn.commit()

    async def cache_delete(self, key: str) -> None:
        await self.conn.execute("DELETE FROM cache WHERE key=?", (key,))
        await self.conn.commit()

    # ---------- havolalar (inline tugmalar uchun; callback_data 64 baytdan oshmasligi kerak) ----------
    async def link_put(self, key: str, url: str) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO links (key, url, created_at) VALUES (?, ?, ?)",
            (key, url, int(time.time())),
        )
        await self.conn.commit()

    async def link_get(self, key: str) -> str | None:
        async with self.conn.execute("SELECT url FROM links WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def cleanup(self, cache_days: int, link_days: int = 14) -> None:
        now = int(time.time())
        await self.conn.execute("DELETE FROM cache WHERE created_at<?", (now - cache_days * 86400,))
        await self.conn.execute("DELETE FROM links WHERE created_at<?", (now - link_days * 86400,))
        await self.conn.execute("DELETE FROM downloads WHERE created_at<?", (now - 180 * 86400,))
        await self.conn.commit()
