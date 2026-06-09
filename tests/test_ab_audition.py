"""Tests for A/B audition workflow: loudness leveling, slot management, and keyboard shortcuts.

Tests TDD-style: these are FAILING tests that define the API the developer must satisfy.
Pure logic tests (loudness, ABState) are Qt-free and deterministic.
GUI tests are guarded with pytest.importorskip and run offscreen.
"""

from __future__ import annotations

import math
import os

import numpy as np
import pytest


class TestLevelGainDb:
    """Test pure loudness-leveling helper: level_gain_db(ref_loudness, target_loudness) -> dB.

    Loudness is measured as linear RMS amplitude (float in range [0, 1]).
    The function returns the dB gain to apply to target so it matches ref.

    Formula: gain_dB = 20 * log10(ref / target)
    - ref == target => gain = 0 dB
    - target < ref (quieter) => gain > 0 dB (boost)
    - target > ref (louder) => gain < 0 dB (cut)
    """

    def test_equal_loudness_returns_zero_db(self):
        """When ref and target have the same loudness, return 0.0 dB (within tolerance)."""
        from cratedig.audio.playback import level_gain_db

        # Both at 0.5 RMS
        result = level_gain_db(0.5, 0.5)
        assert isinstance(result, float)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_target_quieter_than_ref_returns_positive_db(self):
        """When target is quieter than ref, return positive dB (boost to match)."""
        from cratedig.audio.playback import level_gain_db

        # ref=0.5, target=0.25 (target is half as loud)
        result = level_gain_db(0.5, 0.25)

        # gain_dB = 20 * log10(0.5/0.25) = 20 * log10(2) ≈ 6.02
        assert result > 0.0
        assert result == pytest.approx(20 * math.log10(2.0), abs=0.01)

    def test_target_louder_than_ref_returns_negative_db(self):
        """When target is louder than ref, return negative dB (cut to match)."""
        from cratedig.audio.playback import level_gain_db

        # ref=0.25, target=0.5 (target is twice as loud)
        result = level_gain_db(0.25, 0.5)

        # gain_dB = 20 * log10(0.25/0.5) = 20 * log10(0.5) ≈ -6.02
        assert result < 0.0
        assert result == pytest.approx(20 * math.log10(0.5), abs=0.01)

    def test_symmetry_inverse_property(self):
        """Symmetry: level_gain_db(a, b) == -level_gain_db(b, a)."""
        from cratedig.audio.playback import level_gain_db

        a = 0.3
        b = 0.7

        gain_ab = level_gain_db(a, b)
        gain_ba = level_gain_db(b, a)

        # Inverse property: applying gain twice should get back to original
        assert gain_ab == pytest.approx(-gain_ba, abs=1e-6)

    def test_very_quiet_target_returns_large_positive_db(self):
        """A very quiet target should require large positive gain."""
        from cratedig.audio.playback import level_gain_db

        # ref=0.8, target=0.01 (target is 80x quieter)
        result = level_gain_db(0.8, 0.01)

        expected = 20 * math.log10(0.8 / 0.01)
        assert result > 0.0
        assert result == pytest.approx(expected, abs=0.01)

    def test_very_loud_target_returns_large_negative_db(self):
        """A very loud target should require large negative gain (cut)."""
        from cratedig.audio.playback import level_gain_db

        # ref=0.01, target=0.8 (target is 80x louder)
        result = level_gain_db(0.01, 0.8)

        expected = 20 * math.log10(0.01 / 0.8)
        assert result < 0.0
        assert result == pytest.approx(expected, abs=0.01)

    def test_guards_against_zero_or_negative_target(self):
        """Target <= 0 should raise ValueError (log of non-positive is undefined)."""
        from cratedig.audio.playback import level_gain_db

        with pytest.raises(ValueError):
            level_gain_db(0.5, 0.0)

        with pytest.raises(ValueError):
            level_gain_db(0.5, -0.1)

    def test_guards_against_zero_ref_raises(self):
        """Ref <= 0 should also raise ValueError."""
        from cratedig.audio.playback import level_gain_db

        with pytest.raises(ValueError):
            level_gain_db(0.0, 0.5)

        with pytest.raises(ValueError):
            level_gain_db(-0.1, 0.5)

    def test_return_type_is_python_float(self):
        """Return type must be a plain Python float, not numpy."""
        from cratedig.audio.playback import level_gain_db

        result = level_gain_db(0.5, 0.25)
        assert type(result) is float
        assert not isinstance(result, np.floating)


