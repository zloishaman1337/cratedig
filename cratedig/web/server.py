"""Local web panel for sample diving.

The server is intentionally stdlib-only: it is a local companion UI over the
existing SQLite library, not a separate application stack.
"""

from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from ..audio.playback import decode_waveform_data
from ..config import Config
from ..db import Database
from ..db.models import Sample

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
_SERVER: ThreadingHTTPServer | None = None
_SERVER_THREAD: threading.Thread | None = None


def sample_to_payload(db: Database, sample: Sample) -> dict:
    data = asdict(sample)
    data["tags"] = db.tags_for(sample.id) if sample.id is not None else []
    data["audio_url"] = f"/audio?id={sample.id}" if sample.id is not None else None
    data["waveform_url"] = f"/api/waveform?id={sample.id}" if sample.id is not None else None
    return data


def build_tree(samples: list[Sample], roots: tuple[Path, ...]) -> list[dict]:
    root_nodes: dict[str, dict] = {}
    resolved_roots = [r.resolve() for r in roots if str(r)]

    for sample in sorted(samples, key=lambda s: s.path.lower()):
        path = Path(sample.path)
        rel_parts: tuple[str, ...]
        root_label = "Library"
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path

        for root in resolved_roots:
            try:
                rel = resolved.relative_to(root)
            except ValueError:
                continue
            root_label = root.name or str(root)
            rel_parts = rel.parts
            break
        else:
            parent = path.parent
            root_label = parent.name or str(parent) or "Library"
            rel_parts = (path.name,)

        node = root_nodes.setdefault(root_label, {"name": root_label, "type": "folder", "children": {}})
        for part in rel_parts[:-1]:
            node = node["children"].setdefault(part, {"name": part, "type": "folder", "children": {}})
        node["children"][rel_parts[-1]] = {
            "name": sample.filename,
            "type": "sample",
            "id": sample.id,
            "category": sample.category,
            "duration_sec": sample.duration_sec,
        }

    def freeze(node: dict) -> dict:
        children = node.get("children")
        if isinstance(children, dict):
            ordered = sorted(children.values(), key=lambda n: (n["type"] == "sample", n["name"].lower()))
            node = {k: v for k, v in node.items() if k != "children"}
            node["children"] = [freeze(child) for child in ordered]
        return node

    return [freeze(root_nodes[name]) for name in sorted(root_nodes, key=str.lower)]


def waveform_to_payload(data) -> dict:
    return {
        "duration_sec": data.duration_sec,
        "sample_rate": data.sample_rate,
        "channels": data.channels,
        "bins": data.bins,
        "peaks": data.peaks.tolist(),
        "rms": data.rms.tolist(),
    }


def ensure_web_server(cfg: Config, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    global _SERVER, _SERVER_THREAD
    if _SERVER is not None:
        return f"http://{host}:{_SERVER.server_port}"

    handler = _make_handler(cfg)
    _SERVER = ThreadingHTTPServer((host, port), handler)
    _SERVER_THREAD = threading.Thread(target=_SERVER.serve_forever, daemon=True)
    _SERVER_THREAD.start()
    return f"http://{host}:{_SERVER.server_port}"


def run_web(
    cfg: Config,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    sample_id: int | None = None,
) -> None:
    global _SERVER
    if _SERVER is None:
        _SERVER = ThreadingHTTPServer((host, port), _make_handler(cfg))
    url = f"http://{host}:{_SERVER.server_port}"
    if sample_id is not None:
        url = f"{url}/?sample={sample_id}"
    if open_browser:
        webbrowser.open(url)
    print(f"cratedig web panel: {url}")
    assert _SERVER is not None
    try:
        _SERVER.serve_forever()
    except KeyboardInterrupt:
        pass


def _make_handler(cfg: Config):
    class WebHandler(BaseHTTPRequestHandler):
        server_version = "cratedig-web/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_static("index.html", "text/html; charset=utf-8")
            elif parsed.path.startswith("/static/"):
                self._send_static(unquote(parsed.path.removeprefix("/static/")))
            elif parsed.path == "/api/tree":
                self._send_tree()
            elif parsed.path == "/api/sample":
                self._send_sample(parsed.query)
            elif parsed.path == "/api/waveform":
                self._send_waveform(parsed.query)
            elif parsed.path == "/audio":
                self._send_audio(parsed.query)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def log_message(self, fmt: str, *args) -> None:
            return

        def _db(self) -> Database:
            return Database(cfg.paths.db)

        def _send_json(self, payload: dict | list, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_static(self, name: str, content_type: str | None = None) -> None:
            if "/" in name or "\\" in name:
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            try:
                ref = resources.files("cratedig.web.static").joinpath(name)
                body = ref.read_bytes()
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            ctype = content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _sample_id(self, query: str) -> int | None:
            raw = parse_qs(query).get("id", [""])[0]
            try:
                return int(raw)
            except ValueError:
                return None

        def _send_tree(self) -> None:
            with self._db() as db:
                samples = db.all_samples(limit=20000)
            self._send_json(build_tree(samples, cfg.paths.library_dirs))

        def _send_sample(self, query: str) -> None:
            sample_id = self._sample_id(query)
            if sample_id is None:
                self.send_error(HTTPStatus.BAD_REQUEST, "missing sample id")
                return
            with self._db() as db:
                sample = db.get_sample(sample_id)
                if sample is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                payload = sample_to_payload(db, sample)
            self._send_json(payload)

        def _send_waveform(self, query: str) -> None:
            params = parse_qs(query)
            sample_id = self._sample_id(query)
            if sample_id is None:
                self.send_error(HTTPStatus.BAD_REQUEST, "missing sample id")
                return
            try:
                bins = max(256, min(8192, int(params.get("bins", ["2048"])[0])))
            except ValueError:
                bins = 2048
            with self._db() as db:
                sample = db.get_sample(sample_id)
            if sample is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                data = decode_waveform_data(sample.path, bins=bins, channels=sample.channels or 2)
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json(waveform_to_payload(data))

        def _send_audio(self, query: str) -> None:
            sample_id = self._sample_id(query)
            if sample_id is None:
                self.send_error(HTTPStatus.BAD_REQUEST, "missing sample id")
                return
            with self._db() as db:
                sample = db.get_sample(sample_id)
            if sample is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._send_file(Path(sample.path))

        def _send_file(self, path: Path) -> None:
            if not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            size = path.stat().st_size
            start, end = 0, size - 1
            status = HTTPStatus.OK
            range_header = self.headers.get("Range")
            if range_header and range_header.startswith("bytes="):
                raw_start, _, raw_end = range_header.removeprefix("bytes=").partition("-")
                try:
                    start = int(raw_start) if raw_start else 0
                    end = int(raw_end) if raw_end else size - 1
                    start = max(0, min(start, size - 1))
                    end = max(start, min(end, size - 1))
                    status = HTTPStatus.PARTIAL_CONTENT
                except ValueError:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return

            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "audio/*")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with path.open("rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = fh.read(min(1024 * 256, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    self.wfile.write(chunk)

    return WebHandler


def sample_url(base_url: str, sample_id: int | None = None) -> str:
    if sample_id is None:
        return base_url
    return f"{base_url}/?sample={quote(str(sample_id))}"
