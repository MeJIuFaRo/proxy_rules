import io
import json
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import call, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from scripts import update_ip_lists as updater


URL = "https://example.invalid/ranges"


def http_error(code):
    return HTTPError(URL, code, "simulated response", {}, io.BytesIO())


class SlowBody(io.BytesIO):
    def read(self, *args):
        raise TimeoutError("The read operation timed out")


class RetryTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.urlopen = stack.enter_context(patch.object(updater.urllib.request, "urlopen"))
        self.sleep = stack.enter_context(patch.object(updater.time, "sleep"))

    def test_first_attempt_succeeds(self):
        self.urlopen.return_value = io.BytesIO(b"192.0.2.0/24\n")
        self.assertEqual(updater.http_get(URL), "192.0.2.0/24\n")
        self.urlopen.assert_called_once()
        self.sleep.assert_not_called()

    def test_timeout_while_reading_then_timeout_while_opening(self):
        body = SlowBody()
        self.urlopen.side_effect = [body, URLError(TimeoutError()), io.BytesIO(b"ok")]
        self.assertEqual(updater.http_get(URL), "ok")
        self.assertTrue(body.closed)
        self.assertEqual(self.sleep.call_args_list, [call(1), call(2)])
        for attempt in self.urlopen.call_args_list:
            self.assertEqual(attempt.args[0].full_url, URL)
            self.assertEqual(attempt.kwargs["timeout"], 60)

    def test_transient_statuses(self):
        for code in (408, 429, 500, 502, 503, 504):
            with self.subTest(code=code):
                self.urlopen.reset_mock()
                self.sleep.reset_mock()
                self.urlopen.side_effect = [http_error(code), io.BytesIO(b"ok")]
                self.assertEqual(updater.http_get(URL), "ok")
                self.assertEqual(self.urlopen.call_count, 2)
                self.sleep.assert_called_once_with(1)

    def test_permanent_errors(self):
        errors = [http_error(code) for code in (400, 401, 403, 404, 501)]
        errors.append(URLError("certificate verify failed"))
        for error in errors:
            with self.subTest(error=str(error)):
                self.urlopen.reset_mock()
                self.urlopen.side_effect = error
                with self.assertRaises(type(error)) as caught:
                    updater.http_get(URL)
                self.assertIs(caught.exception, error)
                self.urlopen.assert_called_once()
                self.sleep.assert_not_called()

    def test_invalid_ripestat_data(self):
        cases = [(b"{", json.JSONDecodeError), (b'{"status":"error"}', RuntimeError)]
        for payload, error in cases:
            with self.subTest(payload=payload):
                self.urlopen.reset_mock()
                self.urlopen.return_value = io.BytesIO(payload)
                with self.assertRaises(error):
                    updater.asn_prefixes(32934)
                self.urlopen.assert_called_once()
                self.sleep.assert_not_called()

    def test_ripe_db_retries_with_original_headers_and_encoding(self):
        inetnum = {"primary-key": {"attribute": [{"value": "192.0.2.0 - 192.0.2.255"}]}}
        payload = json.dumps({"objects": {"object": [inetnum]}}).encode("utf-16")
        self.urlopen.side_effect = [http_error(503), io.BytesIO(payload)]
        nets = updater.ripe_org_inetnums("ORG-TEST-RIPE")
        self.assertEqual(nets, {updater.Network("192.0.2.0/24")})
        self.sleep.assert_called_once_with(1)
        self.assertEqual(self.urlopen.call_count, 2)
        for attempt in self.urlopen.call_args_list:
            headers = dict(attempt.args[0].header_items())
            self.assertEqual(headers["Accept"], "application/json")
            self.assertEqual(headers["User-agent"], updater.USER_AGENT)

    def test_exhausted_meta_asn_preserves_previous_list_and_continues(self):
        meta = updater.Source("meta", "Meta", asns=[32934, 63293, 54115])
        other = updater.Source("other", "Other", urls=[URL])
        partial = {"status": "ok", "data": {"prefixes": [{"prefix": "198.51.100.0/24"}]}}
        self.urlopen.side_effect = [
            io.BytesIO(json.dumps(partial).encode()),
            SlowBody(), SlowBody(), SlowBody(),
            io.BytesIO(b"203.0.113.0/24\n"),
        ]
        with TemporaryDirectory() as directory:
            out = Path(directory)
            previous = b"192.0.2.0/24\n"
            (out / "meta.txt").write_bytes(previous)
            errors = io.StringIO()
            with ExitStack() as stack:
                stack.enter_context(patch.object(updater, "OUT_DIR", out))
                stack.enter_context(patch.object(updater, "SOURCES", [meta, other]))
                stack.enter_context(redirect_stdout(io.StringIO()))
                stack.enter_context(redirect_stderr(errors))
                self.assertEqual(updater.main(), 1)
            self.assertEqual((out / "meta.txt").read_bytes(), previous)
            self.assertEqual((out / "other.txt").read_text(), "203.0.113.0/24\n")
            ranges = (out / "vpn.txt").read_text().splitlines()
            self.assertEqual(ranges, ["192.0.2.0/24", "203.0.113.0/24"])
            script = (out / "vpn.rsc").read_text()
            self.assertIn("192.0.2.0/24", script)
            self.assertIn("203.0.113.0/24", script)
            self.assertNotIn("198.51.100.0/24", script)
            self.assertIn("failed sources: meta", errors.getvalue())
        self.assertEqual(self.sleep.call_args_list, [call(1), call(2)])
        urls = [attempt.args[0].full_url for attempt in self.urlopen.call_args_list]
        resources = [parse_qs(urlsplit(url).query)["resource"][0] for url in urls[:-1]]
        self.assertEqual(resources, ["AS32934", "AS63293", "AS63293", "AS63293"])
        self.assertEqual(urls[-1], URL)


if __name__ == "__main__":
    unittest.main()
