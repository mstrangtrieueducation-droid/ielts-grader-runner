import assert from 'node:assert/strict';
import {preprocessingRecoverable,isTransient,PREPROCESS_VERSION} from './universal-media.mjs';
import {resumeUncalledPreprocessing} from './automatic-preprocessing.mjs';
const base={id:'synthetic-quota',source:{className:'IELTS 99',time:'2026-10-20T00:00:00Z'},status:'PENDING_RETRY',error:'GOOGLE_HTTP_429',preprocessorRecovery:PREPROCESS_VERSION,nextAt:0};
assert(isTransient(Error('GOOGLE_HTTP_429')));assert(!isTransient(Error('SHADOW_GEMINI_HTTP_429')));assert(preprocessingRecoverable(base));
let saved=0;
for(const mode of ['unpaid','raw','historicalRaw','usage','reserved','historicalRequest','future','old','stale']){
 const j=structuredClone(base);if(mode==='raw')j.rawId='saved:fixture';if(mode==='historicalRaw')j.failedAttempts=[{rawId:'saved:archive'}];if(mode==='usage')j.apiUsage={tokens:1};if(mode==='reserved')j.masterGenerationReserved=true;if(mode==='historicalRequest')j.failedAttempts=[{generateRequests:1}];if(mode==='future')j.nextAt=Date.now()+60000;if(mode==='old')j.source.time='2026-08-30T00:00:00Z';
 const out=resumeUncalledPreprocessing([{job:j,row:2}],{isLatest:()=>mode!=='stale',save:()=>saved++});assert.equal(out.recovered,mode==='unpaid'?1:0,mode);if(mode==='unpaid'){assert.equal(j.status,'READY');assert.equal(j.preprocessHistory[0].error,'GOOGLE_HTTP_429');assert.equal(j.error,'');}else assert.equal(j.status,'PENDING_RETRY',mode);
}
assert.equal(saved,1);console.log('PASS unpaid Google data quota requeues after backoff; provider 429, saved/archived responses, paid history, reservations, future/old/stale sources stay protected; 0 AI/0 Sheet writes.');
