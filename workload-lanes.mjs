// Scheduling only. Native source, eligibility, paid history and final-cell guards remain authoritative.
import {sourceIds} from './universal-media.mjs';
export const FAST_BYTES=50_000_000;
export const SERVICE_MS=300*60000;
export const ITEM_MS=10*60000;
export function mediaWorkload(job){
 if(job.rawId||job.gradeId)return {lane:'fast',bytes:0,saved:true};
 const media=(job.media||[]).filter(m=>!m.isReference),files=media.length?media:job.sourceIntake?.files||[];
 const sizes=files.map(m=>Number(m.size??m.bytes));
 const known=sizes.length>0&&sizes.every(n=>Number.isFinite(n)&&n>0),bytes=known?sizes.reduce((n,v)=>n+v,0):null;
 return {lane:known&&bytes<FAST_BYTES?'fast':'heavy',bytes,saved:false};
}
export function workerAccepts(job,slot,{heavyWaiting=true,ownerSlot}={}){if(slot===3&&ownerSlot===3)return true;return slot===3?mediaWorkload(job).lane==='heavy'||!heavyWaiting:slot>=0&&slot<3&&mediaWorkload(job).lane==='fast';}
export const serviceMinutes=(deadline,now=Date.now())=>Math.max(1,(deadline-now)/60000-3);
export function assertDelegatedWork(lane,id){
 if(!process.send||process.env.GITHUB_ACTIONS!=='true'||process.env.GITHUB_REPOSITORY!=='mstrangtrieueducation-droid/'+lane+'-grader-runner'||String(process.ppid)!==process.env.LANE_POOL_PARENT_PID||id!==process.env.LANE_POOL_JOB_ID)throw Error('TRUSTED_OWNED_WORKER_REQUIRED');
}
export function workConflict(a,b){
 const cls=j=>j.cls?.spreadsheetId||j.source?.className;
 // A single worker owns each class transaction; media cannot be used twice concurrently.
 if(cls(a)===cls(b))return true;
 const input=j=>{try{return sourceIds(j.source?.link||j.receipt?.links||'');}catch{return [];}};
 const ids=new Set([...(a.media||[]).filter(m=>!m.isReference).map(m=>m.id),...input(a)]);
 return [...(b.media||[]).filter(m=>!m.isReference).map(m=>m.id),...input(b)].some(id=>ids.has(id));
}
