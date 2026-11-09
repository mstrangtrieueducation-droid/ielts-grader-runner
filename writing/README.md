# Writing runner (Claude API)

Separate from the Speaking runner; it does not import or change any Speaking file.

Each cycle (every 3 hours, 07:17–22:17 Vietnam time):
collect finished Claude batches → scan the Form tabs for new or changed submissions → submit one batch
→ write results to the class tracker (only after approval, or automatically when `autoPublish` is on).

Only code is public. The lesson prompts, class configuration and runner state are encrypted
(`bundle.enc`, branch `writing-state`). Logs print counts only.

Secrets: `ANTHROPIC_API_KEY`, `WRITING_BUNDLE_KEY` (and the existing `GOOGLE_SERVICE_ACCOUNT_JSON`).
Without them the workflow only prints "not configured".

`python writing/tests_offline.py` checks the safeguards without network: combining multiple submissions,
no writes before approval, status prefix kept, teacher comments never overwritten, unchanged work not regraded.
