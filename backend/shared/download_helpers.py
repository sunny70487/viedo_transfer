import os
from pathlib import Path
import re
import time

import yt_dlp


def build_safe_title(title, fallback_name=None):
    if title:
        safe_title = "".join(
            [
                char if char.isalnum() or char in [" ", "-", "_"] else "_"
                for char in title
            ]
        )
        return safe_title[:50]

    if fallback_name is not None:
        return fallback_name

    return f"download_{int(time.time())}"


def build_yt_dlp_options(
    *,
    folder_path,
    download_format,
    verbose,
    cookies,
    video_quality,
):
    ydl_opts = {
        "quiet": not verbose,
        "no_warnings": not verbose,
        "paths": {"home": str(folder_path)},
        "outtmpl": {"default": "%(title)s.%(ext)s"},
        "windowsfilenames": True,
        "restrictfilenames": True,
        "keepvideo": True,
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 5,
        "retry_sleep_functions": {
            "http": lambda n: min(2 ** n, 30),
            "fragment": lambda n: min(2 ** n, 30),
        },
        "http_chunk_size": 10485760,
    }

    if download_format == "audio":
        ydl_opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "flac",
                        "preferredquality": "192",
                    }
                ],
                "keepfiles": True,
            }
        )
    else:
        if video_quality == "best":
            format_str = "bestvideo+bestaudio/best"
        elif video_quality == "1080p":
            format_str = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
        elif video_quality == "720p":
            format_str = "bestvideo[height<=720]+bestaudio/best[height<=720]"
        elif video_quality == "480p":
            format_str = "bestvideo[height<=480]+bestaudio/best[height<=480]"
        elif video_quality == "360p":
            format_str = "bestvideo[height<=360]+bestaudio/best[height<=360]"
        else:
            format_str = "best"

        ydl_opts.update(
            {
                "format": format_str,
                "merge_output_format": "mp4",
            }
        )

    if cookies:
        ydl_opts["cookiefile"] = cookies

    return ydl_opts


def download_from_url(
    url,
    output_dir=None,
    download_format="audio",
    verbose=True,
    cookies=None,
    video_quality="best",
):
    if verbose:
        print(f"正在從 URL 下載: {url}")
        print(f"設定的影片品質: {video_quality}")

    if output_dir:
        base_output_path = Path(output_dir)
        base_output_path.mkdir(parents=True, exist_ok=True)
    else:
        base_output_path = Path.cwd()

    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        safe_title = build_safe_title(info.get("title", None))

    folder_path = base_output_path / safe_title
    folder_path.mkdir(exist_ok=True)

    if verbose:
        print(f"為該下載項目創建資料夾: {folder_path}")

    ydl_opts = build_yt_dlp_options(
        folder_path=folder_path,
        download_format=download_format,
        verbose=verbose,
        cookies=cookies,
        video_quality=video_quality,
    )

    downloaded_file = None

    def get_filepath_hook(data):
        nonlocal downloaded_file
        if data["status"] == "finished":
            downloaded_file = data["filename"]
            if verbose:
                print(f"下載完成：{downloaded_file}")

    ydl_opts["progress_hooks"] = [get_filepath_hook]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            if "requested_downloads" in info_dict:
                for download in info_dict["requested_downloads"]:
                    filepath = download.get("filepath")
                    if filepath:
                        downloaded_file = filepath
                        if verbose:
                            print(f"使用最終輸出檔案：{downloaded_file}")
                        break

            if not downloaded_file and "title" in info_dict and "ext" in info_dict:
                safe_title = build_safe_title(info_dict["title"])
                possible_path = str(folder_path / f"{safe_title}.{info_dict['ext']}")
                if os.path.exists(possible_path):
                    downloaded_file = possible_path
                    if verbose:
                        print(f"檢測到已存在的檔案：{downloaded_file}")
    except Exception as exc:
        error_msg = str(exc).lower()
        if "has already been downloaded" in error_msg or "already exists" in error_msg:
            path_match = re.search(r"'(.*?)'", str(exc))
            if path_match:
                downloaded_file = path_match.group(1)
                if verbose:
                    print(f"使用已下載的檔案：{downloaded_file}")
            else:
                potential_files = list(folder_path.glob("*.*"))
                if potential_files:
                    downloaded_file = str(
                        sorted(potential_files, key=os.path.getmtime)[-1]
                    )
                    if verbose:
                        print(f"使用資料夾中最新的檔案：{downloaded_file}")
        else:
            print(f"下載時出錯: {exc}")
            raise

    if download_format == "audio" and downloaded_file:
        downloaded_file = re.sub(r"\.[^.]+$", ".flac", downloaded_file)

    if downloaded_file and verbose:
        print(f"文件已下載至: {downloaded_file}")

    return downloaded_file, folder_path
