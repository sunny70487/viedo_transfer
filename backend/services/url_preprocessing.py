def prepare_url_input(*, task, request, output_directory, download):
    task.message = f"正在從 URL 下載: {request.url}"
    task.progress = 10.0

    downloaded_file, _folder_path = download(
        url=request.url,
        output_dir=output_directory,
        download_format=request.download_format,
        verbose=True,
        video_quality=request.video_quality,
    )

    if not downloaded_file:
        raise RuntimeError("下載失敗")

    task.message = f"下載完成，開始轉錄: {downloaded_file}"
    task.progress = 30.0
    return downloaded_file
