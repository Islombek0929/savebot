"""Format tanlash: suv belgisiz va hajm chegarasiga mos sifat."""
import pytest

from savebot.downloader import DownloadError, audio_bitrate, choose_video_format

MB = 1024 * 1024


def _info(formats, duration=30):
    return {"id": "x", "title": "t", "extractor": "test", "extractor_key": "Test",
            "webpage_url": "https://example.com/x", "duration": duration, "formats": formats}


def tiktok_formats(clean_size=8 * MB):
    # yt-dlp TikTok extractori qaytaradigan formatlarga o'xshash
    return [
        {"format_id": "download_addr-0", "url": "https://t/wm", "ext": "mp4", "vcodec": "h264",
         "acodec": "aac", "width": 720, "height": 1280, "preference": -2,
         "format_note": "Download video, watermarked", "filesize": 3 * MB},
        {"format_id": "play_addr-0", "url": "https://t/clean", "ext": "mp4", "vcodec": "h264",
         "acodec": "aac", "width": 1080, "height": 1920, "format_note": "Direct video",
         "filesize": clean_size},
        {"format_id": "download", "url": "https://t/wm2", "ext": "mp4", "vcodec": "h264",
         "acodec": "aac", "width": 576, "height": 1024, "format_note": "watermarked",
         "preference": -2, "filesize": 2 * MB},
    ]


def test_tiktok_never_picks_watermarked():
    fmt, _ = choose_video_format(_info(tiktok_formats()), 50 * MB, 720)
    assert fmt == "play_addr-0"


def test_tiktok_watermarked_not_used_even_if_clean_is_big_ladder():
    # Toza video 1080p bo'lsa ham, 720p'li suv belgili variantga tushib ketmasligi kerak
    fmt, _ = choose_video_format(_info(tiktok_formats(clean_size=20 * MB)), 50 * MB, 480)
    assert fmt == "play_addr-0"


def youtube_formats():
    return [
        {"format_id": "137", "url": "https://y/1", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "width": 1920, "height": 1080, "filesize": 200 * MB},
        {"format_id": "136", "url": "https://y/2", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "width": 1280, "height": 720, "filesize": 90 * MB},
        {"format_id": "135", "url": "https://y/3", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "width": 854, "height": 480, "filesize": 40 * MB},
        {"format_id": "134", "url": "https://y/4", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "width": 640, "height": 360, "filesize": 20 * MB},
        {"format_id": "140", "url": "https://y/5", "ext": "m4a", "vcodec": "none", "acodec": "mp4a", "filesize": 6 * MB},
        {"format_id": "251", "url": "https://y/6", "ext": "webm", "vcodec": "none", "acodec": "opus", "filesize": 7 * MB},
    ]


def test_youtube_720_when_fits():
    fmt, size = choose_video_format(_info(youtube_formats()), 2000 * MB, 720)
    assert fmt == "136+140"
    assert size == 96 * MB


def test_youtube_drops_quality_to_fit_50mb():
    fmt, size = choose_video_format(_info(youtube_formats()), 50 * MB, 720)
    assert fmt == "135+140"
    assert size <= 50 * MB


def test_too_big_everywhere():
    with pytest.raises(DownloadError) as e:
        choose_video_format(_info(youtube_formats()), 5 * MB, 720)
    assert e.value.code == "too_big"


def test_vertical_video_uses_smallest_side():
    formats = [
        {"format_id": "v1080", "url": "https://v/1", "ext": "mp4", "vcodec": "h264", "acodec": "aac", "width": 1080, "height": 1920, "filesize": 30 * MB},
        {"format_id": "v720", "url": "https://v/2", "ext": "mp4", "vcodec": "h264", "acodec": "aac", "width": 720, "height": 1280, "filesize": 15 * MB},
    ]
    fmt, _ = choose_video_format(_info(formats), 50 * MB, 720)
    assert fmt == "v720"


def test_unknown_size_is_accepted():
    formats = [{"format_id": "only", "url": "https://v/1", "ext": "mp4", "vcodec": "h264", "acodec": "aac", "width": 640, "height": 360}]
    assert choose_video_format(_info(formats, duration=None), 50 * MB, 720)[0] == "only"


@pytest.mark.parametrize("duration,expected", [(None, 192), (180, 192), (60 * 60, 96), (2 * 3600, 48)])
def test_audio_bitrate(duration, expected):
    assert audio_bitrate(duration, 50 * MB) == expected


def test_audio_too_long():
    with pytest.raises(DownloadError):
        audio_bitrate(5 * 3600, 50 * MB)


# ---------------- sifat tanlash (360p ... 2K) ----------------
from savebot.downloader import pick_quality, quality_label, quality_options  # noqa: E402


@pytest.mark.parametrize("w,h,label", [
    (1920, 1080, 1080), (1080, 1920, 1080), (1920, 800, 1080), (2560, 1440, 1440),
    (1280, 720, 720), (720, 1280, 720), (854, 480, 480), (640, 360, 360), (576, 1024, 480),
    (3840, 2160, 2160), (None, 720, 720),
])
def test_quality_label(w, h, label):
    assert quality_label({"width": w, "height": h, "vcodec": "avc1"}) == label


def youtube_full():
    return youtube_formats() + [
        {"format_id": "271", "url": "https://y/7", "ext": "webm", "vcodec": "vp9", "acodec": "none", "width": 2560, "height": 1440, "filesize": 300 * MB},
        {"format_id": "400", "url": "https://y/8", "ext": "mp4", "vcodec": "av01.0.12M.08", "acodec": "none", "width": 2560, "height": 1440, "filesize": 250 * MB},
        {"format_id": "313", "url": "https://y/9", "ext": "webm", "vcodec": "vp9", "acodec": "none", "width": 3840, "height": 2160, "filesize": 900 * MB},
        {"format_id": "248", "url": "https://y/10", "ext": "webm", "vcodec": "vp9", "acodec": "none", "width": 1920, "height": 1080, "filesize": 150 * MB},
    ]


def test_quality_options_up_to_2k():
    opts = quality_options(_info(youtube_full()), max_quality=1440)
    assert [o.label for o in opts] == [360, 480, 720, 1080, 1440]  # 4K ko'rsatilmaydi
    by = {o.label: o for o in opts}
    assert by[720].format_id == "136+140" and by[720].size == 96 * MB
    assert by[1080].format_id == "137+140"  # h264 vp9'dan afzal
    assert by[1440].format_id == "271+140"  # vp9 av1'dan afzal (ko'proq qurilmada o'ynaydi)


def test_quality_options_4k_when_allowed():
    assert quality_options(_info(youtube_full()), max_quality=2160)[-1].label == 2160


def test_quality_options_skip_watermarked():
    opts = quality_options(_info(tiktok_formats()))
    assert [(o.label, o.format_id) for o in opts] == [(1080, "play_addr-0")]


def test_pick_quality():
    info = _info(youtube_full())
    assert pick_quality(info, 720, 2000 * MB, 1440) == "136+140"
    assert pick_quality(info, 1440, 2000 * MB, 1440) == "271+140"
    assert pick_quality(info, 600, 2000 * MB, 1440) == "135+140"  # yo'q bo'lsa — pastrog'i
    with pytest.raises(DownloadError) as e:
        pick_quality(info, 1080, 50 * MB, 1440)
    assert e.value.code == "too_big"