class TestABState:
    """Test pure A/B slot model: ABState(slot_a, slot_b, current).

    Minimal immutable or quasi-immutable data class holding two sample IDs
    and a "current" flag indicating which slot is active.
    """

    def test_ab_state_stores_slot_ids(self):
        """ABState(slot_a=1, slot_b=2, current='a') stores both IDs."""
        from cratedig.gui.logic import ABState

        state = ABState(slot_a=1, slot_b=2, current='a')
        assert state.slot_a == 1
        assert state.slot_b == 2

    def test_ab_state_stores_current_flag(self):
        """ABState stores current as 'a' or 'b'."""
        from cratedig.gui.logic import ABState

        state_a = ABState(slot_a=10, slot_b=20, current='a')
        assert state_a.current == 'a'

        state_b = ABState(slot_a=10, slot_b=20, current='b')
        assert state_b.current == 'b'

    def test_active_id_returns_current_slot_id(self):
        """active_id() returns the ID of the currently active slot."""
        from cratedig.gui.logic import ABState

        state = ABState(slot_a=100, slot_b=200, current='a')
        assert state.active_id() == 100

        state_b = ABState(slot_a=100, slot_b=200, current='b')
        assert state_b.active_id() == 200

    def test_toggle_flips_current_and_returns_new_active_id(self):
        """toggle() flips current A<->B and returns the now-active sample ID."""
        from cratedig.gui.logic import ABState

        state = ABState(slot_a=10, slot_b=20, current='a')
        new_state, new_id = state.toggle()

        assert new_state.current == 'b'
        assert new_id == 20

        # Toggle again to go back to A
        state2, id2 = new_state.toggle()
        assert state2.current == 'a'
        assert id2 == 10

    def test_toggle_with_empty_other_slot_stays_on_filled_slot(self):
        """toggle() with empty other slot stays on the filled slot (no crash)."""
        from cratedig.gui.logic import ABState

        # A is filled, B is None (empty)
        state = ABState(slot_a=10, slot_b=None, current='a')
        new_state, new_id = state.toggle()

        # Should stay on A (the filled slot), not crash
        assert new_state.current == 'a'
        assert new_id == 10

    def test_toggle_with_both_slots_empty_raises_or_handles_gracefully(self):
        """toggle() with both slots empty should raise or return a sensible default."""
        from cratedig.gui.logic import ABState

        # Both empty
        state = ABState(slot_a=None, slot_b=None, current='a')

        # Should either raise ValueError or return a safe value
        with pytest.raises((ValueError, RuntimeError)):
            state.toggle()

    def test_set_a_returns_new_state_with_updated_slot_a(self):
        """set_a(sample_id) returns a new ABState with slot_a updated."""
        from cratedig.gui.logic import ABState

        state = ABState(slot_a=1, slot_b=2, current='a')
        new_state = state.set_a(100)

        assert new_state.slot_a == 100
        assert new_state.slot_b == 2
        assert new_state.current == 'a'

    def test_set_b_returns_new_state_with_updated_slot_b(self):
        """set_b(sample_id) returns a new ABState with slot_b updated."""
        from cratedig.gui.logic import ABState

        state = ABState(slot_a=1, slot_b=2, current='a')
        new_state = state.set_b(200)

        assert new_state.slot_a == 1
        assert new_state.slot_b == 200
        assert new_state.current == 'a'

    def test_initial_state_with_none_slots(self):
        """ABState can be initialized with None slots (both empty)."""
        from cratedig.gui.logic import ABState

        state = ABState(slot_a=None, slot_b=None, current='a')
        assert state.slot_a is None
        assert state.slot_b is None
        assert state.current == 'a'

    def test_ab_state_is_immutable_or_returns_new_instance(self):
        """Calling set_a/set_b/toggle does not mutate original state."""
        from cratedig.gui.logic import ABState

        orig = ABState(slot_a=1, slot_b=2, current='a')
        new_a = orig.set_a(10)
        new_b = orig.set_b(20)
        new_toggle, _ = orig.toggle()

        # Original should be unchanged
        assert orig.slot_a == 1
        assert orig.slot_b == 2
        assert orig.current == 'a'

        # New instances differ
        assert new_a.slot_a == 10
        assert new_b.slot_b == 20
        assert new_toggle.current == 'b'

    def test_only_one_slot_filled_active_id_returns_that_id(self):
        """When only one slot is filled, active_id always returns it."""
        from cratedig.gui.logic import ABState

        state = ABState(slot_a=5, slot_b=None, current='b')
        # current='b', but B is None, so only A is available
        # active_id should return A's id
        assert state.active_id() == 5

    def test_toggle_when_only_one_slot_filled_stays_on_that_slot(self):
        """toggle() when only one slot is filled stays on that slot."""
        from cratedig.gui.logic import ABState

        state = ABState(slot_a=5, slot_b=None, current='b')
        new_state, new_id = state.toggle()

        # Should stay on A (the only filled slot)
        assert new_state.current == 'a'
        assert new_id == 5

        # Toggle again: should stay on A
        state2, id2 = new_state.toggle()
        assert state2.current == 'a'
        assert id2 == 5


