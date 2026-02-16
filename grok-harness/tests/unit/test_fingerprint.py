"""Unit tests for fingerprint module."""

import pytest
from pathlib import Path

from grok_harness.browser.fingerprint import BrowserFingerprint


@pytest.fixture
def fingerprint_manager(tmp_path: Path) -> BrowserFingerprint:
    """Fingerprint manager fixture."""
    return BrowserFingerprint(tmp_path)


def test_generate_fingerprint(fingerprint_manager: BrowserFingerprint) -> None:
    """Test fingerprint generation."""
    fp = fingerprint_manager.generate_fingerprint()

    assert "id" in fp
    assert "created_at" in fp
    assert "user_agent" in fp
    assert "screen" in fp
    assert "fonts" in fp
    assert "webgl_vendor" in fp
    assert "audio" in fp
    assert "canvas" in fp


def test_generate_fingerprint_with_seed(
    fingerprint_manager: BrowserFingerprint,
) -> None:
    """Test deterministic fingerprint generation with seed."""
    fp1 = fingerprint_manager.generate_fingerprint(seed="test-domain.com")
    fp2 = fingerprint_manager.generate_fingerprint(seed="test-domain.com")

    assert fp1["id"] == fp2["id"]
    assert fp1["user_agent"] == fp2["user_agent"]


def test_different_seeds_different_fingerprints(
    fingerprint_manager: BrowserFingerprint,
) -> None:
    """Test different seeds produce different fingerprints."""
    fp1 = fingerprint_manager.generate_fingerprint(seed="domain1.com")
    fp2 = fingerprint_manager.generate_fingerprint(seed="domain2.com")

    assert fp1["id"] != fp2["id"]


def test_save_load_fingerprint(
    fingerprint_manager: BrowserFingerprint,
) -> None:
    """Test saving and loading fingerprints."""
    fp = fingerprint_manager.generate_fingerprint()
    fp_id = fingerprint_manager.save_fingerprint(fp)

    loaded = fingerprint_manager.load_fingerprint(fp_id)
    assert loaded is not None
    assert loaded["id"] == fp["id"]
    assert loaded["user_agent"] == fp["user_agent"]


def test_list_fingerprints(fingerprint_manager: BrowserFingerprint) -> None:
    """Test listing fingerprints."""
    fp1 = fingerprint_manager.generate_fingerprint(seed="fingerprint-1")
    fp2 = fingerprint_manager.generate_fingerprint(seed="fingerprint-2")

    fingerprint_manager.save_fingerprint(fp1)
    fingerprint_manager.save_fingerprint(fp2)

    fingerprints = fingerprint_manager.list_fingerprints()
    assert len(fingerprints) >= 2


def test_delete_fingerprint(
    fingerprint_manager: BrowserFingerprint,
) -> None:
    """Test deleting fingerprint."""
    fp = fingerprint_manager.generate_fingerprint()
    fp_id = fingerprint_manager.save_fingerprint(fp)

    assert fingerprint_manager.load_fingerprint(fp_id) is not None

    fingerprint_manager.delete_fingerprint(fp_id)
    assert fingerprint_manager.load_fingerprint(fp_id) is None


def test_consistent_fingerprint_for_domain(
    fingerprint_manager: BrowserFingerprint,
) -> None:
    """Test getting consistent fingerprint for domain."""
    fp1 = fingerprint_manager.get_consistent_fingerprint("example.com")
    fp2 = fingerprint_manager.get_consistent_fingerprint("example.com")

    assert fp1["id"] == fp2["id"]

    fp3 = fingerprint_manager.get_consistent_fingerprint("different.com")
    assert fp1["id"] != fp3["id"]


def test_fingerprint_components(
    fingerprint_manager: BrowserFingerprint,
) -> None:
    """Test fingerprint has all required components."""
    fp = fingerprint_manager.generate_fingerprint()

    assert "width" in fp["screen"]
    assert "height" in fp["screen"]
    assert "color_depth" in fp["screen"]

    assert "cores" in fp["hardware"]
    assert "memory" in fp["hardware"]

    assert "vendor" in fp["webgl_vendor"]
    assert "renderer" in fp["webgl_vendor"]

    assert isinstance(fp["fonts"], list)
    assert len(fp["fonts"]) > 0


def test_fingerprint_persistence(
    fingerprint_manager: BrowserFingerprint,
    tmp_path: Path,
) -> None:
    """Test fingerprints persist across instances."""
    fp = fingerprint_manager.generate_fingerprint()
    fp_id = fingerprint_manager.save_fingerprint(fp)

    new_manager = BrowserFingerprint(tmp_path)

    loaded = new_manager.load_fingerprint(fp_id)
    assert loaded is not None
    assert loaded["id"] == fp["id"]
