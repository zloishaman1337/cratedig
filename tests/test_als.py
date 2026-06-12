"""Tests for cratedig.als.parser module - ALS project file parsing."""

import gzip
import math
from pathlib import Path

import pytest

from cratedig.als.parser import parse_als, _linear_to_db, _match_plugin


# ── ALS fixture ────────────────────────────────────────────────────────────────

def _als_xml() -> str:
    """Return a minimal but representative ALS project XML."""
    return """<?xml version="1.0"?>
<Ableton Creator="Ableton Live 12.0" MajorVersion="5">
<LiveSet>
 <Tracks>
  <MidiTrack>
   <Name><EffectiveName Value="Lead"/></Name>
   <DeviceChain><DeviceChain><Devices><Operator/><Eq8/></Devices></DeviceChain></DeviceChain>
   <DeviceChain><MainSequencer><ClipTimeable><ArrangerAutomation><Events>
     <MidiClip Time="0"><CurrentStart Value="0"/><CurrentEnd Value="16"/>
       <Notes><KeyTracks><KeyTrack><Notes><MidiNoteEvent/></Notes></KeyTrack></KeyTracks></Notes>
     </MidiClip>
   </Events></ArrangerAutomation></ClipTimeable></MainSequencer></DeviceChain>
  </MidiTrack>
 </Tracks>
 <MasterTrack>
  <DeviceChain><Mixer><Volume><Manual Value="1.0"/></Volume>
    <Tempo><Manual Value="140"/></Tempo></Mixer>
    <Devices><Reverb/></Devices>
  </DeviceChain>
 </MasterTrack>
 <SampleRef><FileRef><Name Value="kick.wav"/></FileRef></SampleRef>
</LiveSet>
</Ableton>"""


def _als_xml_with_au() -> str:
    """Return ALS XML with Audio Unit (AU) devices for instrument and effect classification."""
    return """<?xml version="1.0"?>
<Ableton Creator="Ableton Live 12.0" MajorVersion="5">
<LiveSet>
 <Tracks>
  <MidiTrack>
   <Name><EffectiveName Value="Track with AU"/></Name>
   <DeviceChain><DeviceChain><Devices>
     <AuPluginDevice>
       <PluginDesc>
         <AuPluginInfo>
           <Name Value="Kontakt 7"/>
           <ComponentType Value="1635085685"/>
           <NumAudioInputs Value="0"/>
         </AuPluginInfo>
       </PluginDesc>
     </AuPluginDevice>
     <AuPluginDevice>
       <PluginDesc>
         <AuPluginInfo>
           <Name Value="RC-20"/>
           <ComponentType Value="1635083896"/>
           <NumAudioInputs Value="1"/>
         </AuPluginInfo>
       </PluginDesc>
     </AuPluginDevice>
     <Operator/>
     <Eq8/>
   </Devices></DeviceChain></DeviceChain>
   <DeviceChain><MainSequencer><ClipTimeable><ArrangerAutomation><Events>
     <MidiClip Time="0"><CurrentStart Value="0"/><CurrentEnd Value="16"/>
       <Notes><KeyTracks><KeyTrack><Notes><MidiNoteEvent/></Notes></KeyTrack></KeyTracks></Notes>
     </MidiClip>
   </Events></ArrangerAutomation></ClipTimeable></MainSequencer></DeviceChain>
  </MidiTrack>
 </Tracks>
 <MasterTrack>
  <DeviceChain><Mixer><Volume><Manual Value="1.0"/></Volume>
    <Tempo><Manual Value="140"/></Tempo></Mixer>
    <Devices><Reverb/></Devices>
  </DeviceChain>
 </MasterTrack>
</LiveSet>
</Ableton>"""


@pytest.fixture
def als_file(tmp_path):
    """Create a minimal ALS fixture with gzip compression."""
    xml_bytes = _als_xml().encode("utf-8")
    als_path = tmp_path / "test.als"
    als_path.write_bytes(gzip.compress(xml_bytes))
    return str(als_path)


