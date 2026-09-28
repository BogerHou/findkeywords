"""Offline policy/transport tests. Unmocked DNS and subprocesses fail the tests."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import probe_domains as probe
import probe_prescreen as pre


def response(body=b"", status=200, **extra):
    return {"status": "ok" if status is not None and 200 <= status < 300 else "http_error",
            "http_status": status, "body": body, "content_type": "text/html",
            "final_url": "https://generator.example/", "curl_exit_code": 0,
            "request_count": 1, **extra}


CONTENT = b"<html><title>Recipe generator</title><body><h1>Recipe generator</h1><p>" + b"Choose ingredients and build a recipe for your family. " * 6 + b"</p></body></html>"
DOMAIN = "generator.example"
ORIGIN = "https://" + DOMAIN


class FakeTransport:
    def __init__(self, routes):
        self.routes, self.urls = routes, []

    def get(self, url, *, stage="homepage"):
        self.urls.append(url)
        return self.routes[url]


class PrecheckTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch("socket.getaddrinfo", side_effect=AssertionError("Unexpected real DNS")))
        self.stack.enter_context(patch("subprocess.Popen", side_effect=AssertionError("Unexpected process/network")))
        self.addCleanup(self.stack.close)

    def check(self, homepage, robots=None):
        routes = {ORIGIN + "/robots.txt": robots or response(status=404), ORIGIN + "/": homepage}
        transport = FakeTransport(routes)
        return pre.DomainCheck({"domain": DOMAIN}, transport).run(), transport

    def test_substantive_page_without_description_passes(self):
        row, transport = self.check(response(CONTENT))
        self.assertEqual(row["decision"], "pass")
        self.assertEqual(row["page"]["title"], "Recipe generator")
        self.assertEqual(len(transport.urls), 2)

    def test_parking_and_default_pages_skip(self):
        for title, reason in [("This domain is for sale", "parking_page"), ("Coming soon", "placeholder_page"), ("Welcome to nginx!", "placeholder_page"), ("404 - Page not found", "soft_404")]:
            with self.subTest(title=title):
                row, _ = self.check(response(f"<title>{title}</title><h1>{title}</h1>".encode()))
                self.assertEqual((row["decision"], row["reason"]), ("skip", reason))

    def test_article_discussing_domain_sales_is_not_parking(self):
        html = b"<title>How to buy this domain</title><p>" + b"Read the guide to choosing a name and negotiating a purchase. " * 40 + b"</p>"
        row, _ = self.check(response(html))
        self.assertEqual(row["decision"], "pass")

    def test_javascript_empty_and_short_pages_are_uncertain(self):
        for html, reason in [(b'<title>App</title><div id="root"></div><script src="app.js"></script>', "javascript_or_thin"), (b"<title>Loan calculator</title><h1>Loan calculator</h1><input>", "thin_or_empty"), (b"", "thin_or_empty")]:
            row, _ = self.check(response(html))
            self.assertEqual((row["decision"], row["reason"]), ("recheck", reason))

    def test_truncated_html_is_evidence_not_a_pass_or_empty_site(self):
        partial = response(b"<title>Recipe generator</title>", body_truncated=True)
        partial["status"] = "too_large"
        row, _ = self.check(partial)
        self.assertEqual(row["decision"], "recheck")
        self.assertTrue(row["incomplete_html"])
        self.assertEqual(row["page_prefix"]["title"], "Recipe generator")

    def test_challenge_is_not_an_empty_or_unused_site(self):
        row, _ = self.check(response(b"<title>Just a moment...</title><p>Verify you are human</p>"))
        self.assertEqual((row["decision"], row["reason"]), ("recheck", "challenge"))

    def test_robots_disallow_stops_before_homepage(self):
        row, transport = self.check(response(CONTENT), response(b"User-agent: *\nDisallow: /\n", content_type="text/plain"))
        self.assertEqual(row["reason"], "robots_disallowed")
        self.assertEqual(transport.urls, [ORIGIN + "/robots.txt"])

    def test_complex_robots_rules_do_not_get_ignored(self):
        row, transport = self.check(response(CONTENT), response(b"User-agent: *\n  Disallow: /*\n", content_type="text/plain"))
        self.assertEqual(row["reason"], "robots_complex_rules")
        self.assertEqual(len(transport.urls), 1)

    def test_https_certificate_failure_is_deferred_without_http_fallback(self):
        row, transport = self.check(response(CONTENT), response(status=None, error_kind="tls_certificate_error", curl_exit_code=60))
        self.assertEqual((row["decision"], row["reason"]), ("recheck", "tls_certificate_error"))
        self.assertEqual(len(transport.urls), 1)

    def test_429_stops_batch_and_preserves_retry_after(self):
        row, transport = self.check(response(CONTENT), response(status=429, retry_after="1800"))
        self.assertTrue(row["stop_batch"])
        self.assertEqual(row["requests"][0]["retry_after"], "1800")
        self.assertEqual(len(transport.urls), 1)

    def test_forbidden_and_timeout_are_deferred(self):
        row, _ = self.check(response(status=403))
        self.assertEqual(row["reason"], "http_blocked")
        transport = FakeTransport({})
        with patch.object(transport, "get", side_effect=TimeoutError("DNS timed out")):
            row = pre.DomainCheck({"domain": DOMAIN}, transport).run()
        self.assertEqual(row["reason"], "timeout")

    def test_missing_homepage_skips_but_missing_robots_does_not(self):
        row, transport = self.check(response(status=404))
        self.assertEqual(row["reason"], "homepage_missing")
        self.assertEqual(len(transport.urls), 2)

    def test_external_redirect_or_http_downgrade_not_followed(self):
        for location, reason in [("https://auction.example/buy", "external_or_unsupported_redirect"), ("http://generator.example/", "https_downgrade")]:
            row, transport = self.check(response(status=301, location=location))
            self.assertEqual(row["reason"], reason)
            self.assertEqual(len(transport.urls), 2)

    def test_www_redirect_obeys_destination_robots(self):
        www = "https://www." + DOMAIN
        transport = FakeTransport({ORIGIN + "/robots.txt": response(status=404),
                                   ORIGIN + "/": response(status=301, location=www + "/"),
                                   www + "/robots.txt": response(b"User-agent: *\nDisallow: /", content_type="text/plain")})
        row = pre.DomainCheck({"domain": DOMAIN}, transport).run()
        self.assertEqual(row["reason"], "robots_disallowed")
        self.assertEqual(len(transport.urls), 3)

    def test_private_and_fake_addresses_rejected_without_doh(self):
        for address in ("127.0.0.1", "169.254.169.254", "198.18.0.3"):
            with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]), patch.object(probe, "doh_addresses", side_effect=AssertionError("Unexpected DoH")):
                result = probe.fetch_public(ORIGIN, allow_fake_ip_doh=False)
            self.assertEqual(result["status"], "blocked_url")
            self.assertEqual(result["request_count"], 0)

    def test_dns_failure_diagnostic_without_http(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror(-2, "no address")):
            result = probe.fetch_public(ORIGIN, allow_fake_ip_doh=False)
        self.assertEqual(result["error_kind"], "dns_error")
        self.assertEqual(result["request_count"], 0)

    def test_tls_verification_enabled_and_exit_code_recorded(self):
        with patch.object(probe, "safe_target", return_value=(ORIGIN, DOMAIN, 443, "1.1.1.1")), patch.object(probe, "run_curl_bounded", return_value=(b"", b"certificate failed", 60, False)) as curl:
            result = probe.fetch_public(ORIGIN, max_redirects=0, allow_fake_ip_doh=False)
        self.assertEqual(result["error_kind"], "tls_certificate_error")
        command = curl.call_args.args[0]
        self.assertNotIn("--insecure", command)
        self.assertNotIn("-k", command)
        self.assertNotIn("--location", command)
        self.assertIn("--noproxy", command)

    def test_run_requires_local_config_and_rejects_wrong_machine_or_proxy(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "queue.json"
            path.write_text(json.dumps({"domains": [{"domain": DOMAIN}]}))
            args = argparse.Namespace(input=path, output=Path(folder) / "out", limit=100, execute=False,
                                      network_config=Path(folder) / "network.local.json", label="test-mac")
            with contextlib.redirect_stdout(io.StringIO()):
                pre.run(args)
            self.assertFalse(args.output.exists())
            args.execute = True
            with patch.object(pre.sys, "platform", "darwin"), self.assertRaises(SystemExit):
                pre.run(args)
            with patch.object(pre.sys, "platform", "darwin"), contextlib.redirect_stdout(io.StringIO()):
                pre.network_init(args)
                with patch.dict("os.environ", {"https_proxy": "http://proxy.invalid"}), self.assertRaises(SystemExit):
                    pre.run(args)
                with patch.object(pre, "machine_marker", return_value="different-computer"), self.assertRaises(SystemExit):
                    pre.run(args)
            self.assertFalse(args.output.exists())

    def test_batch_stops_after_429_and_refuses_automatic_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "queue.json"
            path.write_text(json.dumps({"domains": [{"domain": DOMAIN}, {"domain": "next.example"}]}))
            args = argparse.Namespace(input=path, output=Path(folder) / "out", limit=100, execute=True,
                                      network_config=Path(folder) / "network.local.json", label="test-mac")
            transport = FakeTransport({ORIGIN + "/robots.txt": response(status=429, retry_after="1800")})
            with patch.object(pre.sys, "platform", "linux"), patch.dict("os.environ", {}, clear=True), patch.object(pre.shutil, "which", return_value="/usr/bin/curl"), patch.object(pre, "Transport", return_value=transport), contextlib.redirect_stdout(io.StringIO()):
                pre.network_init(args)
                pre.run(args)
                summary = json.loads((args.output / "summary.json").read_text())
                self.assertEqual(summary["stop_reason"], "rate_limited")
                self.assertEqual(summary["completed"], 1)
                self.assertEqual(summary["pending"], 1)
                with self.assertRaises(SystemExit):
                    pre.run(args)
            self.assertEqual(transport.urls, [ORIGIN + "/robots.txt"])


if __name__ == "__main__":
    unittest.main()
