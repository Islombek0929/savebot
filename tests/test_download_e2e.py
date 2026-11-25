"""Haqiqiy yt-dlp / gallery-dl / ffmpeg bilan yuklash — lokal HTTP server orqali (internet shart emas)."""
import functools
import hashlib
import http.server
import shutil
import subprocess
import threading

import pytest
import yt_dlp

from savebot.downloader import Downloader, DownloadError, prepare_files

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg kerak")


def _make_video(path, color, size="320x568"):
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c={color}:s={size}:d=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path,
    ], check=True)


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp("www")
    _make_video(str(root / "clean.mp4"), "green")
    _make_video(str(root / "watermarked.mp4"), "red")
    _make_video(str(root / "v360.mp4"), "yellow", "640x360")
    _make_video(str(root / "v720.mp4"), "white", "1280x720")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64",
                    "-frames:v", "1", str(root / "photo.jpg")], check=True)
    (root / "page.html").write_text("<html><body>video yo'q</body></html>")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", root
    httpd.shutdown()


def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


async def test_direct_video(server, cfg, tmp_path):
    base, _ = server
    result = await Downloader(cfg).download(f"{base}/clean.mp4", "video", str(tmp_path))
    files = await prepare_files(result, cfg.max_bytes)
    assert len(files) == 1
    f = files[0]
    assert f.kind == "video" and f.path.endswith(".mp4")
    assert (f.width, f.height, f.duration) == (320, 568, 2)


async def test_mp3(server, cfg, tmp_path):
    base, _ = server
    result = await Downloader(cfg).download(f"{base}/clean.mp4", "audio", str(tmp_path))
    assert [f.kind for f in result.files] == ["audio"]
    assert result.files[0].path.endswith(".mp3")


async def test_photo_falls_back_to_gallery_dl(server, cfg, tmp_path):
    base, _ = server
    result = await Downloader(cfg).download(f"{base}/photo.jpg", "video", str(tmp_path))
    assert [f.kind for f in result.files] == ["photo"]


async def test_page_without_media_gives_error(server, cfg, tmp_path):
    base, _ = server
    with pytest.raises(DownloadError) as e:
        await Downloader(cfg).download(f"{base}/page.html", "video", str(tmp_path))
    assert e.value.code in ("unsupported", "failed", "not_found")


async def test_tiktok_like_downloads_clean_file(server, cfg, tmp_path, monkeypatch):
    """TikTok'ga o'xshash: ikkala format bor, suv belgili kichikroq va 720p — baribir toza fayl tushadi."""
    base, root = server

    def fake_extract(self, url, download=True, **kw):
        info = {
            "id": "7300000000000000000", "title": "Video by someone", "description": "Zo'r video #fyp",
            "uploader": "someone", "extractor": "TikTok", "extractor_key": "TikTok",
            "webpage_url": url, "duration": 2,
            "formats": [
                {"format_id": "download_addr-0", "url": f"{base}/watermarked.mp4", "ext": "mp4",
                 "vcodec": "h264", "acodec": "aac", "width": 720, "height": 1280,
                 "format_note": "Download video, watermarked", "preference": -2},
                {"format_id": "play_addr-0", "url": f"{base}/clean.mp4", "ext": "mp4",
                 "vcodec": "h264", "acodec": "aac", "width": 1080, "height": 1920,
                 "format_note": "Direct video"},
            ],
        }
        return self.process_ie_result(info, download=download)

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", fake_extract)
    result = await Downloader(cfg).download("https://www.tiktok.com/@someone/video/7300000000000000000",
                                            "video", str(tmp_path))
    assert len(result.files) == 1
    assert md5(result.files[0].path) == md5(root / "clean.mp4")
    assert result.title == "Zo'r video #fyp"  # "Video by someone" — akkaunt nomi olib tashlandi


async def test_live_rejected(cfg, tmp_path, monkeypatch):
    def fake_extract(self, url, download=True, **kw):
        return {"id": "l", "title": "live", "is_live": True, "extractor": "x", "extractor_key": "X",
                "webpage_url": url, "formats": []}

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", fake_extract)
    with pytest.raises(DownloadError) as e:
        await Downloader(cfg).download("https://youtube.com/watch?v=live", "video", str(tmp_path))
    assert e.value.code == "live"


