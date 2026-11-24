import time

from savebot.db import Database


async def test_users_and_ban(db: Database):
    await db.touch_user(10, "Ali", "ali")
    await db.touch_user(11, "Vali", None)
    assert not await db.is_banned(10)
    assert await db.set_banned(10, True)
    assert await db.is_banned(10)
    assert await db.banned_ids() == {10}
    assert await db.broadcast_ids() == [11]
    await db.set_blocked(11)
    assert await db.broadcast_ids() == []
    await db.touch_user(11, "Vali", None)  # qayta yozsa — blokdan chiqqan hisoblanadi
    assert await db.broadcast_ids() == [11]
    assert not await db.set_banned(999, True)  # bazada yo'q


async def test_cache_roundtrip_and_ttl(db: Database):
    await db.cache_set("video:https://x", [("video", "FILEID")], "sarlavha")
    hit = await db.cache_get("video:https://x", 30)
    assert hit.items == [("video", "FILEID")] and hit.title == "sarlavha"
    await db.conn.execute("UPDATE cache SET created_at=?", (int(time.time()) - 40 * 86400,))
    assert await db.cache_get("video:https://x", 30) is None
    await db.cleanup(30)
    async with db.conn.execute("SELECT COUNT(*) FROM cache") as cur:
        assert (await cur.fetchone())[0] == 0


async def test_links(db: Database):
    await db.link_put("abc", "https://a")
    assert await db.link_get("abc") == "https://a"
    assert await db.link_get("zzz") is None


async def test_stats(db: Database):
    await db.touch_user(1, "A", None)
    await db.log_download(1, "instagram", "video", True)
    await db.log_download(1, "instagram", "video", True, from_cache=True)
    await db.log_download(1, "tiktok", "video", False)
    s = await db.stats()
    assert s["users"] == 1 and s["dl_total"] == 2 and s["fail_today"] == 1
    assert s["cache_today"] == 1
    assert s["top_platforms"][0] == ("instagram", 2)


async def test_old_database_is_migrated(tmp_path):
    import aiosqlite
    path = str(tmp_path / "old.db")
    async with aiosqlite.connect(path) as conn:  # 1-versiyadagi jadval (lang ustunisiz)
        await conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, first_name TEXT, username TEXT,"
                           " joined_at INTEGER NOT NULL, last_seen INTEGER NOT NULL,"
                           " is_banned INTEGER NOT NULL DEFAULT 0, is_blocked INTEGER NOT NULL DEFAULT 0,"
                           " downloads INTEGER NOT NULL DEFAULT 0)")
        await conn.execute("INSERT INTO users VALUES (5, 'A', NULL, 1, 1, 0, 0, 3)")
        await conn.commit()
    db = Database(path)
    await db.connect()
    assert await db.get_lang(5) is None
    await db.set_lang(5, "ru")
    assert await db.get_lang(5) == "ru"
    await db.close()
