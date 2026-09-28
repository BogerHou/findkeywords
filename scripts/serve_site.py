#!/usr/bin/env python3
"""Serve only the project's public research snapshot on localhost."""

import csv
import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import parse_qsl, quote, unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
HOST, PORT = "127.0.0.1", 8878
ALLOWED = {"site", "reports", "data"}


class Handler(BaseHTTPRequestHandler):
    server_version = "FindKeywords/1"

    def do_GET(self):
        self.serve_file(send_body=True)

    def do_HEAD(self):
        self.serve_file(send_body=False)

    def serve_file(self, send_body):
        try:
            parsed_url = urlsplit(self.path)
            path = unquote(parsed_url.path, encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, ValueError):
            self.send_error(400, "Invalid URL")
            return
        if path == "/site/export.csv":
            self.serve_csv(parsed_url.query, send_body)
            return
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/site/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        parts = path.strip("/").split("/")
        if not path.startswith("/") or "\\" in path or "\x00" in path or parts[0] not in ALLOWED or any(not part or part.startswith(".") for part in parts):
            self.send_error(404, "Not found")
            return
        candidate = ROOT.joinpath(*parts)
        try:
            resolved = candidate.resolve()
            relative = resolved.relative_to(ROOT)
        except (ValueError, OSError):
            self.send_error(404, "Not found")
            return
        # Resolve symlinks before checking boundaries; hidden targets stay hidden.
        if not relative.parts or relative.parts[0] not in ALLOWED or any(p.startswith(".") for p in relative.parts):
            self.send_error(404, "Not found")
            return
        # This run contains quarantined source material. Only its neutral public
        # snapshot is exposed by the local website; original evidence stays local.
        if relative.parts[:2] == ('data', 'runs') and len(relative.parts)>2 and relative.parts[2] in {'2026-09-26-tld', '2026-09-26-trends30'} and (len(relative.parts) < 4 or relative.parts[3] != 'public'):
            self.send_error(404, "Private research evidence")
            return
        if resolved.is_dir():
            if parts != ["site"]:
                self.send_error(404, "Directory listing disabled")
                return
            if not path.endswith("/"):
                self.send_response(301)
                self.send_header("Location", quote(path, safe="/") + "/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            resolved = (resolved / "index.html").resolve()
            try:
                relative = resolved.relative_to(ROOT)
            except ValueError:
                self.send_error(404, "Not found")
                return
            if not relative.parts or relative.parts[0] not in ALLOWED or any(p.startswith(".") for p in relative.parts):
                self.send_error(404, "Not found")
                return
        if not resolved.is_file():
            self.send_error(404, "Not found")
            return
        try:
            with resolved.open("rb") as source:
                content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
                if resolved.suffix in {".md", ".txt"}:
                    content_type = "text/plain"
                if content_type.startswith("text/") or content_type in {"application/json", "application/javascript"}:
                    content_type += "; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(resolved.stat().st_size))
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                if send_body:
                    shutil.copyfileobj(source, self.wfile)
        except (BrokenPipeError, ConnectionResetError):
            return
        except OSError:
            self.send_error(404, "Not found")

    def serve_csv(self, query, send_body):
        try:
            if len(query) > 4096 or re.search(r"%(?![0-9A-Fa-f]{2})", query):
                raise ValueError("Invalid query encoding or length")
            parameters = parse_qsl(query, keep_blank_values=True, strict_parsing=True,
                                   encoding="utf-8", errors="strict", max_num_fields=1) if query else []
            if parameters and parameters[0][0] != "ids":
                raise ValueError("Only ids is supported")
            requested = parameters[0][1].split(",") if parameters else None
            if requested is not None and (not all(requested) or len(requested) != len(set(requested))):
                raise ValueError("Empty or repeated IDs")
        except (UnicodeDecodeError, ValueError):
            self.send_error(400, "Invalid export IDs")
            return

        try:
            source = (ROOT / "site" / "data.json").resolve()
            relative = source.relative_to(ROOT)
            if relative.parts[0] not in ALLOWED or any(p.startswith(".") for p in relative.parts):
                raise ValueError("Research data outside served directories")
            keywords = json.loads(source.read_text(encoding="utf-8"))["keywords"]
            known_ids = {item["id"] for item in keywords}
        except (OSError, ValueError, KeyError, TypeError):
            self.send_error(500, "Research data unavailable")
            return
        if requested is not None and (len(requested) > len(keywords) or not set(requested).issubset(known_ids)):
            self.send_error(400, "Unknown or excessive export IDs")
            return
        selected = set(requested) if requested is not None else known_ids
        fields = ["关键词", "来源域名", "分组", "研究状态", "基准情景下限（非实测）",
                  "基准情景上限（非实测）", "证据字段", "页面原文", "口径"]

        def cell(value):
            text = "" if value is None else str(value)
            # Spreadsheet apps can interpret formulas even after leading spaces.
            if text[:1] in {"\t", "\r", "\n"} or text.lstrip(" \t\r\n")[:1] in {"=", "+", "-", "@"}:
                text = "'" + text
            return text

        output = io.StringIO(newline="")
        writer = csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        writer.writerow(fields)
        for item in keywords:
            if item["id"] not in selected:
                continue
            estimate_range = item.get("estimateRange") or {}
            writer.writerow(cell(value) for value in [
                item["keyword"], item["domain"], item["group"], item["statusLabel"],
                estimate_range.get("min"), estimate_range.get("max"), item["sourceField"],
                item["evidenceQuote"], "美国／网页搜索；年度条件性月均量级；非当前月实测或网站流量",
            ])
        content = output.getvalue().encode("utf-8-sig")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Content-Disposition", 'attachment; filename="findkeywords-2026-09-26.csv"')
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if send_body:
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError):
                pass


def main():
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            print(f"端口 {PORT} 已被占用。若工作台已启动，请直接访问 http://{HOST}:{PORT}/site/ 。")
            print("如果该端口属于其他程序，请先自行关闭那个程序后再启动；本脚本不会终止任何进程。")
            return 1
        raise
    print(f"关键词工作台：http://{HOST}:{PORT}/site/", flush=True)
    print("本地只读服务。关闭此终端或按 Ctrl+C 停止。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n工作台服务已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
