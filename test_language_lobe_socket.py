"""Socket transport and hesitation behavior for the standalone LanguageLobe."""

from __future__ import annotations

import socket
import threading
import time

import pytest

from language_lobe import LanguageClient, LanguageLobe


def _serve(lobe):
    thread = threading.Thread(target=lobe.start_server, daemon=True)
    thread.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if lobe.socket_path.exists():
            return thread
        time.sleep(0.01)
    lobe.shutdown()
    raise AssertionError("LanguageLobe did not create its socket")


def test_language_client_round_trips_hesitation_prefixes(tmp_path):
    path = str(tmp_path / "nested" / "language.sock")
    lobe = LanguageLobe(path)
    thread = _serve(lobe)
    client = LanguageClient(path)
    try:
        assert client.send_packet("share_insight", "I found a pattern.", 0.8) == (
            "Um... I found a pattern."
        )
        assert client.send_packet("inquire", "Could you clarify?", 0.5) == (
            "Well... Could you clarify?"
        )
        assert client.send_packet("statement", "All set.", 0.4) == "All set."
        long_content = "language " * 600
        assert client.send_packet("statement", long_content) == long_content
    finally:
        lobe.shutdown()
        thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert not lobe.socket_path.exists()


def test_startup_removes_stale_socket_and_rebinds(tmp_path):
    path = tmp_path / "stale.sock"
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(path))
    stale.close()

    lobe = LanguageLobe(str(path))
    thread = _serve(lobe)
    try:
        assert LanguageClient(str(path)).send_packet(
            "statement", "Rebound successfully."
        ) == "Rebound successfully."
    finally:
        lobe.shutdown()
        thread.join(timeout=2.0)
    assert not thread.is_alive()


def test_startup_preserves_active_socket_and_regular_files(tmp_path):
    path = tmp_path / "active.sock"
    active = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    active.bind(str(path))
    active.listen(1)
    try:
        with pytest.raises(OSError, match="already accepting"):
            LanguageLobe(str(path))
    finally:
        active.close()
        path.unlink(missing_ok=True)

    regular_file = tmp_path / "not-a-socket"
    regular_file.write_text("keep", encoding="utf-8")
    with pytest.raises(OSError, match="non-socket"):
        LanguageLobe(str(regular_file))
    assert regular_file.read_text(encoding="utf-8") == "keep"
