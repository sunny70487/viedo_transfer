from backend.shared.download_helpers import build_safe_title, build_yt_dlp_options


def test_build_safe_title_preserves_letters_spaces_and_underscores():
    assert build_safe_title("Hello/World: 測試_影片") == "Hello_World_ 測試_影片"


def test_build_safe_title_falls_back_when_title_missing():
    assert build_safe_title(None, fallback_name="download_123") == "download_123"


def test_build_yt_dlp_options_for_audio_keeps_flac_postprocessor(tmp_path):
    options = build_yt_dlp_options(
        folder_path=tmp_path,
        download_format="audio",
        verbose=False,
        cookies=None,
        video_quality="best",
    )

    assert options["paths"]["home"] == str(tmp_path)
    assert options["format"] == "bestaudio/best"
    assert options["postprocessors"][0]["preferredcodec"] == "flac"


def test_build_yt_dlp_options_for_video_sets_merge_output_format(tmp_path):
    options = build_yt_dlp_options(
        folder_path=tmp_path,
        download_format="video",
        verbose=True,
        cookies="cookies.txt",
        video_quality="720p",
    )

    assert options["format"] == "bestvideo[height<=720]+bestaudio/best[height<=720]"
    assert options["merge_output_format"] == "mp4"
    assert options["cookiefile"] == "cookies.txt"
