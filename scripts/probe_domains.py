#!/usr/bin/env python3
"""Probe a small JSON domain sample using Python's standard library and curl.

Input: [{"domain": "example.com"}, ...]
Usage: python3 scripts/probe_domains.py --input sample.json --output results.json

No certificate age is inferred here. registration_date comes only from an RDAP
event whose eventAction is 'registration'. Unknown dates remain unknown. This
script fetches public homepages; it does not run JavaScript or bypass blocking.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from urllib.parse import quote, urljoin, urlsplit, urlunsplit


TIMEOUT_SECONDS = 10
MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 512 * 1024
MAX_HEADER_BYTES = 64 * 1024
REDIRECT_CODES = {301, 302, 303, 307, 308}
USER_AGENT = "FindKeywordsResearch/0.1 (public homepage and RDAP sampling)"
FAKE_IP_RANGE = ipaddress.ip_network("198.18.0.0/15")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_text(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


def normalize_domain(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("domain must be a string")
    value = value.strip().rstrip(".")
    if any(c in value for c in "/:@?#\\") or any(ord(c) < 33 for c in value):
        raise ValueError("domain must be a hostname without a URL, port, or wildcard")
    try:
        domain = value.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("invalid IDNA domain") from exc
    labels = domain.split(".")
    if len(domain) > 253 or len(labels) < 2 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
        for part in labels
    ):
        raise ValueError("invalid domain name")
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        return domain
    raise ValueError("IP literals are not domain names")


def run_curl_bounded(command: list[str], limit: int) -> tuple[bytes, bytes, int, bool]:
    """Bound decoded stdout even on curl versions with weaker max-filesize handling."""
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert proc.stdout is not None
        body = proc.stdout.read(limit + 1)
        oversized = len(body) > limit
        if oversized:
            proc.kill()
        _, stderr = proc.communicate(timeout=TIMEOUT_SECONDS + 2)
        return body[:limit], stderr, proc.returncode, oversized
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()


@lru_cache(maxsize=1024)
def doh_addresses(host: str) -> tuple[str, ...]:
    """Resolve through public DoH when local DNS returns a proxy Fake-IP.

    The resolver hostname is pinned to 1.1.1.1 with normal TLS verification.
    This bootstrap request never follows redirects. Only DNS answers are read.
    """
    command = [
        "curl", "-q", "--silent", "--show-error", "--globoff", "--noproxy", "*",
        "--proto", "=https", "--connect-timeout", "5", "--max-time", str(TIMEOUT_SECONDS),
        "--max-filesize", "65536", "--fail", "--resolve", "cloudflare-dns.com:443:1.1.1.1",
        "--header", "accept: application/dns-json", "--url",
        f"https://cloudflare-dns.com/dns-query?name={quote(host, safe='')}&type=A",
    ]
    body, stderr, returncode, oversized = run_curl_bounded(command, 65536)
    if returncode or oversized:
        raise OSError("public DNS-over-HTTPS lookup failed: " + stderr.decode("utf-8", errors="replace")[:200])
    try:
        answer = json.loads(body)
        if answer.get("Status") != 0:
            raise ValueError("DNS response was not successful")
        ips = tuple(row["data"] for row in answer.get("Answer", []) if row.get("type") in {1, 28})
        if not ips:
            raise ValueError("DNS response has no A/AAAA records")
        return ips
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        raise OSError(f"public DNS-over-HTTPS lookup failed: {exc}") from exc


def safe_target(url: str, *, allow_fake_ip_doh: bool = True) -> tuple[str, str, int, str]:
    """Validate every hop and resolve it once, then pin curl to that public IP."""
    if len(url) > 8192 or "\\" in url or any(ord(c) < 32 or ord(c) == 127 for c in url):
        raise ValueError("URL contains unsafe characters or is too long")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("only http/https URLs with a hostname are permitted")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URL credentials are not permitted")
    default_port = 443 if parts.scheme == "https" else 80
    if parts.port not in {None, default_port}:
        raise ValueError("only the default HTTP/HTTPS port is permitted")
    host = parts.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    if not host or any(c in host for c in "%/\\"):
        raise ValueError("invalid URL hostname")
    addresses = socket.getaddrinfo(host, default_port, type=socket.SOCK_STREAM)
    ips = {entry[4][0] for entry in addresses}
    if not ips:
        raise ValueError("hostname resolved to no IP addresses")
    # Some desktop proxy tools synthesize benchmark-range addresses. Never
    # connect to those. Resolve the hostname publicly and pin the real address.
    if allow_fake_ip_doh and all(ipaddress.ip_address(ip) in FAKE_IP_RANGE for ip in ips):
        try:
            ipaddress.ip_address(host)
        except ValueError:
            ips = set(doh_addresses(host))
    for address in ips:
        ip = ipaddress.ip_address(address)
        # Explicitly reject mapped/transition IPv6 addresses as well as local,
        # reserved, multicast, link-local, documentation, and private addresses.
        if not ip.is_global or ip.is_multicast or (
            isinstance(ip, ipaddress.IPv6Address)
            and (ip.ipv4_mapped is not None or ip.sixtofour is not None or ip.teredo is not None)
        ):
            raise ValueError("hostname resolves to a non-public or transition IP address")
    address = sorted(ips, key=lambda ip: (":" in ip, ip))[0]
    authority = f"[{host}]" if ":" in host else host
    safe_url = urlunsplit((
        parts.scheme, authority,
        quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~"),
        quote(parts.query, safe="/%?:@!$&'()*+,;=-._~"), "",
    ))
    return safe_url, host, default_port, address


def parse_headers(raw: bytes) -> tuple[int | None, dict[str, str]]:
    status = None
    headers: dict[str, str] = {}
    # curl can receive interim 100/103 header blocks. Use the final block.
    for line in raw.decode("iso-8859-1", errors="replace").splitlines():
        if line.startswith("HTTP/"):
            match = re.match(r"HTTP/\S+\s+(\d{3})", line)
            status = int(match.group(1)) if match else None
            headers = {}
        elif ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return status, headers


def fetch_public(url: str, *, max_redirects: int | None = None,
                 allow_fake_ip_doh: bool = True,
                 max_response_bytes: int | None = None) -> dict:
    """Fetch with manually validated redirects, TLS checks, and a body limit."""
    result = {
        "status": "network_error", "http_status": None, "final_url": url,
        "fetched_at": iso_time(utc_now()), "content_type": None,
        "error": None, "body": b"", "body_truncated": False,
        "error_kind": None, "curl_exit_code": None, "request_count": 0,
        "retry_after": None, "location": None,
    }
    seen: set[str] = set()
    body_limit = MAX_RESPONSE_BYTES if max_response_bytes is None else max_response_bytes
    if not 0 < body_limit <= MAX_RESPONSE_BYTES:
        raise ValueError("response limit must be between 1 and MAX_RESPONSE_BYTES")
    redirect_limit = MAX_REDIRECTS if max_redirects is None else max_redirects
    for hop in range(redirect_limit + 1):
        try:
            current_url, host, port, address = safe_target(url, allow_fake_ip_doh=allow_fake_ip_doh)
        except (ValueError, UnicodeError, OSError, subprocess.SubprocessError) as exc:
            result.update(status="blocked_url" if isinstance(exc, ValueError) else "network_error",
                          final_url=url, error=str(exc)[:500],
                          error_kind=("dns_error" if isinstance(exc, socket.gaierror) else
                                      "timeout" if isinstance(exc, TimeoutError) else "target_error"))
            return result
        result["final_url"] = current_url
        if current_url in seen:
            result.update(status="redirect_error", error="redirect loop")
            return result
        seen.add(current_url)
        pin = f"[{address}]" if ":" in address else address
        # -q must be first: ignore ~/.curlrc (proxies, redirects, TLS overrides).
        with tempfile.TemporaryDirectory(prefix="findkeywords-probe-") as temp_dir:
            header_path = Path(temp_dir) / "headers"
            command = [
                "curl", "-q", "--silent", "--show-error", "--globoff",
                "--noproxy", "*", "--proto", "=http,https",
                "--connect-timeout", "5", "--max-time", str(TIMEOUT_SECONDS),
                "--max-filesize", str(body_limit), "--compressed",
                "--resolve", f"{host}:{port}:{pin}",
                "--dump-header", str(header_path), "--output", "-",
                "--user-agent", USER_AGENT, "--url", current_url,
            ]
            try:
                result["request_count"] += 1
                body, stderr, returncode, oversized = run_curl_bounded(command, body_limit)
            except (OSError, subprocess.TimeoutExpired) as exc:
                result.update(error=str(exc)[:500], error_kind="timeout" if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)) else "transport_error")
                return result
            raw_headers = b""
            if header_path.exists():
                with header_path.open("rb") as header_file:
                    raw_headers = header_file.read(MAX_HEADER_BYTES + 1)
            if len(raw_headers) > MAX_HEADER_BYTES:
                result.update(status="too_large", error="HTTP headers exceed limit")
                return result
        status, headers = parse_headers(raw_headers)
        result.update(http_status=status, content_type=headers.get("content-type"),
                      fetched_at=iso_time(utc_now()), curl_exit_code=returncode,
                      retry_after=headers.get("retry-after"), location=headers.get("location"))
        if oversized or returncode == 63:
            result.update(status="too_large", error=f"response exceeds {body_limit} byte limit",
                          body_truncated=True, body=body)
            return result
        if returncode != 0:
            result.update(error=stderr.decode("utf-8", errors="replace").strip()[:500]
                          or f"curl exited with code {returncode}",
                          error_kind={6: "dns_error", 7: "connect_error", 28: "timeout",
                                      35: "tls_handshake_error", 60: "tls_certificate_error",
                                      77: "local_ca_error"}.get(returncode, "transport_error"))
            return result
        if status in REDIRECT_CODES:
            location = headers.get("location")
            if not location:
                result.update(status="redirect_error", error="redirect has no Location header")
                return result
            if hop == redirect_limit:
                result.update(status="redirect_error", error="redirect limit reached")
                return result
            url = urljoin(current_url, location)
            continue
        if status is None:
            result.update(error="no HTTP response status")
            return result
        if not 200 <= status < 300:
            result.update(status="http_error", error=f"HTTP {status}")
            return result
        result.update(status="ok", body=body)
        return result
    return result


def decode_html(body: bytes, content_type: str | None) -> str:
    candidates = []
    if body.startswith((b"\xff\xfe", b"\xfe\xff")):
        candidates.append("utf-16")
    if body.startswith(b"\xef\xbb\xbf"):
        candidates.append("utf-8-sig")
    if content_type:
        match = re.search(r"charset\s*=\s*[\"']?([^;\s\"']+)", content_type, re.I)
        if match:
            candidates.append(match.group(1))
    prefix = body[:8192].decode("ascii", errors="ignore")
    match = re.search(r"<meta\b[^>]*charset\s*=\s*[\"']?([^\s\"'/>;]+)", prefix, re.I)
    if match:
        candidates.append(match.group(1))
    candidates.extend(["utf-8", "gb18030", "windows-1252"])
    for encoding in candidates:
        try:
            return body.decode(encoding)
        except (UnicodeError, LookupError):
            pass
    return body.decode("utf-8", errors="replace")


class PageParser(HTMLParser):
    """Extract document metadata and a bounded text sample without rendering."""

    OMIT = {"script", "style", "noscript", "template", "svg", "head"}
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.description = ""
        self.og_description = ""
        self.headings: list[list[str]] = []
        self.text_parts: list[str] = []
        self.text_size = 0
        self.stack: list[tuple[str, bool]] = []
        self.in_title = False
        self.heading: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): (value or "") for key, value in attrs}
        parent_hidden = bool(self.stack and self.stack[-1][1])
        hidden = (parent_hidden or tag in self.OMIT or "hidden" in attributes
                  or attributes.get("aria-hidden", "").lower() == "true"
                  or bool(re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)",
                                    attributes.get("style", ""), re.I)))
        if tag not in self.VOID:
            self.stack.append((tag, hidden))
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            name = attributes.get("name", "").lower()
            prop = attributes.get("property", "").lower()
            if name == "description" and not self.description:
                self.description = attributes.get("content", "")
            if (prop or name) == "og:description" and not self.og_description:
                self.og_description = attributes.get("content", "")
        elif tag == "h1" and not hidden and len(self.headings) < 10:
            self.heading = []
            self.headings.append(self.heading)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif tag == "h1":
            self.heading = None
        for position in range(len(self.stack) - 1, -1, -1):
            if self.stack[position][0] == tag:
                del self.stack[position:]
                break

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.stack and self.stack[-1][1]:
            return
        if self.heading is not None:
            self.heading.append(data)
        if self.text_size < 5000:
            text = clean_text(data, 5000 - self.text_size)
            if text:
                self.text_parts.append(text)
                self.text_size += len(text) + 1

    def extracted(self) -> dict:
        return {
            "title": clean_text(" ".join(self.title_parts), 600),
            "description": clean_text(self.description, 1500),
            "og_description": clean_text(self.og_description, 1500),
            "h1": [text for parts in self.headings if (text := clean_text(" ".join(parts), 600))],
            "visible_text": clean_text(" ".join(self.text_parts), 3000),
        }


def registration_from_events(document: object, max_age_days: int, now: datetime) -> tuple[str | None, str, str | None]:
    """Never treat last changed, renewal, or expiration as registration."""
    if not isinstance(document, dict) or not isinstance(document.get("events"), list):
        return None, "unknown", "RDAP response has no events array"
    dates = []
    for event in document["events"]:
        if not isinstance(event, dict) or str(event.get("eventAction", "")).lower() != "registration":
            continue
        try:
            raw = event["eventDate"]
            date = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if date.tzinfo is None:
                continue
            dates.append(date.astimezone(timezone.utc))
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    if not dates:
        return None, "unknown", "RDAP has no usable registration event"
    registered = min(dates)
    age_seconds = (now - registered).total_seconds()
    if age_seconds < 0:
        return iso_time(registered), "unknown", "registration date is in the future"
    status = "verified_recent" if age_seconds <= max_age_days * 86400 else "verified_old"
    return iso_time(registered), status, None


def probe_domain(item: object, max_age_days: int) -> dict:
    raw_domain = item.get("domain") if isinstance(item, dict) else None
    result = {
        **(item if isinstance(item, dict) else {}),
        "domain": raw_domain, "http_status": None, "final_url": None,
        "fetched_at": None, "fetch_status": "invalid_domain", "fetch_error": None,
        "content_type": None, "title": "", "description": "", "og_description": "",
        "h1": [], "visible_text": "", "registration_date": None,
        "registration_status": "unknown", "registration_source": None,
        "registration_http_status": None, "registration_checked_at": None,
        "registration_error": None,
    }
    try:
        domain = normalize_domain(raw_domain)
    except ValueError as exc:
        result.update(fetch_error=str(exc), registration_error="invalid domain")
        return result
    result["domain"] = domain
    homepage = fetch_public(f"https://{domain}/")
    result.update(
        http_status=homepage["http_status"], final_url=homepage["final_url"],
        fetched_at=homepage["fetched_at"], fetch_status=homepage["status"],
        fetch_error=homepage["error"], content_type=homepage["content_type"],
    )
    if homepage["status"] == "ok":
        content_type = (homepage["content_type"] or "").lower().split(";", 1)[0].strip()
        body = homepage["body"]
        looks_html = bool(re.search(br"<(?:!doctype\s+html|html|head|title|body)\b", body[:4096], re.I))
        if content_type in {"text/html", "application/xhtml+xml"} or (not content_type and looks_html):
            try:
                parser = PageParser()
                parser.feed(decode_html(body, homepage["content_type"]))
                parser.close()
                result.update(parser.extracted())
            except Exception as exc:
                result.update(fetch_status="parse_error", fetch_error=f"HTML parse failed: {exc}"[:500])
        else:
            result.update(fetch_status="unsupported_content_type", fetch_error="response is not HTML")
    # Do this even when the homepage is unavailable; conversely, an old RDAP
    # registration never prevents the homepage evidence above from being saved.
    rdap = fetch_public(f"https://rdap.org/domain/{quote(domain, safe='')}")
    result.update(registration_source=rdap["final_url"],
                  registration_http_status=rdap["http_status"],
                  registration_checked_at=rdap["fetched_at"])
    if rdap["status"] != "ok":
        result["registration_error"] = rdap["error"] or rdap["status"]
        return result
    try:
        # Retain only registration evidence, never RDAP contacts or raw bodies.
        document = json.loads(rdap["body"])
        date, status, error = registration_from_events(document, max_age_days, utc_now())
        result.update(registration_date=date, registration_status=status, registration_error=error)
    except (ValueError, UnicodeError) as exc:
        result["registration_error"] = f"RDAP response is not valid JSON: {exc}"[:500]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path, help="JSON array of objects with domain fields")
    parser.add_argument("--output", required=True, type=Path, help="JSON output (replaced atomically)")
    parser.add_argument("--max-age-days", type=int, default=30)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.max_age_days < 0 or not 1 <= args.workers <= 16:
        parser.error("--max-age-days must be nonnegative; --workers must be 1 through 16")
    if not shutil.which("curl"):
        parser.error("curl must be installed and available on PATH")
    try:
        items = json.loads(args.input.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        parser.error(f"cannot read input: {exc}")
    if not isinstance(items, list):
        parser.error("input must be a JSON array")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda item: probe_domain(item, args.max_age_days), items))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".tmp", delete=False,
                                         dir=args.output.parent) as output:
            temp_path = Path(output.name)
            json.dump(results, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temp_path, args.output)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    counts: dict[str, int] = {}
    for result in results:
        key = result["registration_status"]
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({"count": len(results), "registration_status_counts": counts,
                      "output": str(args.output)}, ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