@pytest.fixture
def als_file_with_au(tmp_path):
    """Create an ALS fixture with AU devices (instrument and effect)."""
    xml_bytes = _als_xml_with_au().encode("utf-8")
    als_path = tmp_path / "test_au.als"
    als_path.write_bytes(gzip.compress(xml_bytes))
    return str(als_path)


@pytest.fixture
def invalid_als_file(tmp_path):
    """Create an invalid (non-gzip) file."""
    bad_path = tmp_path / "bad.als"
    bad_path.write_bytes(b"This is not a gzip file")
    return str(bad_path)


# ── Test parse_als ────────────────────────────────────────────────────────

class TestParseAls:
    """Test parse_als(path: str) -> dict."""

    def test_parse_als_returns_dict_with_expected_keys(self, als_file):
        """Verify parse_als returns dict with all expected top-level keys."""
        result = parse_als(als_file)
        assert isinstance(result, dict)
        assert "ableton_version" in result
        assert "tracks" in result
        assert "main" in result
        assert "arrangement" in result
        assert "samples" in result

    def test_parse_als_version_extracted(self, als_file):
        """Version should be extracted from Creator attribute."""
        result = parse_als(als_file)
        assert result["ableton_version"] == "Ableton Live 12.0"

    def test_parse_als_single_track_parsed(self, als_file):
        """One MIDI track should be parsed."""
        result = parse_als(als_file)
        assert len(result["tracks"]) == 1
        track = result["tracks"][0]
        assert track["name"] == "Lead"
        assert track["type"] == "midi"

    def test_parse_als_track_has_content(self, als_file):
        """Track with MIDI notes should have has_content = True."""
        result = parse_als(als_file)
        track = result["tracks"][0]
        assert track["has_content"] is True

    def test_parse_als_track_instruments(self, als_file):
        """Track should contain 'Operator' instrument."""
        result = parse_als(als_file)
        track = result["tracks"][0]
        assert "Operator" in track["live_instruments"]

    def test_parse_als_track_effects(self, als_file):
        """Track should contain 'EQ Eight' effect."""
        result = parse_als(als_file)
        track = result["tracks"][0]
        assert "EQ Eight" in track["live_effects"]

    def test_parse_als_main_effects(self, als_file):
        """Main channel should contain 'Reverb' effect."""
        result = parse_als(als_file)
        main = result["main"]
        assert "Reverb" in main["live_effects"]

    def test_parse_als_main_fader_db(self, als_file):
        """Main fader at 1.0 linear should be 0.0 dB."""
        result = parse_als(als_file)
        main = result["main"]
        assert main["fader_db"] == 0.0

    def test_parse_als_main_fader_not_above_0db(self, als_file):
        """With fader_db == 0.0, fader_above_0db should be False."""
        result = parse_als(als_file)
        main = result["main"]
        assert main["fader_above_0db"] is False

    def test_parse_als_arrangement_bars(self, als_file):
        """Arrangement should show 4 bars (16 beats / 4 = 4 bars)."""
        result = parse_als(als_file)
        arr = result["arrangement"]
        assert arr is not None
        assert arr["bars"] == 4.0

    def test_parse_als_arrangement_bpm(self, als_file):
        """Arrangement should show 140 BPM from master tempo."""
        result = parse_als(als_file)
        arr = result["arrangement"]
        assert arr is not None
        assert arr["bpm"] == 140.0

    def test_parse_als_arrangement_beats(self, als_file):
        """Arrangement should show 16 beats (from clip end position)."""
        result = parse_als(als_file)
        arr = result["arrangement"]
        assert arr is not None
        assert arr["beats"] == 16.0

    def test_parse_als_samples_missing(self, als_file):
        """Sample 'kick.wav' not on disk should be in missing list."""
        result = parse_als(als_file)
        samples = result["samples"]
        assert "kick.wav" in samples["missing"]

    def test_parse_als_samples_found_is_empty(self, als_file):
        """No samples on disk, so found list should be empty."""
        result = parse_als(als_file)
        samples = result["samples"]
        assert samples["found"] == []

    def test_parse_als_track_vst2_empty(self, als_file):
        """No VST2 plugins in fixture, so list should be empty."""
        result = parse_als(als_file)
        track = result["tracks"][0]
        assert track["vst2_plugins"] == []

    def test_parse_als_track_vst3_empty(self, als_file):
        """No VST3 plugins in fixture, so list should be empty."""
        result = parse_als(als_file)
        track = result["tracks"][0]
        assert track["vst3_plugins"] == []

    def test_parse_als_main_vst2_empty(self, als_file):
        """No VST2 plugins on main, so list should be empty."""
        result = parse_als(als_file)
        main = result["main"]
        assert main["vst2_plugins"] == []

    def test_parse_als_main_vst3_empty(self, als_file):
        """No VST3 plugins on main, so list should be empty."""
        result = parse_als(als_file)
        main = result["main"]
        assert main["vst3_plugins"] == []

    def test_parse_als_raises_on_invalid_file(self, invalid_als_file):
        """Non-gzip file should raise ValueError."""
        with pytest.raises(ValueError):
            parse_als(invalid_als_file)

    def test_parse_als_raises_on_missing_file(self):
        """Non-existent file should raise ValueError."""
        with pytest.raises(ValueError):
            parse_als("/nonexistent/path/file.als")

    def test_parse_als_track_has_aggregated_instruments_key(self, als_file):
        """Track dict should contain 'instruments' aggregated list key."""
        result = parse_als(als_file)
        track = result["tracks"][0]
        assert "instruments" in track
        assert isinstance(track["instruments"], list)

    def test_parse_als_track_has_aggregated_plugins_key(self, als_file):
        """Track dict should contain 'plugins' aggregated list key."""
        result = parse_als(als_file)
        track = result["tracks"][0]
        assert "plugins" in track
        assert isinstance(track["plugins"], list)

    def test_parse_als_main_has_aggregated_instruments_key(self, als_file):
        """Main dict should contain 'instruments' aggregated list key."""
        result = parse_als(als_file)
        main = result["main"]
        assert "instruments" in main
        assert isinstance(main["instruments"], list)

    def test_parse_als_main_has_aggregated_plugins_key(self, als_file):
        """Main dict should contain 'plugins' aggregated list key."""
        result = parse_als(als_file)
        main = result["main"]
        assert "plugins" in main
        assert isinstance(main["plugins"], list)

    def test_parse_als_track_native_devices_in_aggregated_lists(self, als_file):
        """Native Operator should appear in instruments, native Eq8 in plugins."""
        result = parse_als(als_file)
        track = result["tracks"][0]
        assert "Operator" in track["instruments"]
        assert "EQ Eight" in track["plugins"]

    def test_parse_als_main_native_device_in_aggregated_plugins(self, als_file):
        """Native Reverb on main should appear in plugins aggregated list."""
        result = parse_als(als_file)
        main = result["main"]
        assert "Reverb" in main["plugins"]

    def test_parse_als_au_instrument_classified_correctly(self, als_file_with_au):
        """AU device with ComponentType aumu (1635085685) should be instrument."""
        result = parse_als(als_file_with_au)
        track = result["tracks"][0]
        # Kontakt 7 is AU instrument; should appear in instruments list with [AU] suffix
        assert any("Kontakt 7" in name and "[AU]" in name for name in track["instruments"])

    def test_parse_als_au_effect_classified_correctly(self, als_file_with_au):
        """AU device with ComponentType aufx (1635083896) should be effect."""
        result = parse_als(als_file_with_au)
        track = result["tracks"][0]
        # RC-20 is AU effect; should appear in plugins list with [AU] suffix
        assert any("RC-20" in name and "[AU]" in name for name in track["plugins"])

    def test_parse_als_au_devices_in_track_live_instruments_and_effects(self, als_file_with_au):
        """AU devices should roll into the aggregated instruments/plugins lists."""
        result = parse_als(als_file_with_au)
        track = result["tracks"][0]
        # au_* are internal collector keys; parse_als exposes them only via the
        # aggregated instruments/plugins lists on each track dict.
        instruments = track.get("instruments", [])
        plugins = track.get("plugins", [])
        assert any("Kontakt 7" in name for name in instruments)
        assert any("RC-20" in name for name in plugins)

    def test_parse_als_native_and_au_devices_coexist(self, als_file_with_au):
        """Native devices (Operator, Eq8) and AU devices should both appear in aggregated lists."""
        result = parse_als(als_file_with_au)
        track = result["tracks"][0]
        # Native
        assert "Operator" in track["instruments"]
        assert "EQ Eight" in track["plugins"]
        # AU
        assert any("Kontakt 7" in name and "[AU]" in name for name in track["instruments"])
        assert any("RC-20" in name and "[AU]" in name for name in track["plugins"])


