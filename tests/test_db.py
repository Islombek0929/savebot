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
