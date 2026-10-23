"""IELTS runner: Python owns Sheets I/O; existing grading engine is preserved."""
import os
import subprocess
import sys
from pathlib import Path

GEMINI_KEY_IELTS_SPEAKING = os.environ.get('GEMINI_KEY_IELTS_SPEAKING')
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')

if __name__ == '__main__':
    os.environ['IELTS_SHEETS_TRANSPORT'] = 'python'
    os.environ['IELTS_PYTHON'] = sys.executable
    completed = subprocess.run(['node', str(Path(__file__).with_name('run-speaking.mjs')), *sys.argv[1:]])
    raise SystemExit(completed.returncode)
