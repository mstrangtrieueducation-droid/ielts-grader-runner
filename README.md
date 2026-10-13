# IELTS Speaking runner

Generic IELTS Speaking grading code on standard GitHub-hosted runners. Writing is excluded.

Only code is public. Credentials, classroom configuration, approved lesson rubrics, recordings, student names and feedback remain private. The workflow never uploads artifacts, caches student data or prints individual results.

## Configuration

Repository Secrets:

- `GEMINI_KEY_IELTS_SPEAKING`: the existing dedicated Speaking API key.
- `GOOGLE_SERVICE_ACCOUNT_JSON`: the existing authorized service account JSON.
- `IELTS_RUNNER_CONFIG_GZIP_B64`: gzip/base64 private runtime configuration, including the approved repository identity and native source/target mapping.
- `IELTS_SPEAKING_BAREM_GZIP_B64`: gzip/base64 approved supplemental Speaking rubric catalog.

Keep `SPEAKING_ENABLED=false` until the previous Windows and hosted writers have stopped and released their queue lease. Set it to `true` only after audit succeeds.

## Run

Open Actions → **Grade IELTS Pipeline** → Run workflow.

- `validate`: tests only; no provider calls or Sheet writes.
- `audit`: verifies credentials/model and reads queue counts; no grading.
- `grade`: processes eligible ungraded audio and writes verified feedback to the original private Sheets.

The schedule runs every 10 minutes, with one writer. Scheduling can be delayed by GitHub; it is not a realtime guarantee. Paid/uncertain results are checkpointed and are not regenerated automatically. Existing feedback, old parent hashes, lesson mapping and approved rubric rules are preserved.

Node.js 24 is required. `python run.py` is an optional standard-library launcher with the same environment variables. There are no Python third-party dependencies for Speaking.

Public standard GitHub runners have free minutes; per-job, concurrency, API quotas and Gemini charges still apply. A green validation run does not mean student work was graded: read the run summary's returned-result counter.

Never commit secrets, configuration JSON, student media, feedback or the `.runtime` directory. Run only the trusted default branch. The workflow has read-only repository permissions and no pull-request trigger.
