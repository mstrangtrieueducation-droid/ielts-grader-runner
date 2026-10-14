import assert from 'node:assert/strict';
import {sourceInMasterScope,masterScopeAllowsJob} from './master-submission-scope.mjs';
import {automaticEligible,mayResumeSaved} from './automatic-authorization.mjs';
import {createMasterSweep} from './master-cross-class-sweep.mjs';
import {restoreSpeakingCache} from './master-native-sweep.mjs';
import {installMasterScoreProtection} from './master-kids-sweep.mjs';
for(const s of [{time:'31/08/2026 23:59:59'},{time:'2026-08-31T16:59:59Z'},{at:'2026-08-01T10:00:00Z'},{time:''},{time:'not a date'},{}])assert.equal(sourceInMasterScope(s),false);
for(const s of [{time:'01/09/2026 00:00:00'},{time:'2026-08-31T17:00:00Z'},{at:'2026-09-01T00:00:00+07:00'},{time:'14/10/2026 05:30 CH'}])assert.equal(sourceInMasterScope(s),true);
const prior=process.env.MASTER_CROSS_CLASS_SWEEP;process.env.MASTER_CROSS_CLASS_SWEEP='true';
try{
 const old={id:'old',status:'READY',receipt:{student:'Fixture',time:'31/08/2026 23:59:59'}},current={...old,id:'current',receipt:{...old.receipt,time:'01/09/2026 00:00:00'}};
 assert.equal(automaticEligible(old),false);assert.equal(automaticEligible(current),true);
 assert.equal(mayResumeSaved({...old,status:'GENERATED',rawId:'paid'}),false);
 assert.equal(masterScopeAllowsJob({...old,teacherApproval:{approved:true,automatic:false}}),false);
 let calls=0;assert.equal(restoreSpeakingCache({}, {job:{...old,rawId:'paid'}},{},{}),false);
 const c={step_:()=>calls++,persist_:()=>calls++};installMasterScoreProtection(c);c.step_(old,2);assert.equal(calls,0);
 const sources=[old.receipt,current.receipt].map((s,i)=>({...s,className:'Fixture',code:'TASK-'+i})),enqueued=[];
 const sweep=createMasterSweep({lane:'kids',classes:[{className:'Fixture'}],entries:sources.map(source=>({source,cls:{className:'Fixture'}})),findJob:()=>null,resolve:()=>({text:''}),hasFeedback:()=>false,enqueue:s=>{enqueued.push(s);return {job:{},row:2};},save:()=>{}});
 assert.equal(sweep.scan(),1);assert.equal(enqueued.length,1);assert.equal(enqueued[0].code,'TASK-1');
}finally{if(prior===undefined)delete process.env.MASTER_CROSS_CLASS_SWEEP;else process.env.MASTER_CROSS_CLASS_SWEEP=prior;}
console.log('PASS September submission boundary, all native timestamp shapes, invalid dates, old paid cache and explicit approval protection; provider calls: 0.');
