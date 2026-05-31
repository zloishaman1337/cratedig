import numpy as np

from cratedig.audio.playback import AudioPlayer, WaveformData, render_waveform, render_waveform_panel


def test_render_waveform_scales_peaks_to_width():
    samples = np.array([0.0, 0.25, -0.5, 1.0], dtype=np.float32)
    out = render_waveform(samples, width=4)
    assert len(out) == 4
    assert out[-1] == "█"


def test_render_waveform_handles_silence():
    out = render_waveform(np.zeros(8, dtype=np.float32), width=4)
    assert out == "▁" * 4


def test_render_waveform_empty_or_bad_width():
    samples = np.array([0.0, 1.0], dtype=np.float32)
    assert render_waveform(samples, width=0) == ""
    assert render_waveform(np.array([], dtype=np.float32), width=8) == ""


def test_render_waveform_panel_draws_stereo_playhead_and_selection():
    peaks = np.array(
        [
            [[-0.2, 0.5], [-1.0, 0.8], [-0.3, 0.3], [-0.1, 0.1]],
            [[-0.1, 0.1], [-0.4, 0.4], [-0.8, 1.0], [-0.2, 0.2]],
        ],
        dtype=np.float32,
    )
    rms = np.array([[0.1, 0.4, 0.2, 0.05], [0.05, 0.2, 0.5, 0.1]], dtype=np.float32)
    data = WaveformData(peaks=peaks, rms=rms, duration_sec=4.0, sample_rate=4, channels=2)

    out = render_waveform_panel(
        data,
        width=4,
        lane_height=5,
        playhead_sec=2.0,
        selection=(1.0, 3.0),
    )

    assert "L " in out
    assert "R " in out
    assert "│" in out
    assert "▒" in out
    assert "0:00.0-0:04.0 / 0:04.0" in out


def test_audio_player_play_builds_seek_loop_command(monkeypatch):
    calls = []

    class Proc:
        def poll(self):
            return 0

    def fake_popen(cmd, **kwargs):
        calls.append(cmd)
        return Proc()

    monkeypatch.setattr("shutil.which", lambda name: "ffplay.exe" if name == "ffplay" else None)
    monkeypatch.setattr("subprocess.Popen", fake_popen)

    AudioPlayer().play("kick.wav", start_sec=1.25, duration_sec=0.5, loop=True)

    assert calls == [
        [
            "ffplay.exe",
            "-nodisp",
            "-autoexit",
            "-loglevel",
            "error",
            "-ss",
            "1.250",
            "-t",
            "0.500",
            "-loop",
            "0",
            "kick.wav",
        ]
    ]
