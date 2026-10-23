import importlib.util
from pathlib import Path
import unittest

p = Path(__file__).with_name('google-sheets-python.py')
spec = importlib.util.spec_from_file_location('python_google', p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class TransportTests(unittest.TestCase):
    def test_only_direct_apis(self):
        for url in ['https://sheets.googleapis.com/v4/spreadsheets/abc/values/A1',
                    'https://www.googleapis.com/drive/v3/files/abc']:
            m.validate_url(url, 'GET')

    def test_never_calls_apps_script_or_ai(self):
        for url in ['https://script.google.com/macros/s/id/exec',
                    'https://script.googleapis.com/v1/scripts/id:run',
                    'https://generativelanguage.googleapis.com/v1/models/abc:generateContent',
                    'https://sheets.googleapis.com.attacker.invalid/v4/spreadsheets/abc',
                    'http://sheets.googleapis.com/v4/spreadsheets/abc',
                    'https://user:pass@sheets.googleapis.com/v4/spreadsheets/abc']:
            with self.assertRaises(ValueError):
                m.validate_url(url, 'GET')

    def test_rejects_user_oauth(self):
        with self.assertRaises(ValueError):
            m.Google({'type': 'authorized_user', 'refresh_token': 'fixture'})

    def test_rejects_redirect(self):
        with self.assertRaises(ValueError):
            m.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://script.google.com/')


if __name__ == '__main__':
    unittest.main()
