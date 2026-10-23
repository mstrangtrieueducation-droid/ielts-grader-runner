"""Service-account Google I/O for IELTS; no Apps Script or user OAuth.

The private JSON protocol is stdin/stdout. Never log the request or credentials.
Only explicit Google Sheets v4 and Drive v3 API routes are accepted.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('GOOGLE_REDIRECT_REJECTED')


def validate_url(url, method):
    p = urllib.parse.urlsplit(url)
    allowed = (p.netloc == 'sheets.googleapis.com' and p.path.startswith('/v4/spreadsheets/')) or (
        p.netloc == 'www.googleapis.com' and p.path.startswith('/drive/v3/files/'))
    if p.scheme != 'https' or not allowed or p.username or p.password or p.fragment:
        raise ValueError('GOOGLE_API_ROUTE_REJECTED')
    if method not in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'):
        raise ValueError('GOOGLE_API_METHOD_REJECTED')


class Google:
    def __init__(self, account, cache_dir=None):
        if account.get('type') != 'service_account' or not account.get('private_key') or not account.get('client_email'):
            raise ValueError('CLEAN_SERVICE_ACCOUNT_REQUIRED')
        if account.get('private_key_id') is None:
            raise ValueError('SERVICE_ACCOUNT_KEY_ID_REQUIRED')
        self.account = account
        self.cache_dir = Path(cache_dir or Path(__file__).parent / '.runtime')
        self.opener = urllib.request.build_opener(NoRedirect())

    def token(self):
        identity = hashlib.sha256((self.account['client_email'] + self.account['private_key_id']).encode()).hexdigest()[:24]
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.cache_dir / ('python-token-' + identity + '.json')
        try:
            cached = json.loads(path.read_text())
            if cached['expires_at'] > time.time() + 120:
                return cached['access_token']
        except (OSError, ValueError, KeyError):
            pass
        encode = lambda value: base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).rstrip(b'=')
        now = int(time.time())
        claims = {'iss': self.account['client_email'], 'aud': 'https://oauth2.googleapis.com/token',
                  'scope': 'https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/drive.readonly',
                  'iat': now, 'exp': now + 3600}
        body = encode({'alg': 'RS256', 'typ': 'JWT'}) + b'.' + encode(claims)
        key = serialization.load_pem_private_key(self.account['private_key'].encode(), password=None)
        signature = key.sign(body, padding.PKCS1v15(), hashes.SHA256())
        assertion = body + b'.' + base64.urlsafe_b64encode(signature).rstrip(b'=')
        data = urllib.parse.urlencode({'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                                     'assertion': assertion.decode()}).encode()
        req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data,
                                     headers={'Content-Type': 'application/x-www-form-urlencoded'})
        with self.opener.open(req, timeout=40) as response:
            result = json.load(response)
        cached = {'access_token': result['access_token'], 'expires_at': now + int(result['expires_in'])}
        tmp = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
        try:
            with tmp.open('x', encoding='utf-8') as stream:
                os.chmod(tmp, 0o600)
                json.dump(cached, stream)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
        return result['access_token']

    def api(self, url, method='GET', data=None):
        validate_url(url, method)
        body = None if data is None else json.dumps(data, ensure_ascii=False).encode()
        req = urllib.request.Request(url, data=body, method=method,
            headers={'Authorization': 'Bearer ' + self.token(), 'Content-Type': 'application/json'})
        # Non-idempotent writes are NEVER replayed after an uncertain outcome.
        # The existing runner performs exact readback/reconciliation.
        with self.opener.open(req, timeout=180) as response:
            return json.loads(response.read() or b'{}')


def main():
    q = json.load(sys.stdin)
    try:
        g = Google(q['account'])
        result = g.api(q['url'], q.get('method', 'GET'), q.get('data'))
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
    except urllib.error.HTTPError as error:
        print(json.dumps({'ok': False, 'code': 'GOOGLE_HTTP_' + str(error.code), 'httpCode': error.code}))
    except Exception as error:
        safe = str(error) if isinstance(error, ValueError) and str(error).isupper() else 'NETWORK_OUTCOME_UNKNOWN'
        print(json.dumps({'ok': False, 'code': safe}))


if __name__ == '__main__':
    main()
