"""Cookies to'plami: rotatsiya, 401 da chetlash, anonim rejimga o'tish, Telegram orqali yuklash."""
import os

import pytest

from savebot.cookies import CookiePool, parse_cookies
from savebot.downloader import Downloader, DownloadError, Result, MediaFile

IG = ".instagram.com\tTRUE\t/\tTRUE\t2000000000\tsessionid\t{sid}\n" \
     ".instagram.com\tTRUE\t/\tTRUE\t2000000000\tds_user_id\t{uid}\n"
YT = ".youtube.com\tTRUE\t/\tTRUE\t2000000000\tSID\tyyy\n"


def write(path, body):
    path.write_text("# Netscape HTTP Cookie File\n" + body)
    return str(path)


@pytest.fixture
def pool(tmp_path):
    d = tmp_path / "cookies"
    d.mkdir()
    write(d / "a.txt", IG.format(sid="A", uid="1") + YT)
    write(d / "b.txt", IG.format(sid="B", uid="2"))
    return CookiePool(dirs=[str(d)], upload_dir=str(tmp_path / "data" / "cookies"))


def test_rotation_and_platform_filter(pool):
    picks = [os.path.basename(pool.pick("instagram")) for _ in range(4)]
    assert sorted(picks) == ["a.txt", "a.txt", "b.txt", "b.txt"]  # navbat bilan
    assert os.path.basename(pool.pick("youtube")) == "a.txt"
    assert pool.pick("tiktok") is None and pool.pick("example.com") is None


def test_dead_only_for_that_platform_and_reset_on_change(pool, tmp_path):
    a = str(tmp_path / "cookies" / "a.txt")
    pool.mark_dead(a, "instagram", "HTTP Error 401: Unauthorized")
    assert {os.path.basename(pool.pick("instagram")) for _ in range(3)} == {"b.txt"}
    assert os.path.basename(pool.pick("youtube")) == "a.txt"  # YouTube uchun tirik
    st = {f["name"]: f for f in pool.status()}
    ig = next(p for p in st["a.txt"]["platforms"] if p["platform"] == "instagram")
    assert not ig["alive"] and "401" in ig["reason"]
    os.utime(a, (os.path.getmtime(a) + 10,) * 2)  # fayl yangilandi
    assert "a.txt" in {os.path.basename(pool.pick("instagram")) for _ in range(4)}


def test_parse_handles_spaces_instead_of_tabs():
    text = ".instagram.com TRUE / TRUE 2000000000 sessionid abc\n#HttpOnly_.x.com TRUE / TRUE 1 a b\n"
    rows = parse_cookies(text)
    assert rows[0] == [".instagram.com", "TRUE", "/", "TRUE", "2000000000", "sessionid", "abc"]
    assert rows[1][0] == "#HttpOnly_.x.com"


def test_save_upload(pool, tmp_path):
    name, platforms = pool.save_upload(IG.format(sid="C", uid="777").replace("\t", " "))
    assert name == "instagram-777.txt" and platforms == ["instagram"]
    saved = (tmp_path / "data" / "cookies" / name).read_text()
    assert saved.startswith("# Netscape HTTP Cookie File") and "\tsessionid\tC" in saved
    assert "instagram-777.txt" in {os.path.basename(pool.pick("instagram")) for _ in range(3)}
    with pytest.raises(ValueError, match="sessionid"):
        pool.save_upload(".instagram.com\tTRUE\t/\tTRUE\t2000000000\tcsrftoken\tx\n")
    with pytest.raises(ValueError):
        pool.save_upload("salom")


async def test_downloader_rotates_then_anonymous(cfg, pool, tmp_path, monkeypatch):
    dl = Downloader(cfg, pool=pool)
    used = []

    def fake_sync(ctx):
        used.append(os.path.basename(ctx.cookie_source) if ctx.cookie_source else None)
        if ctx.cookie_source:
            raise DownloadError("private", "ERROR: [Instagram] x: HTTP Error 401: Unauthorized")
        path = tmp_path / "ok.mp4"
        path.write_bytes(b"x")
        return Result(files=[MediaFile(str(path), "video")])

    monkeypatch.setattr(dl, "_ytdlp_sync", fake_sync)
    notes = []

    async def notifier(text):
        notes.append(text)

    pool.notifier = notifier
    workdir = tmp_path / "w"
    workdir.mkdir()
    result = await dl.download("https://www.instagram.com/reel/x/", "video", str(workdir))
    assert result.files
    assert sorted(used[:2]) == ["a.txt", "b.txt"] and used[2] is None  # ikkala akkaunt, keyin anonim
    import asyncio
    await asyncio.sleep(0)
    assert len(notes) == 2 and "401" in notes[0]
    used.clear()
    await dl.download("https://www.instagram.com/reel/y/", "video", str(workdir))
    assert used == [None]  # o'lgan cookies qayta sinalmaydi
