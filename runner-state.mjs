import {sheetTruthEnabled} from './sheet-truth-state.mjs';
import {completedLeaseOwner} from './completed-lease-owner.mjs';
import fs from 'node:fs';
import {randomUUID} from 'node:crypto';

// One production workflow (GitHub concurrency), one local process, and a shared
// checkpoint guard. Sheets does not offer compare-and-swap: independent writers
// must not bypass the workflow's concurrency group.
export function localGuard(file) {
  try { fs.writeFileSync(file, JSON.stringify({pid:process.pid,at:Date.now()}),{flag:'wx'}); }
  catch(e) { if(e.code!=='EEXIST')throw e; const previous=JSON.parse(fs.readFileSync(file));
    try { process.kill(previous.pid,0); throw Error('LOCAL_RUNNER_BUSY'); }
    catch(e2) { if(e2.message==='LOCAL_RUNNER_BUSY'||e2.code!=='ESRCH')throw e2; }
    fs.unlinkSync(file);fs.writeFileSync(file,JSON.stringify({pid:process.pid,at:Date.now()}),{flag:'wx'});
  }
  return ()=>{try {const p=JSON.parse(fs.readFileSync(file));if(p.pid===process.pid)fs.unlinkSync(file);}catch{}};
}
export const LOCK_TTL_MS=10*60000;
export function stateStore(google,controlId,sheetName='RunnerState'){
 const b=google.book(controlId),s=b.getSheetByName(sheetName)||b.insertSheet(sheetName),truth=sheetTruthEnabled();
 const read=()=>{if(truth)return google.api('https://sheets.googleapis.com/v4/spreadsheets/'+controlId+'/values/'+encodeURIComponent("'"+sheetName+"'!A1:B1")).values?.[0]||[];b.cache.clear();return s.getRange('A1:B1').getDisplayValues()[0];};
 const write=value=>truth?google.api('https://sheets.googleapis.com/v4/spreadsheets/'+controlId+'/values/'+encodeURIComponent("'"+sheetName+"'!B1")+'?valueInputOption=RAW','PUT',{values:[[value]]}):s.getRange('B1').setValue(value);
 const [raw]=read();let initial={};if(raw){try{initial=JSON.parse(raw);}catch{throw Error('RUNNER_STATE_INVALID');}}
 const token=randomUUID();let owned=false,lastBeat=0,beating=false,originalApi,wrappedApi;
 const heartbeat=()=>{if(!truth||!owned||beating||Date.now()-lastBeat<4*60000)return;beating=true;try{const previous=JSON.parse(read()[1]||'{}');if(previous.token!==token)throw Error('PROCESS_LOCK_OWNERSHIP_LOST');write(JSON.stringify({...previous,until:Date.now()+LOCK_TTL_MS,heartbeatAt:Date.now()}));lastBeat=Date.now();}finally{beating=false;}};
 return {initial,heartbeat,acquire(until){const previous=JSON.parse(read()[1]||'{}');if((previous.until>Date.now()||truth&&previous.token&&previous.runId)&&!completedLeaseOwner(previous))throw Error('SHARED_RUNNER_BUSY');write(JSON.stringify({token,until:truth?Date.now()+LOCK_TTL_MS:until,...(truth?{ttlMs:LOCK_TTL_MS,heartbeatAt:Date.now()}:{}),...(process.env.GITHUB_RUN_ID?{runId:process.env.GITHUB_RUN_ID}:{})}));if(JSON.parse(read()[1]||'{}').token!==token)throw Error('SHARED_RUNNER_BUSY');owned=true;lastBeat=Date.now();if(truth){originalApi=google.api;wrappedApi=function(...args){heartbeat();return originalApi.apply(this,args);};google.api=wrappedApi;}},
  save(properties){heartbeat();const filtered=Object.fromEntries([...properties].filter(([k])=>/^(FLEET_SCAN_|FLEET_WORK_|FLEET_LAST_SCAN|LAST_GENERATE_AT|KIDS_GENERATE_)/.test(k)));s.getRange('A1').setValue(JSON.stringify(filtered));},
  release(){if(!owned)return;try{beating=true;const previous=JSON.parse(read()[1]||'{}');if(previous.token===token){if(truth)write('');else s.getRange('B1').clearContent();}}finally{owned=false;beating=false;if(wrappedApi&&google.api===wrappedApi)google.api=originalApi;}}
 };
}
