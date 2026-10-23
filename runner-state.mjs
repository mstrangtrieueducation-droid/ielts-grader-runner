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
export function stateStore(google,controlId,sheetName='RunnerState'){
 const b=google.book(controlId),s=b.getSheetByName(sheetName)||b.insertSheet(sheetName);
 const read=()=>{b.cache.clear();return s.getRange('A1:B1').getDisplayValues()[0];};
 const [raw]=read();let initial={};if(raw){try{initial=JSON.parse(raw);}catch{throw Error('RUNNER_STATE_INVALID');}}
 const token=randomUUID();
 return {initial,acquire(until){const [_,leaseRaw]=read();const previous=leaseRaw?JSON.parse(leaseRaw):{};if(previous.until>Date.now()&&!completedLeaseOwner(previous))throw Error('SHARED_RUNNER_BUSY');s.getRange('B1').setValue(JSON.stringify({token,until,...(process.env.GITHUB_RUN_ID?{runId:process.env.GITHUB_RUN_ID}:{})}));const [__,actual]=read();if(JSON.parse(actual||'{}').token!==token)throw Error('SHARED_RUNNER_BUSY');},
  save(properties){const filtered=Object.fromEntries([...properties].filter(([k])=>/^(FLEET_SCAN_|FLEET_WORK_|FLEET_LAST_SCAN|LAST_GENERATE_AT|KIDS_GENERATE_)/.test(k)));s.getRange('A1').setValue(JSON.stringify(filtered));},
  release(){const [_,raw]=read();if(JSON.parse(raw||'{}').token===token)s.getRange('B1').clearContent();}
 };
}
