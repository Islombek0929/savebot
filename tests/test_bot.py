"""Bot handlerlarini soxta Telegram sessiyasi bilan tekshirish (tarmoqsiz)."""
import datetime
import os

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.enums import ChatMemberStatus
from aiogram.methods import (
    CopyMessage,
    DeleteMessage,
    EditMessageText,
    GetChatMember,
    GetMe,
    SendAudio,
    SendMediaGroup,
    SendMessage,
    SendPhoto,
    SendVideo,
)
from aiogram.types import (
    Audio,
    CallbackQuery,
    Chat,
    ChatMemberLeft,
    ChatMemberMember,
    Message,
    PhotoSize,
    Update,
    User,
    Video,
)

from savebot.__main__ import build
from savebot.downloader import DownloadError, MediaFile, Probe, QualityOption, Result

MB = 1024 * 1024

NOW = datetime.datetime.now()
BOT_USER = User(id=42, is_bot=True, first_name="Save", username="save_test_bot")
USER = User(id=500, is_bot=False, first_name="Ali")
ADMIN = User(id=1, is_bot=False, first_name="Admin")


class MockSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.member_status = ChatMemberStatus.MEMBER
        self._mid = 1000

    def _msg(self, chat_id, **kw):
        self._mid += 1
        return Message(message_id=self._mid, date=NOW, chat=Chat(id=chat_id, type="private"),
                       from_user=BOT_USER, **kw)

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        result = self._respond(method)
        if isinstance(result, list):
            return [r.as_(bot) for r in result]
        return result.as_(bot) if hasattr(result, "as_") else result

    def _respond(self, method):
        if isinstance(method, GetMe):
            return BOT_USER
        if isinstance(method, SendVideo):
            return self._msg(method.chat_id, video=Video(
                file_id=f"VID{self._mid}", file_unique_id="u", width=1, height=1, duration=1),
                caption=method.caption)
        if isinstance(method, SendAudio):
            return self._msg(method.chat_id, audio=Audio(file_id=f"AUD{self._mid}", file_unique_id="u", duration=1))
        if isinstance(method, SendPhoto):
            return self._msg(method.chat_id, photo=[PhotoSize(file_id=f"PH{self._mid}", file_unique_id="u", width=1, height=1)])
        if isinstance(method, SendMediaGroup):
            out = []
            for m in method.media:
                if m.type == "photo":
                    out.append(self._msg(method.chat_id, photo=[PhotoSize(file_id=f"PH{self._mid}", file_unique_id="u", width=1, height=1)]))
                else:
                    out.append(self._msg(method.chat_id, video=Video(file_id=f"VID{self._mid}", file_unique_id="u", width=1, height=1, duration=1)))
            return out
        if isinstance(method, (SendMessage, EditMessageText)):
            return self._msg(getattr(method, "chat_id", 0) or 0, text=method.text,
                             reply_markup=method.reply_markup)
        if isinstance(method, GetChatMember):
            if self.member_status == ChatMemberStatus.LEFT:
                return ChatMemberLeft(user=USER)
            return ChatMemberMember(user=USER)
        if isinstance(method, CopyMessage):
            from aiogram.types import MessageId
            return MessageId(message_id=1)
        return True  # SendChatAction, DeleteMessage, AnswerCallbackQuery ...

    async def close(self):
        pass

    async def stream_content(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError

    def of(self, kind):
        return [c for c in self.calls if isinstance(c, kind)]


class FakeDownloader:
    """Haqiqiy yuklash o'rniga workdir'ga fayl yozadi."""

    def __init__(self, kinds=("video",), error=None):
        self.kinds = kinds
        self.error = error
        self.calls = []
        self.kwargs = []
        self.probe_calls = 0
        # Standart: bitta sifat (TikTok/Instagram kabi) — tanlov chiqmaydi
        self.probe_result = Probe(info={"id": "x"}, title="T", duration=30,
                                  options=[QualityOption(1080, "play", 5 * MB)])
        self.probe_error = None

    async def probe(self, url):
        self.probe_calls += 1
        if self.probe_error:
            raise DownloadError(self.probe_error)
        return self.probe_result

    async def download(self, url, kind, workdir, progress=None, **kw):
        self.calls.append((url, kind))
        self.kwargs.append(kw)
        if self.error:
            raise DownloadError(self.error)
        files = []
        kinds = ["audio"] if kind == "audio" else list(self.kinds)
        for i, k in enumerate(kinds):
            ext = {"video": ".mp4", "audio": ".mp3", "photo": ".jpg"}[k]
            path = os.path.join(workdir, f"f{i}{ext}")
            with open(path, "wb") as f:
                f.write(b"x" * 100)
            files.append(MediaFile(path, k))
        return Result(files=files, title="Sarlavha <b>", platform="instagram", performer="Art")


async def _noprobe(path):
    return 720, 1280, 10


@pytest.fixture
async def env(cfg, db, monkeypatch, tmp_path):
    os.makedirs(cfg.tmp_dir, exist_ok=True)
    monkeypatch.setattr("savebot.downloader.probe_video", _noprobe)

    async def public(url):
        return True

    monkeypatch.setattr("savebot.services.is_public_url", public)
    session = MockSession()
    bot = Bot("42:TEST", session=session)
    dp = await build(cfg, bot, db)
    fake = FakeDownloader()
    dp["deps"].downloader = fake
    return dp, bot, session, fake


def message(text, user=USER, chat_type="private", chat_id=None, mid=1):
    return Update(update_id=mid, message=Message(
        message_id=mid, date=NOW, text=text, from_user=user,
        chat=Chat(id=chat_id or user.id, type=chat_type)))


def callback(data, user=USER, msg_text="x", reply_to_mid=None):
    msg = Message(message_id=77, date=NOW, text=msg_text, chat=Chat(id=user.id, type="private"),
                  from_user=BOT_USER)
    return Update(update_id=9, callback_query=CallbackQuery(
        id="cb1", from_user=user, chat_instance="ci", data=data, message=msg))


async def test_start(env):
    dp, bot, session, _ = env
    await dp.feed_update(bot, message("/start"))
    text = session.of(SendMessage)[0].text
    assert "Salom" in text and "Ali" in text


async def test_instagram_link_sends_clean_video_with_mp3_button(env, db):
    dp, bot, session, fake = env
    await dp.feed_update(bot, message("https://www.instagram.com/reel/ABC/?igsh=zz"))
    assert fake.calls == [("https://www.instagram.com/reel/ABC/?igsh=zz", "video")]
    video = session.of(SendVideo)[0]
    assert video.caption == "Sarlavha &lt;b&gt;\n\n📥 @save_test_bot"  # HTML xavfsiz
    assert (video.width, video.height, video.duration) == (720, 1280, 10)
    assert video.reply_markup.inline_keyboard[0][0].callback_data.startswith("mp3:")
    assert session.of(DeleteMessage)  # "Yuklanmoqda" xabari o'chirildi
    s = await db.stats()
    assert s["dl_total"] == 1 and s["users"] == 1


async def test_second_request_served_from_cache(env, db):
    dp, bot, session, fake = env
    await dp.feed_update(bot, message("https://www.instagram.com/reel/ABC/", mid=1))
    await dp.feed_update(bot, message("https://instagram.com/reel/ABC?utm_source=x", mid=2))
    assert len(fake.calls) == 1  # ikkinchisi keshdan
    second = session.of(SendVideo)[1]
    assert isinstance(second.video, str) and second.video.startswith("VID")
    assert (await db.stats())["cache_today"] == 1


async def test_mp3_button(env):
    dp, bot, session, fake = env
    await dp.feed_update(bot, message("https://www.tiktok.com/@u/video/1"))
    data = session.of(SendVideo)[0].reply_markup.inline_keyboard[0][0].callback_data
    await dp.feed_update(bot, callback(data))
    assert fake.calls[-1] == ("https://www.tiktok.com/@u/video/1", "audio")
    audio = session.of(SendAudio)[0]
    assert audio.performer == "Art"


def youtube_probe():
    return Probe(info={}, title="Zo'r <klip>", duration=245, options=[
        QualityOption(360, "18", 12 * MB), QualityOption(480, "135+140", 25 * MB),
        QualityOption(720, "136+140", 45 * MB), QualityOption(1080, "137+140", 98 * MB),
        QualityOption(1440, "271+140", 210 * MB),
    ])


async def test_quality_picker_shown_and_used(env):
    dp, bot, session, fake = env
    fake.probe_result = youtube_probe()
    await dp.feed_update(bot, message("https://youtu.be/dQw4w9WgXcQ"))
    assert not fake.calls
    picker = session.of(EditMessageText)[-1]
    rows = picker.reply_markup.inline_keyboard
    texts_ = [b.text for row in rows for b in row]
    assert texts_ == ["📹 360p · 12 MB", "📹 480p · 25 MB", "📹 720p · 45 MB", "🎵 MP3 · 5.6 MB"]
    assert "Zo'r &lt;klip&gt;" in picker.text and "4:05" in picker.text
    assert "1080p, 2K — 50 MB dan katta" in picker.text
    await dp.feed_update(bot, callback(rows[1][0].callback_data))  # 720p
    assert fake.calls == [("https://youtu.be/dQw4w9WgXcQ", "video")]
    assert fake.kwargs[0]["quality"] == 720
    assert session.of(SendVideo)


async def test_2k_offered_with_local_api(cfg, db, monkeypatch):
    from dataclasses import replace
    cfg = replace(cfg, max_mb=2000, local_api_url="http://telegram-bot-api:8081")
    os.makedirs(cfg.tmp_dir, exist_ok=True)
    monkeypatch.setattr("savebot.downloader.probe_video", _noprobe)
    session = MockSession()
    bot = Bot("42:TEST", session=session)
    dp = await build(cfg, bot, db)
    fake = FakeDownloader()
    fake.probe_result = youtube_probe()
    dp["deps"].downloader = fake

    async def public(url):
        return True
    monkeypatch.setattr("savebot.services.is_public_url", public)
    await dp.feed_update(bot, message("https://youtu.be/abc"))
    picker = session.of(EditMessageText)[-1]
    labels = [b.text for row in picker.reply_markup.inline_keyboard for b in row]
    assert "📹 2K · 210 MB" in labels and "📹 1080p · 98 MB" in labels
    assert "katta" not in picker.text


async def test_quality_cache_separate_and_picker_cached(env):
    dp, bot, session, fake = env
    fake.probe_result = youtube_probe()
    url = "https://youtu.be/dQw4w9WgXcQ"
    await dp.feed_update(bot, message(url, mid=1))
    data360 = session.of(EditMessageText)[-1].reply_markup.inline_keyboard[0][0].callback_data
    await dp.feed_update(bot, callback(data360))
    await dp.feed_update(bot, message(url, mid=2))  # sifatlar ro'yxati xotiradan
    assert fake.probe_calls == 1
    picker2 = session.of(SendMessage)[-1]
    data720 = picker2.reply_markup.inline_keyboard[1][0].callback_data
    await dp.feed_update(bot, callback(data720))
    assert len(fake.calls) == 2  # 720p alohida yuklanadi (360p keshi unga berilmaydi)
    await dp.feed_update(bot, callback(data360))
    assert len(fake.calls) == 2  # 360p esa keshdan


async def test_single_quality_downloads_immediately_with_probe_info(env):
    dp, bot, session, fake = env
    await dp.feed_update(bot, message("https://www.tiktok.com/@u/video/1"))
    assert fake.calls == [("https://www.tiktok.com/@u/video/1", "video")]
    assert fake.kwargs[0]["info"] == {"id": "x"}  # sayt qayta so'ralmaydi
    assert session.of(SendVideo)


async def test_probe_failure_falls_back_to_gallery(env):
    dp, bot, session, fake = env
    fake.probe_error = "unsupported"
    await dp.feed_update(bot, message("https://x.com/u/status/1"))
    assert fake.kwargs[0]["ytdlp_error"].code == "unsupported"


async def test_probe_live_error(env):
    dp, bot, session, fake = env
    fake.probe_error = "live"
    await dp.feed_update(bot, message("https://youtu.be/live1"))
    assert not fake.calls
    assert any("Jonli efir" in c.text for c in session.of(EditMessageText))


async def test_music_site_goes_straight_to_mp3(env):
    dp, bot, session, fake = env
    await dp.feed_update(bot, message("https://music.youtube.com/watch?v=abc"))
    assert fake.calls == [("https://music.youtube.com/watch?v=abc", "audio")] and not fake.probe_calls


async def test_album_for_carousel(env):
    dp, bot, session, fake = env
    fake.kinds = ("photo", "video", "photo")
    await dp.feed_update(bot, message("https://www.instagram.com/p/XYZ/"))
    group = session.of(SendMediaGroup)[0]
    assert [m.type for m in group.media] == ["photo", "video", "photo"]
    assert group.media[0].caption and not group.media[1].caption


async def test_error_message(env):
    dp, bot, session, fake = env
    fake.error = "private"
    await dp.feed_update(bot, message("https://www.instagram.com/stories/u/1/"))
    assert any("yopiq" in (c.text or "") for c in session.of(EditMessageText))


async def test_plain_text_hint(env):
    dp, bot, session, _ = env
    await dp.feed_update(bot, message("salom"))
    assert "havola" in session.of(SendMessage)[0].text


async def test_group_ignores_unknown_sites(env):
    dp, bot, session, fake = env
    await dp.feed_update(bot, message("https://news.example.com/article", chat_type="group", chat_id=-100))
    await dp.feed_update(bot, message("oddiy gap", chat_type="group", chat_id=-100, mid=2))
    assert not fake.calls and not session.of(SendMessage)
    await dp.feed_update(bot, message("https://vm.tiktok.com/abc/", chat_type="group", chat_id=-100, mid=3))
    assert fake.calls


async def test_required_subscription(cfg, db, monkeypatch):
    from dataclasses import replace
    cfg = replace(cfg, required_channels=("@mychannel",))
    os.makedirs(cfg.tmp_dir, exist_ok=True)
    session = MockSession()
    session.member_status = ChatMemberStatus.LEFT
    bot = Bot("42:TEST", session=session)
    dp = await build(cfg, bot, db)
    fake = FakeDownloader()
    dp["deps"].downloader = fake
    await dp.feed_update(bot, message("https://www.instagram.com/reel/ABC/"))
    assert not fake.calls
    prompt = session.of(SendMessage)[-1]
    assert prompt.reply_markup.inline_keyboard[0][0].url == "https://t.me/mychannel"
    session.member_status = ChatMemberStatus.MEMBER
    await dp.feed_update(bot, callback("check_sub"))
    assert any("Rahmat" in c.text for c in session.of(EditMessageText))


async def test_per_user_limit(env):
    dp, bot, session, fake = env
    queue = dp["queue"]
    assert queue.try_reserve(USER.id)  # limit = 1, allaqachon band
    await dp.feed_update(bot, message("https://www.instagram.com/reel/NEW/"))
    assert not fake.calls
    assert any("kuting" in c.text for c in session.of(SendMessage) + session.of(EditMessageText))
    queue.release(USER.id)


async def test_admin_stats_and_ban(env, db):
    dp, bot, session, fake = env
    await dp.feed_update(bot, message("/stats", user=USER))  # oddiy foydalanuvchi — ruxsat yo'q
    assert not any("Statistika" in (c.text or "") for c in session.of(SendMessage))
    await dp.feed_update(bot, message("/stats", user=ADMIN, mid=2))
    assert "Statistika" in session.of(SendMessage)[-1].text
    await dp.feed_update(bot, message(f"/ban {USER.id}", user=ADMIN, mid=3))
    assert await db.is_banned(USER.id)
    n = len(session.calls)
    await dp.feed_update(bot, message("https://www.instagram.com/reel/ABC/", mid=4))
    assert len(session.calls) == n and not fake.calls  # ban qilingan — javob yo'q


async def test_broadcast(env, db):
    import asyncio
    dp, bot, session, _ = env
    for uid in (500, 501, 502):
        await db.touch_user(uid, "u", None)
    src = Message(message_id=5, date=NOW, text="Yangilik!", chat=Chat(id=1, type="private"), from_user=ADMIN)
    upd = Update(update_id=3, message=Message(message_id=6, date=NOW, text="/broadcast", from_user=ADMIN,
                                              chat=Chat(id=1, type="private"), reply_to_message=src))
    await dp.feed_update(bot, upd)
    data = session.of(SendMessage)[-1].reply_markup.inline_keyboard[0][0].callback_data
    assert data == "bc:yes:5"
    await dp.feed_update(bot, callback(data, user=ADMIN))
    for _ in range(50):
        if not dp["app_state"].broadcasting:
            break
        await asyncio.sleep(0.05)
    assert sorted(c.chat_id for c in session.of(CopyMessage)) == [1, 500, 501, 502]  # admin ham bazada
