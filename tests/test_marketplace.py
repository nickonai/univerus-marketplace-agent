"""Offline contract and safety checks; no live credentials or network."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from datetime import datetime

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/univerus-marketplace/scripts/marketplace.py'
spec = importlib.util.spec_from_file_location('marketplace', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ID = '12345678-1234-1234-1234-123456789abc'

class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['marketplace.py', *args]), contextlib.redirect_stdout(output):
            status = m.main()
        return status, output.getvalue()

    def test_routes(self):
        for args, path in [(('access',), '/api/v1/account/access'), (('categories',), '/categories'), (('order', ID), '/orders/' + ID)]:
            with self.subTest(args=args), patch.object(m, 'request_json', return_value={'ok': True}) as request:
                status, output = self.run_cli(*args)
                self.assertEqual(status, 0)
                self.assertEqual(json.loads(output), {'ok': True})
                request.assert_called_once_with(path)

    def test_filters_and_empty_metadata_preserved(self):
        response = {'items': [], 'total': 0, 'page': 2, 'per_page': 100, 'total_pages': 0}
        with patch.object(m, 'request_json', return_value=response) as request:
            status, output = self.run_cli('orders', '--search', ' дизайн ', '--page', '2', '--per-page', '100', '--category-id', ID, '--date-field', 'discovered', '--sort', 'oldest', '--from-at', '2026-10-01T00:00:00Z', '--before-at', '2026-10-02T00:00:00Z')
        self.assertEqual(json.loads(output), response)
        self.assertEqual(status, 0)
        self.assertEqual(request.call_args.args, ('/orders', {'date_field': 'discovered', 'sort': 'oldest', 'page': 2, 'per_page': 100, 'category_id': ID, 'search': 'дизайн', 'from_at': '2026-10-01T00:00:00+00:00', 'before_at': '2026-10-02T00:00:00+00:00'}))

    def test_today_calendar_bounds(self):
        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz):
                return cls(2026, 10, 25, 12, tzinfo=tz)
        with patch.object(m, 'datetime', FixedDateTime), patch.object(m, 'request_json', return_value={}) as request:
            self.run_cli('orders', '--today', '--timezone', 'Europe/Belgrade')
        params = request.call_args.args[1]
        self.assertEqual(params['from_at'], '2026-10-25T00:00:00+02:00')
        self.assertEqual(params['before_at'], '2026-10-26T00:00:00+01:00')

    def test_invalid_inputs_do_not_request(self):
        cases = [('orders', '--from-at', '2026-10-01'), ('orders', '--from-at', '2026-10-02T00:00Z', '--before-at', '2026-10-01T00:00Z'), ('orders', '--page', '0'), ('orders', '--per-page', '101'), ('orders', '--search', ' a '), ('orders', '--category-id', 'bad'), ('order', 'bad'), ('orders', '--today', '--timezone', 'Bad/Zone'), ('orders', '--today', '--from-at', '2026-10-01T00:00Z')]
        for args in cases:
            with self.subTest(args=args), patch.object(m, 'request_json') as request, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                self.run_cli(*args)
            self.assertEqual(error.exception.code, 2)
            request.assert_not_called()

class TransportTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'UNIVERUS_API_KEY': 'test-secret', 'UNIVERUS_API_BASE_URL': 'https://example.test'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_authorization_routes_and_query(self):
        for path, expected in [('/orders', '/api/v1/marketplace/orders'), ('/api/v1/account/access', '/api/v1/account/access')]:
            with patch.object(m, 'build_opener') as opener:
                opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(b'{"items": []}')
                self.assertEqual(m.request_json(path, {'search': 'a b'}), {'items': []})
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(request.get_header('Authorization'), 'Bearer test-secret')
                self.assertEqual(urlsplit(request.full_url).path, expected)
                self.assertEqual(parse_qs(urlsplit(request.full_url).query), {'search': ['a b']})

    def test_missing_key(self):
        os.environ.pop('UNIVERUS_API_KEY')
        with patch.object(m, 'build_opener') as opener, self.assertRaises(ValueError):
            m.request_json('/orders')
        opener.assert_not_called()

    def test_invalid_key_is_not_printed(self):
        with patch.dict(os.environ, {'UNIVERUS_API_KEY': 'test-secret\n'}), patch.object(m, 'build_opener') as opener, self.assertRaises(ValueError) as caught:
            m.request_json('/orders')
        self.assertNotIn('test-secret', str(caught.exception))
        opener.assert_not_called()

    def test_untrusted_base_rejected(self):
        for base in ['http://example.test', 'http://localhost:80@evil.test', 'https://user:pass@example.test', 'https://example.test/path', 'https://example.test?key=x']:
            with self.subTest(base=base), patch.dict(os.environ, {'UNIVERUS_API_BASE_URL': base}), patch.object(m, 'build_opener') as opener, self.assertRaises(ValueError):
                m.request_json('/orders')
            opener.assert_not_called()

    def test_redirects_blocked(self):
        self.assertIsNone(m.NoRedirects().redirect_request(None, None, 302, '', {}, 'https://other.test'))

    def test_safe_errors(self):
        errors = [HTTPError('https://example.test', code, 'test-secret', {}, None) for code in [401, 403, 404, 422, 429, 503]] + [URLError('test-secret'), TimeoutError('test-secret')]
        for error in errors:
            with self.subTest(error=type(error).__name__), patch.object(m, 'build_opener') as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(ValueError) as caught:
                    m.request_json('/orders')
                self.assertNotIn('test-secret', str(caught.exception))

    def test_invalid_json(self):
        with patch.object(m, 'build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value = io.BytesIO(b'not json')
            with self.assertRaisesRegex(ValueError, 'invalid JSON'):
                m.request_json('/orders')

if __name__ == '__main__':
    unittest.main()
