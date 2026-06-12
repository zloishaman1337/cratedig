"""Extension → parser dispatch for the unified Project Checker."""

from __future__ import annotations

from cratedig.als.parser import parse_als
from cratedig.projects_fmt import detect
from cratedig.projects_fmt.common import to_checker_data
from cratedig.projects_fmt.nuendo import parse_npr
from cratedig.projects_fmt.reaper import parse_rpp


def test_parser_for_known_extensions():
    assert detect.parser_for("song.als").parser is parse_als
    assert detect.parser_for("a.bwproject").name == "Bitwig"
    assert detect.parser_for("mix.cpr").parser is parse_npr  # Cubase reuses Nuendo
    assert detect.parser_for("mix.npr").name == "Nuendo"
    assert detect.parser_for("track.rpp").parser is parse_rpp
    assert detect.parser_for("track.RPP").parser is parse_rpp  # case-insensitive
    assert detect.parser_for("My Song.logicx").name == "Logic Pro"


def test_rpp_bak_does_not_collide_with_rpp():
    spec = detect.parser_for("project.rpp-bak")
    assert spec is not None and spec.parser is parse_rpp


def test_als_carries_no_normalizer_others_do():
    assert detect.parser_for("x.als").normalizer is None
    assert detect.parser_for("x.flp").normalizer is to_checker_data


def test_unknown_extension_returns_none():
    assert detect.parser_for("notes.txt") is None
    assert detect.parser_for("kick.wav") is None


def test_file_filter_lists_every_extension():
    flt = detect.file_filter()
    for ext in detect.ALL_EXTS:
        assert f"*{ext}" in flt
