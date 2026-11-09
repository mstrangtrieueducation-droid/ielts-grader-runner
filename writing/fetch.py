"""MODE=fetch: download the Drive files named in APPROVE (comma-separated IDs) for an offline trial grading.
The files are encrypted with the bundle key before they leave the runner (see the workflow step)."""
import json, os, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from gapi import Google

out = Path(os.environ["RUNTIME_DIR"]) / "fetch"
out.mkdir(parents=True, exist_ok=True)
g = Google(json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]))
ids = [x.strip() for x in os.environ.get("APPROVE", "").split(",") if re.fullmatch(r"[A-Za-z0-9_-]{20,}", x.strip())]
for i in ids:
    (out / i).write_bytes(g.download(i))
print(f"FETCH: files={len(ids)}")
