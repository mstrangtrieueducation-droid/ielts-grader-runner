import {sourceInMasterScope,masterScopeAllowsJob} from './master-submission-scope.mjs';
import {createMasterSweep} from './master-cross-class-sweep.mjs';
import {masterSweepEnabled} from './master-cross-class-sweep.mjs';
export function installMasterScoreProtection(c){const step=c.step_;c.step_=(j,row,...args)=>{if(masterSweepEnabled()){if(!masterScopeAllowsJob(j))return;try{const cell=c.destination_(j.cls,j.route,j.receipt.student).cell;if(c.hasFeedback_(cell.getDisplayValue())||cell.getFormula()||cell.getDataValidation()){j.status='SKIPPED_ALREADY_GRADED';j.error='';c.persist_(j,row);return;}}catch{/* The normal per-job handler records missing names and columns. */}}return step(j,row,...args);};}
export function prepareKidsMasterSweep(c,cluster,google,{emit=()=>{}}={}){
 const tabs=c.masterSweepTabs_,catalog=c.guideCatalog_(),snapshots=new Map(),routes=new Map(),latest=new Map(),jobs=c.loadJobs_(),byReceipt=new Map();
 const receiptKey=s=>[c.norm_(s.className),s.sourceTab,s.row,c.norm_(s.student),c.norm_(s.code),s.links].join('|');
 for(const item of jobs)byReceipt.set(receiptKey(item.job.receipt),item);
 for(const tab of tabs)for(const s of c.sourceRows_(tab)){
  if(!sourceInMasterScope(s)||!cluster.classes.some(cls=>c.norm_(cls.className)===c.norm_(s.className))||c.retiredTextbookHomework_(s))continue;
  const key=[c.norm_(s.className),tab,c.norm_(s.student),c.norm_(s.code)].join('|'),old=latest.get(key);
  if(!old||Date.parse(s.time)>Date.parse(old.time)||s.time===old.time&&s.row>old.row)latest.set(key,s);
 }
 const clsFor=s=>cluster.classes.find(cls=>c.norm_(cls.className)===c.norm_(s.className));
 const routeFor=s=>{const key=receiptKey(s);if(!routes.has(key))routes.set(key,c.routeForReceipt_(s,catalog));return routes.get(key);};
 const sweep=createMasterSweep({google,lane:'kids',controlId:cluster.controlId,classes:cluster.classes,entries:[...latest.values()].map(source=>({source,cls:clsFor(source)})),findJob:s=>byReceipt.get(receiptKey(s)),
  resolve:(s,j)=>{const cls=clsFor(s);if(!snapshots.has(cls.spreadsheetId))snapshots.set(cls.spreadsheetId,c.targetSnapshot_(cls));const snapshot=snapshots.get(cls.spreadsheetId),route=j?.rawId&&j.contentRouting?j.route:routeFor(s),dst=c.autoTarget_(snapshot,route,s.student);return {...dst,cell:snapshot.sheet.getRange(dst.row,dst.column)};},hasFeedback:text=>c.hasFeedback_(text),readyStatus:'READY',
  enqueue:(s,cls)=>{const route=routeFor(s),job={id:c.autoReceiptId_(cls,route,s),status:'WAITING_INPUT',cls,route,receipt:s,attempts:0,nextAt:0,autoManaged:true,media:[],error:''},row=c.persist_(job);const item={job,row};jobs.push(item);byReceipt.set(receiptKey(s),item);return item;},
  save:(j,row)=>c.persist_(j,row),emit});
 sweep.scan();return sweep;
}