async def test_too_long_rejected(cfg, tmp_path, monkeypatch):
    def fake_extract(self, url, download=True, **kw):
        return {"id": "l", "title": "long", "duration": 10 * 3600, "extractor": "x",
                "extractor_key": "X", "webpage_url": url, "formats": []}

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", fake_extract)
    with pytest.raises(DownloadError) as e:
        await Downloader(cfg).download("https://youtube.com/watch?v=long", "video", str(tmp_path))
    assert e.value.code == "too_long"


async def test_mp3_has_cover_and_tags(server, cfg, tmp_path, monkeypatch):
    base, _ = server

    def fake_extract(self, url, download=True, **kw):
        info = {
            "id": "song1", "title": "Qo'shiq nomi", "artist": "Ijrochi", "duration": 2,
            "extractor": "Test", "extractor_key": "Test", "webpage_url": url,
            "thumbnails": [{"url": f"{base}/photo.jpg", "id": "0"}],
            "formats": [{"format_id": "a", "url": f"{base}/clean.mp4", "ext": "mp4",
                         "vcodec": "h264", "acodec": "aac"}],
        }
        return self.process_ie_result(info, download=download)

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", fake_extract)
    result = await Downloader(cfg).download("https://music.youtube.com/watch?v=song1", "audio", str(tmp_path))
    assert [f.kind for f in result.files] == ["audio"]  # muqova rasmi alohida fayl bo'lib kelmaydi
    assert result.title == "Qo'shiq nomi" and result.performer == "Ijrochi"
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name",
                            "-of", "csv=p=0", result.files[0].path], capture_output=True, text=True).stdout
    assert "mp3,audio" in probe and "mjpeg,video" in probe  # muqova ichiga joylangan


async def test_youtube_playlist_rejected(cfg, tmp_path, monkeypatch):
    def fake_extract(self, url, download=True, **kw):
        return {"_type": "playlist", "id": "PL1", "title": "pl", "extractor": "youtube:tab",
                "extractor_key": "YoutubeTab", "webpage_url": url,
                "entries": [{"id": "a", "title": "a"}, {"id": "b", "title": "b"}]}

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", fake_extract)
    with pytest.raises(DownloadError) as e:
        await Downloader(cfg).download("https://www.youtube.com/playlist?list=PL1", "video", str(tmp_path))
    assert e.value.code == "unsupported"


def _multi_quality(base):
    def fake_extract(self, url, download=True, **kw):
        info = {
            "id": "yt1", "title": "Kino", "duration": 2, "extractor": "youtube",
            "extractor_key": "Youtube", "webpage_url": url,
            "formats": [
                {"format_id": "18", "url": f"{base}/v360.mp4", "ext": "mp4", "vcodec": "avc1",
                 "acodec": "mp4a", "width": 640, "height": 360},
                {"format_id": "22", "url": f"{base}/v720.mp4", "ext": "mp4", "vcodec": "avc1",
                 "acodec": "mp4a", "width": 1280, "height": 720},
            ],
        }
        return self.process_ie_result(info, download=download)
    return fake_extract


async def test_probe_lists_qualities(server, cfg, monkeypatch):
    base, _ = server
    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", _multi_quality(base))
    probe = await Downloader(cfg).probe("https://youtu.be/yt1")
    assert [o.label for o in probe.options] == [360, 720]
    assert probe.title == "Kino" and probe.duration == 2


@pytest.mark.parametrize("quality,expected", [(360, "v360.mp4"), (720, "v720.mp4"), (1080, "v720.mp4")])
async def test_download_chosen_quality(server, cfg, tmp_path, monkeypatch, quality, expected):
    base, root = server
    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", _multi_quality(base))
    result = await Downloader(cfg).download("https://youtu.be/yt1", "video", str(tmp_path),
                                            quality=quality)
    assert md5(result.files[0].path) == md5(root / expected)


async def test_download_reuses_probe_info(server, cfg, tmp_path, monkeypatch):
    """probe() dan keyin yuklashda sayt qayta so'ralmaydi (Instagram/TikTok bloklamasligi uchun)."""
    base, root = server
    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", _multi_quality(base))
    dl = Downloader(cfg)
    probe = await dl.probe("https://youtu.be/yt1")

    def boom(*a, **k):
        raise AssertionError("qayta extract qilinmasligi kerak")

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", boom)
    result = await dl.download("https://youtu.be/yt1", "video", str(tmp_path), info=probe.info)
    assert md5(result.files[0].path) == md5(root / "v720.mp4")


