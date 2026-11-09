"""Google Sheets/Drive I/O for the Writing runner (service account, no user OAuth).

Never log request bodies, cell contents or credentials. Only Sheets v4 and Drive v3 routes are allowed.
"""
import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

SCOPES = "https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/drive.readonly"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Drive media downloads may redirect to googleusercontent; allow only that host.
        host = urllib.parse.urlsplit(newurl).netloc
        if host.endswith(".googleusercontent.com"):
            return urllib.request.Request(newurl, headers={"Authorization": req.get_header("Authorization")})
        raise ValueError("GOOGLE_REDIRECT_REJECTED")


def _check(url):
    p = urllib.parse.urlsplit(url)
    ok = (p.netloc == "sheets.googleapis.com" and p.path.startswith("/v4/spreadsheets/")) or (
        p.netloc == "www.googleapis.com" and p.path.startswith("/drive/v3/files"))
    if p.scheme != "https" or not ok:
        raise ValueError("GOOGLE_API_ROUTE_REJECTED")


class Google:
    def __init__(self, account: dict):
        if account.get("type") != "service_account":
            raise ValueError("CLEAN_SERVICE_ACCOUNT_REQUIRED")
        self.account = account
        self._tok = None
        self.opener = urllib.request.build_opener(NoRedirect())

    # ------------------------------------------------------------ auth
    def token(self):
        if self._tok and self._tok[1] > time.time() + 120:
            return self._tok[0]
        enc = lambda v: base64.urlsafe_b64encode(json.dumps(v, separators=(",", ":")).encode()).rstrip(b"=")
        now = int(time.time())
        body = enc({"alg": "RS256", "typ": "JWT"}) + b"." + enc({
            "iss": self.account["client_email"], "aud": "https://oauth2.googleapis.com/token",
            "scope": SCOPES, "iat": now, "exp": now + 3600})
        key = serialization.load_pem_private_key(self.account["private_key"].encode(), password=None)
        sig = key.sign(body, padding.PKCS1v15(), hashes.SHA256())
        data = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                       "assertion": (body + b"." + base64.urlsafe_b64encode(sig).rstrip(b"=")).decode()}).encode()
        req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data,
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with self.opener.open(req, timeout=40) as r:
            res = json.load(r)
        self._tok = (res["access_token"], now + int(res["expires_in"]))
        return self._tok[0]

    def _req(self, url, method="GET", data=None, raw=False, retries=6):
        _check(url)
        body = None if data is None else json.dumps(data, ensure_ascii=False).encode()
        for attempt in range(retries):
            req = urllib.request.Request(url, data=body, method=method, headers={
                "Authorization": "Bearer " + self.token(), "Content-Type": "application/json"})
            try:
                with self.opener.open(req, timeout=300) as r:
                    payload = r.read()
                return payload if raw else json.loads(payload or b"{}")
            except urllib.error.HTTPError as e:
                # Only read-type calls or quota errors are retried; writes are idempotent cell PUTs.
                if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                    time.sleep(20 * (attempt + 1))  # Sheets read quota is per minute
                    continue
                raise RuntimeError(f"GOOGLE_HTTP_{e.code}") from None

    # ------------------------------------------------------------ sheets
    def values(self, sheet_id, rng):
        url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/"
               + urllib.parse.quote(rng, safe="") + "?valueRenderOption=FORMATTED_VALUE")
        return self._req(url).get("values", [])

    def set_cell(self, sheet_id, rng, text):
        url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/"
               + urllib.parse.quote(rng, safe="") + "?valueInputOption=RAW")
        return self._req(url, "PUT", {"range": rng, "values": [[text]]})

    def append_rows(self, sheet_id, tab, rows):
        """Append literal string rows (RAW, never formulas) after the table's last row."""
        rng = f"'{tab}'!A1"
        url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/"
               + urllib.parse.quote(rng, safe="") + ":append?valueInputOption=RAW&insertDataOption=INSERT_ROWS")
        return self._req(url, "POST", {"range": rng, "majorDimension": "ROWS", "values": rows}, retries=1)

    def add_hidden_sheet(self, sheet_id, title, headers):
        self._req(f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}:batchUpdate", "POST",
                  {"requests": [{"addSheet": {"properties": {"title": title, "hidden": True,
                                                             "gridProperties": {"rowCount": 200, "columnCount": len(headers)}}}}]},
                  retries=1)
        rng = f"'{title}'!A1"
        url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/"
               + urllib.parse.quote(rng, safe="") + "?valueInputOption=RAW")
        self._req(url, "PUT", {"range": rng, "values": [headers]})

    def set_row(self, sheet_id, rng, row):
        url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/"
               + urllib.parse.quote(rng, safe="") + "?valueInputOption=RAW")
        return self._req(url, "PUT", {"range": rng, "values": [row]})

    def sheet_titles(self, sheet_id):
        r = self._req(f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}?fields=sheets.properties.title")
        return [x["properties"]["title"] for x in r.get("sheets", [])]

    # ------------------------------------------------------------ drive
    def meta(self, file_id):
        return self._req(f"https://www.googleapis.com/drive/v3/files/{file_id}"
                         "?supportsAllDrives=true&fields=id,name,mimeType,size,md5Checksum,modifiedTime")

    def download(self, file_id):
        return self._req(f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&supportsAllDrives=true",
                         raw=True)

    def search(self, q):
        out, token = [], ""
        while True:
            url = ("https://www.googleapis.com/drive/v3/files?q=" + urllib.parse.quote(q)
                   + "&pageSize=200&supportsAllDrives=true&includeItemsFromAllDrives=true"
                   "&fields=nextPageToken,files(id,name,modifiedTime)" + (f"&pageToken={token}" if token else ""))
            r = self._req(url)
            out += r.get("files", [])
            token = r.get("nextPageToken")
            if not token:
                return out

    def list_folder(self, folder_id):
        out, token = [], ""
        while True:
            q = urllib.parse.quote(f"'{folder_id}' in parents and trashed=false")
            url = (f"https://www.googleapis.com/drive/v3/files?q={q}&pageSize=200&supportsAllDrives=true"
                   "&includeItemsFromAllDrives=true&fields=nextPageToken,files(id,name,mimeType,size,md5Checksum,modifiedTime)"
                   + (f"&pageToken={token}" if token else ""))
            r = self._req(url)
            out += r.get("files", [])
            token = r.get("nextPageToken")
            if not token:
                return out
