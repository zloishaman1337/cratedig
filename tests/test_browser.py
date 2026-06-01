"""Tests for cratedig.tui.browser module."""

from pathlib import Path

from cratedig.db.models import Sample
from cratedig.tui.browser import build_folder_tree, FolderNode


def _sample(path: str, **kw) -> Sample:
    return Sample(id=None, path=path, filename=path.split("/")[-1], **kw)


def test_build_folder_tree_sample_under_root_subfolder(tmp_path):
    """Test that a sample in a subfolder creates both root and subfolder nodes."""
    root = tmp_path / "packs"
    samples = [
        Sample(id=1, path=str(root / "drums" / "kick.wav"), filename="kick.wav", category="kick"),
    ]

    nodes = build_folder_tree(samples, (root,))

    # Root node should exist
    assert "packs" in nodes
    assert nodes["packs"].name == "packs"
    assert nodes["packs"].key == "packs"
    assert nodes["packs"].parent_key is None

    # Subfolder node should exist
    assert "packs/drums" in nodes
    assert nodes["packs/drums"].name == "drums"
    assert nodes["packs/drums"].key == "packs/drums"
    assert nodes["packs/drums"].parent_key == "packs"

    # Sample should be in the subfolder's samples list
    assert len(nodes["packs/drums"].samples) == 1
    assert nodes["packs/drums"].samples[0].filename == "kick.wav"

    # Root folder should have the subfolder as a child
    assert "drums" in nodes["packs"].children
    assert nodes["packs"].children["drums"] is nodes["packs/drums"]


def test_build_folder_tree_multiple_subfolders_same_root(tmp_path):
    """Test that two samples in different subfolders create separate subfolder nodes."""
    root = tmp_path / "packs"
    samples = [
        Sample(id=1, path=str(root / "drums" / "kick.wav"), filename="kick.wav", category="kick"),
        Sample(id=2, path=str(root / "bass" / "sub.wav"), filename="sub.wav", category="bass"),
    ]

    nodes = build_folder_tree(samples, (root,))

    # Root should have both subfolders
    assert "packs/drums" in nodes
    assert "packs/bass" in nodes
    assert "drums" in nodes["packs"].children
    assert "bass" in nodes["packs"].children

    # Each subfolder should have its own sample
    assert len(nodes["packs/drums"].samples) == 1
    assert nodes["packs/drums"].samples[0].filename == "kick.wav"
    assert len(nodes["packs/bass"].samples) == 1
    assert nodes["packs/bass"].samples[0].filename == "sub.wav"


def test_build_folder_tree_sample_directly_under_root(tmp_path):
    """Test that a sample directly under root lands in root's samples list."""
    root = tmp_path / "packs"
    samples = [
        Sample(id=1, path=str(root / "loop.wav"), filename="loop.wav", category="loop"),
    ]

    nodes = build_folder_tree(samples, (root,))

    # Root should exist
    assert "packs" in nodes
    assert nodes["packs"].name == "packs"

    # Sample should be in root's samples list
    assert len(nodes["packs"].samples) == 1
    assert nodes["packs"].samples[0].filename == "loop.wav"

    # No subfolders should be created
    assert len(nodes["packs"].children) == 0


def test_build_folder_tree_deeply_nested_sample(tmp_path):
    """Test that deeply nested samples create all intermediate folder nodes."""
    root = tmp_path / "packs"
    samples = [
        Sample(
            id=1,
            path=str(root / "drums" / "kicks" / "acoustic" / "kick01.wav"),
            filename="kick01.wav",
            category="kick",
        ),
    ]

    nodes = build_folder_tree(samples, (root,))

    # All intermediate nodes should exist
    assert "packs" in nodes
    assert "packs/drums" in nodes
    assert "packs/drums/kicks" in nodes
    assert "packs/drums/kicks/acoustic" in nodes

    # Check parent relationships
    assert nodes["packs"].parent_key is None
    assert nodes["packs/drums"].parent_key == "packs"
    assert nodes["packs/drums/kicks"].parent_key == "packs/drums"
    assert nodes["packs/drums/kicks/acoustic"].parent_key == "packs/drums/kicks"

    # Sample should be in the deepest folder
    assert len(nodes["packs/drums/kicks/acoustic"].samples) == 1
    assert nodes["packs/drums/kicks/acoustic"].samples[0].filename == "kick01.wav"

    # Check child relationships
    assert "drums" in nodes["packs"].children
    assert "kicks" in nodes["packs/drums"].children
    assert "acoustic" in nodes["packs/drums/kicks"].children


def test_build_folder_tree_mixed_depths(tmp_path):
    """Test multiple samples at different nesting depths."""
    root = tmp_path / "packs"
    samples = [
        Sample(id=1, path=str(root / "loop.wav"), filename="loop.wav"),
        Sample(id=2, path=str(root / "drums" / "kick.wav"), filename="kick.wav"),
        Sample(id=3, path=str(root / "drums" / "snare.wav"), filename="snare.wav"),
        Sample(id=4, path=str(root / "bass" / "deep" / "sub.wav"), filename="sub.wav"),
    ]

    nodes = build_folder_tree(samples, (root,))

    # Root should have one sample and two child folders
    assert len(nodes["packs"].samples) == 1
    assert len(nodes["packs"].children) == 2

    # Drums folder should have two samples
    assert len(nodes["packs/drums"].samples) == 2
    sample_names = {s.filename for s in nodes["packs/drums"].samples}
    assert sample_names == {"kick.wav", "snare.wav"}

    # Bass/deep folder should have one sample
    assert len(nodes["packs/bass/deep"].samples) == 1
    assert nodes["packs/bass/deep"].samples[0].filename == "sub.wav"


def test_build_folder_tree_empty_samples(tmp_path):
    """Test that empty samples list returns empty dict."""
    root = tmp_path / "packs"
    samples = []

    nodes = build_folder_tree(samples, (root,))

    assert nodes == {}


def test_build_folder_tree_sample_outside_root(tmp_path):
    """Test that a sample path outside any root falls back to parent folder name."""
    root = tmp_path / "packs"
    other_dir = tmp_path / "other_place"
    
    samples = [
        Sample(id=1, path=str(other_dir / "kick.wav"), filename="kick.wav"),
    ]

    nodes = build_folder_tree(samples, (root,))

    # Should use parent folder name as root label since sample doesn't match root
    assert "other_place" in nodes
    assert nodes["other_place"].name == "other_place"
    assert nodes["other_place"].parent_key is None
    assert len(nodes["other_place"].samples) == 1


def test_build_folder_tree_no_roots(tmp_path):
    """Test that samples with no roots use Library as fallback."""
    samples = [
        Sample(id=1, path="/some/path/kick.wav", filename="kick.wav"),
    ]

    nodes = build_folder_tree(samples, ())

    # Should use parent folder name
    assert "path" in nodes
    assert nodes["path"].name == "path"
    assert len(nodes["path"].samples) == 1