class TestABGUISmoke:
    """Smoke tests for A/B GUI wiring: MainWindow or player widget exposes A/B toggle.

    Tests are guarded with pytest.importorskip and run offscreen. Just verify
    attributes/methods exist and don't raise on no-op calls.
    """

    def _app(self):
        """Set up QApplication for PySide6 tests."""
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        pytest.importorskip("PySide6")
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() or QApplication([])

    def test_player_widget_has_loudness_leveling_option(self):
        """Player widget (playback) exposes a loudness leveling flag or method."""
        self._app()
        pytest.importorskip("PySide6")

        from cratedig.gui.player import Player

        player = Player()

        # Should have a loudness leveling option
        assert hasattr(player, "apply_loudness_leveling") or hasattr(player, "_level_gain")


class TestABIntegration:
    """Integration: A/B toggling, loudness leveling on switch, mark fav/crate during playback.

    Tests the flow: select sample A, toggle to B, optional level, mark favorite, etc.
    """

    def test_ab_toggle_switches_playback_to_new_slot(self):
        """After toggle, playback should switch to the new active sample."""
        from cratedig.gui.logic import ABState

        # Start with A active
        state = ABState(slot_a=10, slot_b=20, current='a')

        # Toggle to B
        new_state, new_id = state.toggle()

        assert new_id == 20  # Should now play B

        # Toggle back to A
        state2, id2 = new_state.toggle()
        assert id2 == 10  # Should now play A

    def test_ab_state_allows_marking_fav_while_playing(self):
        """A/B state can coexist with favorite marking (orthogonal features)."""
        from cratedig.gui.logic import ABState

        state = ABState(slot_a=1, slot_b=2, current='a')

        # Mark slot A as favorite (this happens in DB, not in ABState)
        # But we can query active_id to know which to mark
        fav_id = state.active_id()
        assert fav_id == 1

        # Toggle and mark the new active slot
        new_state, new_id = state.toggle()
        fav_id2 = new_state.active_id()
        assert fav_id2 == 2

    def test_level_gain_db_applied_on_playback_switch(self):
        """loudness leveling: compute gain and apply on slot switch."""
        from cratedig.audio.playback import level_gain_db
        import math

        # Simulate two samples with different loudness
        loudness_a = 0.5  # RMS
        loudness_b = 0.25  # half as loud

        # Compute gain to match B to A
        gain_db = level_gain_db(loudness_a, loudness_b)

        # Should be positive (boost B)
        assert gain_db > 0.0
        assert gain_db == pytest.approx(20 * math.log10(2.0), abs=0.01)