async def test_private_error_skips_gallery(cfg, tmp_path, monkeypatch):
    dl = Downloader(cfg)

    async def boom(ctx):
        raise AssertionError("gallery-dl chaqirilmasligi kerak")

    monkeypatch.setattr(dl, "_gallery", boom)
    with pytest.raises(DownloadError) as e:
        await dl.download("https://www.instagram.com/reel/x/", "video", str(tmp_path),
                          ytdlp_error=DownloadError("private", "login required"))
    assert e.value.code == "private"


async def test_retry_with_fresh_info_after_403(cfg, tmp_path, monkeypatch):
    dl = Downloader(cfg)
    calls = []

    def fake_sync(ctx):
        calls.append(ctx.info)
        if ctx.info is not None:
            raise DownloadError("blocked", "HTTP Error 403: Forbidden")
        from savebot.downloader import MediaFile, Result
        path = tmp_path / "ok.mp4"
        path.write_bytes(b"x")
        return Result(files=[MediaFile(str(path), "video")])

    monkeypatch.setattr(dl, "_ytdlp_sync", fake_sync)
    result = await dl.download("https://www.instagram.com/reel/a/", "video", str(tmp_path),
                               info={"id": "old"})
    assert calls == [{"id": "old"}, None] and result.files


async def test_cookies_copy_used_and_removed(server, cfg, tmp_path, monkeypatch):
    import glob
    from dataclasses import replace
    base, _ = server
    src = tmp_path / "cookies.txt"
    original = ("# Netscape HTTP Cookie File\n"
                ".instagram.com\tTRUE\t/\tTRUE\t2000000000\tsessionid\tabc\n")
    src.write_text(original)
    cfg = replace(cfg, cookies_file=str(src))
    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", _multi_quality(base))
    dl = Downloader(cfg)
    seen = []
    real_base = dl._base_opts

    def spy(ctx):
        seen.append(ctx.cookies)
        return real_base(ctx)

    dl._base_opts = spy
    workdir = tmp_path / "w"
    workdir.mkdir()
    result = await dl.download("https://www.instagram.com/reel/abc/", "video", str(workdir))
    assert result.files
    assert seen and all(p and p != str(src) for p in seen)  # asl fayl emas, nusxa
    assert not glob.glob(f"{cfg.tmp_dir}/ck_*")  # nusxa o'chirildi
    assert src.read_text() == original  # asl fayl o'zgarmadi

    seen.clear()  # boshqa saytlarga Instagram cookies yuborilmaydi
    await dl.download(f"{base}/clean.mp4", "video", str(workdir))
    assert seen and all(p is None for p in seen)


async def test_audio_retries_via_video_after_403(cfg, tmp_path, monkeypatch):
    dl = Downloader(cfg)
    modes = []

    def fake_sync(ctx):
        modes.append(ctx.audio_via_video)
        if not ctx.audio_via_video:
            raise DownloadError("blocked", "unable to download video data: HTTP Error 403")
        from savebot.downloader import MediaFile, Result
        path = tmp_path / "a.mp3"
        path.write_bytes(b"x")
        return Result(files=[MediaFile(str(path), "audio")])

    monkeypatch.setattr(dl, "_ytdlp_sync", fake_sync)
    result = await dl.download("https://www.instagram.com/reel/a/", "audio", str(tmp_path))
    assert modes == [False, True] and result.files


def test_pot_provider_extractor_args(cfg):
    from dataclasses import replace
    from savebot.downloader import Progress, _Ctx
    ctx = _Ctx("https://youtu.be/x", "video", "", Progress(), 0)
    assert "extractor_args" not in Downloader(cfg)._base_opts(ctx)
    cfg2 = replace(cfg, pot_provider_url="http://pot-provider:4416")
    args = Downloader(cfg2)._base_opts(ctx)["extractor_args"]
    assert args == {"youtubepot-bgutilhttp": {"base_url": ["http://pot-provider:4416"]}}