# ── Test _linear_to_db ────────────────────────────────────────────────────

class TestLinearToDb:
    """Test _linear_to_db(value: float) -> float."""

    def test_linear_to_db_unity_is_zero(self):
        """1.0 linear should convert to 0.0 dB."""
        assert _linear_to_db(1.0) == 0.0

    def test_linear_to_db_zero_is_negative_infinity(self):
        """0.0 linear should convert to -inf."""
        assert _linear_to_db(0.0) == float("-inf")

    def test_linear_to_db_negative_is_negative_infinity(self):
        """Negative values should convert to -inf."""
        assert _linear_to_db(-0.5) == float("-inf")

    def test_linear_to_db_half_is_minus_six(self):
        """0.5 linear should convert to approximately -6.0 dB."""
        result = _linear_to_db(0.5)
        assert abs(result - (-6.0)) < 0.1

    def test_linear_to_db_two_is_plus_six(self):
        """2.0 linear should convert to approximately +6.0 dB."""
        result = _linear_to_db(2.0)
        assert abs(result - 6.0) < 0.1

    def test_linear_to_db_ten_is_twenty(self):
        """10.0 linear should convert to 20.0 dB."""
        result = _linear_to_db(10.0)
        assert abs(result - 20.0) < 0.1

    def test_linear_to_db_small_positive(self):
        """Small positive value (0.1) should produce negative dB."""
        result = _linear_to_db(0.1)
        assert result < 0


