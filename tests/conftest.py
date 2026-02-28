"""Shared fixtures for Spondex tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def base_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect all Spondex runtime files to a temporary directory.

    Patches ``spondex.config.get_base_dir`` (and the re-imported reference in
    ``spondex.daemon``) so that nothing touches the real ``~/.spondex/``.
    """
    fake_base = tmp_path / ".spondex"
    fake_base.mkdir()
    (fake_base / "logs").mkdir()

    monkeypatch.setattr("spondex.config.get_base_dir", lambda: fake_base)
    monkeypatch.setattr("spondex.daemon.get_base_dir", lambda: fake_base)

    return fake_base
