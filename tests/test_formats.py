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
