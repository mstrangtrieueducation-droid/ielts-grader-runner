# IELTS Google transport

`python3 run.py` starts the existing Speaking engine with all Sheets/Drive JSON API I/O handled by `google-sheets-python.py`. The local speaking rule library, approved prompts, result validation, receipt signatures and single-writer lease remain unchanged. No remotely deployed Apps Script or restricted-user OAuth is called to read Forms or write results.

`GOOGLE_SERVICE_ACCOUNT_JSON` is the existing clean service-account secret. `IELTS_PYTHON` selects the Python executable for the synchronous adapter. The continuous controller installs the same transport dependency and uses the same path. No additional schedule is needed.

The bridge accepts only direct Sheets v4 / Drive v3 URLs, refuses Apps Script and provider URLs, and never follows redirects. Service-account credentials arrive on stdin, never arguments or public logs. Short-lived access tokens are cached only in the ignored private `.runtime` directory. Existing rate limits and write/readback recovery remain authoritative; the bridge never replays an uncertain non-idempotent write.

Offline transport tests: `python3 test-python-google.py`. A connection test must write only to a dedicated private test tab, with exact readback and zero model calls. Reading/writing Sheets does not exercise or authorize a new grading attempt.
