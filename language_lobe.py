"""Unix-socket interface for realizing already-formed Mercy language packets."""

from __future__ import annotations

import json
import errno
import logging
import math
import socket
import stat
import threading
from pathlib import Path
from typing import Any, Dict, Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("MondayLanguageLobe")


class LanguageClient:
    """Send one semantic packet to a LanguageLobe Unix-domain socket."""

    def __init__(self, socket_path: str = "~/.local/state/monday-chat/chat.sock"):
        self.socket_path = Path(socket_path).expanduser()

    def send_packet(
        self, intent: str, content: str, hesitation_level: float = 0.0
    ) -> str:
        packet = {
            "intent": intent,
            "content": content,
            "hesitation_level": hesitation_level,
        }
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(self.socket_path))
            client.sendall(json.dumps(packet).encode("utf-8"))
            client.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8")


class LanguageLobe:
    """Realize supplied semantic packet content and serve it over a Unix socket."""

    _MAX_PACKET_BYTES = 65536

    def __init__(self, socket_path: str = "~/.local/state/monday-chat/chat.sock"):
        self.socket_path = Path(socket_path).expanduser()
        self._server: Optional[socket.socket] = None
        self._running = False
        self._setup_socket()

    def _setup_socket(self) -> None:
        """Create the socket directory and remove only a genuinely stale socket."""
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            existing = self.socket_path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(existing.st_mode):
            raise OSError(f"Refusing to replace non-socket path: {self.socket_path}")

        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.connect(str(self.socket_path))
        except OSError as exc:
            if exc.errno not in (errno.ECONNREFUSED, errno.ENOENT):
                raise
            try:
                current = self.socket_path.lstat()
            except FileNotFoundError:
                return
            if (
                (current.st_dev, current.st_ino) == (existing.st_dev, existing.st_ino)
                and stat.S_ISSOCK(current.st_mode)
            ):
                self.socket_path.unlink(missing_ok=True)
                logger.info("Removed stale socket file at %s", self.socket_path)
        else:
            raise OSError(f"Language socket is already accepting connections: {self.socket_path}")
        finally:
            probe.close()

    def format_realization(self, semantic_packet: Dict[str, Any]) -> str:
        """Express supplied packet content, without inferring or inventing meaning."""
        if not isinstance(semantic_packet, dict):
            raise ValueError("semantic packet must be a JSON object")
        intent = semantic_packet.get("intent", "statement")
        content = semantic_packet.get("content", "")
        try:
            hesitation = float(semantic_packet.get("hesitation_level", 0.0))
        except (TypeError, ValueError) as exc:
            raise ValueError("hesitation_level must be numeric") from exc
        if not math.isfinite(hesitation):
            raise ValueError("hesitation_level must be finite")

        prefix = ""
        if hesitation > 0.7:
            prefix = "Um... "
        elif hesitation > 0.4:
            prefix = "Well... "

        logger.info("Realizing language packet for intent: %s", intent)
        return f"{prefix}{content}"

    def start_server(self) -> None:
        """Bind and serve packets until :meth:`shutdown` is called."""
        self._setup_socket()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.settimeout(0.2)
        self._server = server
        bound_identity = None
        try:
            server.bind(str(self.socket_path))
            bound_stat = self.socket_path.lstat()
            bound_identity = (bound_stat.st_dev, bound_stat.st_ino)
            server.listen(8)
            self._running = True
            logger.info("Language Lobe listening on %s", self.socket_path)
            while self._running:
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self._running:
                        raise
                    break
                with conn:
                    self._handle_connection(conn)
        finally:
            self._running = False
            server.close()
            self._server = None
            try:
                current = self.socket_path.lstat()
                if bound_identity and (current.st_dev, current.st_ino) == bound_identity:
                    self.socket_path.unlink()
            except FileNotFoundError:
                pass

    def _handle_connection(self, conn: socket.socket) -> None:
        chunks = []
        total = 0
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            total += len(chunk)
            if total > self._MAX_PACKET_BYTES:
                conn.sendall(b"Packet too large")
                return
            chunks.append(chunk)
        try:
            packet = json.loads(b"".join(chunks).decode("utf-8"))
            response = self.format_realization(packet)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            logger.error("Invalid language packet: %s", exc)
            response = "Invalid language packet"
        except Exception:
            logger.exception("Error handling language packet")
            response = "Language realization failed"
        conn.sendall(response.encode("utf-8"))

    def shutdown(self) -> None:
        """Ask the accept loop to stop and release its socket."""
        self._running = False


if __name__ == "__main__":
    LanguageLobe().start_server()
