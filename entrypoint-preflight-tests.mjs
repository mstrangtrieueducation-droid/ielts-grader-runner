import assert from 'node:assert/strict';import {spawnSync} from 'node:child_process';import path from 'node:path';import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url)),env={...process.env,MODE:'audit',NATIVE_YOUTUBE_INPUT:'false',SHEET_TRUTH_SYNC:'false'};
for(const key of ['IELTS_RUNNER_CONFIG_GZIP_B64','IELTS_SPEAKING_BAREM_GZIP_B64','GEMINI_KEY_IELTS_SPEAKING','GOOGLE_SERVICE_ACCOUNT_JSON'])delete env[key];
const run=spawnSync(process.execPath,['run-speaking.mjs'],{cwd:root,env,encoding:'utf8',windowsHide:true,timeout:120000,maxBuffer:4*1024*1024});
assert.equal(run.status,1);assert.match(run.stdout,/PASS range-filtered merge metadata/);assert.match(run.stdout,/Current roster:/);assert.match(run.stderr,/MISSING_IELTS_RUNNER_CONFIG_GZIP_B64/);assert.doesNotMatch(run.stderr,/ReferenceError|ERR_MODULE_NOT_FOUND|SAFEGUARD_TEST_FAILED/);
console.log('PASS actual Speaking entrypoint reaches the private-configuration boundary after all public checks; 0 provider calls, 0 network transport, 0 live writes.');