# ── Test _match_plugin ────────────────────────────────────────────────────

class TestMatchPlugin:
    """Test _match_plugin(name: str, stems: set) -> bool."""

    def test_match_plugin_exact_match(self):
        """Exact case-insensitive match should return True."""
        stems = {"serum", "massive", "wavetable"}
        assert _match_plugin("Serum", stems) is True

    def test_match_plugin_case_insensitive(self):
        """Match should be case-insensitive."""
        stems = {"serum"}
        assert _match_plugin("SERUM", stems) is True
        assert _match_plugin("SeRuM", stems) is True

    def test_match_plugin_substring_in_stems(self):
        """Plugin name substring in stem should match."""
        stems = {"serum_x3"}
        assert _match_plugin("Serum", stems) is True

    def test_match_plugin_stem_in_name(self):
        """Stem substring in plugin name should match."""
        stems = {"serum"}
        assert _match_plugin("Serum X3", stems) is True

    def test_match_plugin_no_match(self):
        """Non-matching name should return False."""
        stems = {"serum", "massive"}
        assert _match_plugin("Sylenth1", stems) is False

    def test_match_plugin_empty_stems(self):
        """Empty stems set should not match any name."""
        stems = set()
        assert _match_plugin("Serum", stems) is False

    def test_match_plugin_whitespace_handling(self):
        """Leading/trailing whitespace should be handled."""
        stems = {"serum"}
        assert _match_plugin("  Serum  ", stems) is True

    def test_match_plugin_partial_match_both_ways(self):
        """Both directions of partial match should work."""
        stems = {"native_instruments_massive"}
        # 'massive' in stem → True
        assert _match_plugin("Massive", stems) is True

        stems2 = {"massive"}
        # 'massive' substring in longer name → True
        assert _match_plugin("Native Instruments Massive", stems2) is True


