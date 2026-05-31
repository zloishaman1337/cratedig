from cratedig.sources.youtube import YouTubeDownloader


def test_youtube_opts_use_ffmpeg_postprocessor_when_available(monkeypatch, tmp_path):
    monkeypatch.setattr("cratedig.sources.youtube.shutil.which", lambda name: "ffmpeg.exe")
    opts = YouTubeDownloader({"audio_format": "wav"})._opts(tmp_path)
    assert opts["postprocessors"] == [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}]


def test_youtube_opts_fall_back_to_native_without_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr("cratedig.sources.youtube.shutil.which", lambda name: None)
    opts = YouTubeDownloader({"audio_format": "wav"})._opts(tmp_path)
    assert "postprocessors" not in opts


def test_youtube_native_format_skips_postprocessor(monkeypatch, tmp_path):
    monkeypatch.setattr("cratedig.sources.youtube.shutil.which", lambda name: "ffmpeg.exe")
    opts = YouTubeDownloader({"audio_format": "native"})._opts(tmp_path)
    assert "postprocessors" not in opts
