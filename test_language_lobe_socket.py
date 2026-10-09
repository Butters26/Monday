"""Socket transport and hesitation behavior for the standalone LanguageLobe."""

from __future__ import annotations

import socket
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor

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


def _read_exact(conn, size):
    parts = []
    while size:
        part = conn.recv(size)
        assert part
        parts.append(part)
        size -= len(part)
    return b"".join(parts)


def _read_frame(conn):
    (size,) = struct.unpack("!I", _read_exact(conn, 4))
    return _read_exact(conn, size)


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
        with ThreadPoolExecutor(max_workers=8) as clients:
            results = list(
                clients.map(
                    lambda index: client.send_packet(
                        "statement", f"Message {index}"
                    ),
                    range(8),
                )
            )
        assert results == [f"Message {index}" for index in range(8)]
        with pytest.raises(ValueError, match="maximum size"):
            client.send_packet("statement", "x" * 70000)
    finally:
        lobe.shutdown()
        thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert not lobe.socket_path.exists()


def test_server_reads_fragmented_length_prefixed_packet(tmp_path):
    path = str(tmp_path / "fragmented.sock")
    lobe = LanguageLobe(path)
    thread = _serve(lobe)
    try:
        payload = b'{"intent":"statement","content":"Fragmented safely."}'
        frame = struct.pack("!I", len(payload)) + payload
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(path)
            for offset in range(0, len(frame), 3):
                client.sendall(frame[offset : offset + 3])
            response = _read_frame(client)
        assert response == b"Fragmented safely."
    finally:
        lobe.shutdown()
        thread.join(timeout=2.0)
    assert not thread.is_alive()


def test_server_rejects_oversized_frame_header(tmp_path):
    path = str(tmp_path / "oversized.sock")
    lobe = LanguageLobe(path)
    thread = _serve(lobe)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(path)
            client.sendall(struct.pack("!I", 65537))
            assert _read_frame(client) == b"Invalid language packet"
    finally:
        lobe.shutdown()
        thread.join(timeout=2.0)
    assert not thread.is_alive()


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