# ── GUI smoke test (PySide6 optional) ──────────────────────────────────────

def test_als_explorer_gui_acceptdrops(als_file):
    """Smoke test: AlsExplorerPanel accepts drops."""
    pytest.importorskip("PySide6")

    from PySide6.QtWidgets import QApplication
    from cratedig.gui.als_explorer import AlsExplorerPanel

    app = QApplication.instance() or QApplication([])

    w = AlsExplorerPanel()
    assert w.acceptDrops() is True

    w.close()


def test_als_explorer_gui_tab_count(als_file):
    """Smoke test: After loading a file, panel has 4 tabs: Overview / Instruments / Plugins / Tracks."""
    pytest.importorskip("PySide6")

    from PySide6.QtWidgets import QApplication, QTabWidget
    from cratedig.gui.als_explorer import AlsExplorerPanel

    app = QApplication.instance() or QApplication([])

    w = AlsExplorerPanel()
    w._load_file(als_file)

    tab_widget = w.findChild(QTabWidget)
    assert tab_widget is not None
    assert tab_widget.count() == 4

    w.close()


def test_project_checker_detect_routes_by_extension(als_file):
    """Detect mode picks parse_als for a .als and renders + names the DAW."""
    pytest.importorskip("PySide6")

    from PySide6.QtWidgets import QApplication, QTabWidget
    from cratedig.als.parser import parse_als
    from cratedig.gui.als_explorer import AlsExplorerPanel

    app = QApplication.instance() or QApplication([])

    w = AlsExplorerPanel(detect=True)
    w._load_file(str(als_file))

    assert w._parser is parse_als
    assert "Ableton Live" in w._title_lbl.text()
    tab_widget = w.findChild(QTabWidget)
    assert tab_widget is not None and tab_widget.count() == 4

    w.close()


def test_project_checker_detect_rejects_unknown_extension(tmp_path, monkeypatch):
    """An unsupported extension is rejected without raising (warning path)."""
    pytest.importorskip("PySide6")

    from PySide6.QtWidgets import QApplication
    from cratedig.gui import als_explorer
    from cratedig.gui.als_explorer import AlsExplorerPanel

    app = QApplication.instance() or QApplication([])
    # Don't pop a real modal in the headless test.
    monkeypatch.setattr(als_explorer.QMessageBox, "warning", lambda *a, **k: None)
    bogus = tmp_path / "notes.txt"
    bogus.write_text("not a project")

    w = AlsExplorerPanel(detect=True)
    assert w._resolve_detect(str(bogus)) is False
    assert w._data is None  # nothing loaded

    w.close()


def test_main_window_has_stacked_pages(tmp_path):
    """Smoke test: MainWindow embeds samples + unified Project Checker + Health."""
    pytest.importorskip("PySide6")

    from PySide6.QtWidgets import QApplication, QStackedWidget
    from cratedig.config import AudioCfg, Config, Paths
    from cratedig.db import Database
    from cratedig.gui.main_window import MainWindow
    from cratedig.gui.als_explorer import AlsExplorerPanel
    from cratedig.gui.health_panel import HealthPanel

    app = QApplication.instance() or QApplication([])

    cfg = Config(
        paths=Paths(db=tmp_path / "m.db", download_dir=tmp_path / "dl", library_dirs=(), saved_dir=tmp_path / "_saved"),
        audio=AudioCfg(),
    )
    db = Database(tmp_path / "m.db")
    w = MainWindow(db, cfg)

    stack = w.findChild(QStackedWidget)
    assert stack is not None
    # samples · Project Checker · Health
    assert stack.count() == 3
    assert isinstance(stack.widget(1), AlsExplorerPanel)
    assert isinstance(stack.widget(2), HealthPanel)

    # The Project Checker panel is in detect mode (one panel, all DAW formats).
    assert w._project_checker._detect is True

    # Sidebar switches to the Project Checker page.
    w._nav_checker.click()
    assert stack.currentIndex() == 1

    # Sidebar switches to the Health page.
    w._nav_health.click()
    assert stack.currentIndex() == 2

    w.close()
