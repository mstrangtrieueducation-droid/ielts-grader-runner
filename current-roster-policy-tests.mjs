import assert from 'node:assert/strict';import {rosterContains,createCurrentRosterCheck,markNotCurrent} from './current-roster-policy.mjs';
import {createMasterSweep} from './master-cross-class-sweep.mjs';
const rows=[['header'],[],[],['1','Học sinh mẫu A','ALPHA'],['2','Người khác','BETA']],source={className:'KIDS 8',student:'ALPHA'};
assert(rosterContains(rows,source));assert(!rosterContains(rows,{...source,student:'ALPHE'}));assert(!rosterContains(rows,{...source,student:'FORMER'}));
let actual=rows,reads=0;const g={book:()=>({getSheetByName:()=>({getName:()=> 'THEO DÕI TOÀN DIỆN',meta:{properties:{gridProperties:{rowCount:50}}}})}),api:()=>{reads++;return {values:actual};}},check=createCurrentRosterCheck(g,[{className:'KIDS 8',spreadsheetId:'fixture'}]);
assert(check(source));assert.equal(reads,1);actual=rows.filter(r=>r[2]!=='ALPHA');assert(!check(source,{fresh:true}));assert.equal(reads,2);
const old={status:'READY',receipt:{...source},nextAt:100,rawId:'paid',generateRequests:1,apiUsage:{tokens:5},generationReservation:{id:'keep'}},before=JSON.stringify(old);markNotCurrent(old,()=>{});assert.equal(JSON.stringify({...old,rosterEligibility:undefined}),before);
const pending={status:'READY',generateRequests:0};markNotCurrent(pending,()=>{});assert.equal(pending.status,'SKIPPED_NOT_IN_CURRENT_ROSTER');assert.equal(pending.generateRequests,0);
actual=[];assert.throws(()=>check(source,{fresh:true}),/CURRENT_ROSTER_UNAVAILABLE/);
assert(rosterContains([[],[],[],[],[],[],['1','Nguyễn Văn A\nNew 20/10/2026','']],{className:'IELTS 50',name:'Nguyễn Văn A'}));
const archived={status:'RETRY',previousGradingAttempts:[{rawId:'retain-archive',generateRequests:1}]};markNotCurrent(archived,()=>{});assert.equal(archived.status,'RETRY');assert.equal(archived.previousGradingAttempts[0].rawId,'retain-archive');
for(const lane of ['kids','shadowing','ielts']){
 const job={id:'removed',status:'READY'},s={className:'KIDS 8',student:'FORMER',name:'FORMER',code:'TASK',time:'2026-10-24T00:00:00+07:00'},cls={className:'KIDS 8',spreadsheetId:'fixture'};let touched=0;
 const sweep=createMasterSweep({google:{},lane,controlId:'fixture',classes:[cls],entries:[{source:s,cls}],findJob:()=>({job,row:2}),isCurrentStudent:()=>false,resolve:()=>{touched++;throw Error('MUST_NOT_RESOLVE_REMOVED');},hasFeedback:()=>false,enqueue:()=>{touched++;throw Error('MUST_NOT_ENQUEUE_REMOVED');},save:()=>{}});
 sweep.scan();assert.equal(sweep.refresh()[0].inactive,1);assert.equal(sweep.refresh()[0].pending,0);assert.equal(sweep.allowsJob(job),false);assert.equal(job.status,'SKIPPED_NOT_IN_CURRENT_ROSTER');assert.equal(touched,0);
}
console.log('Current roster: removed/misspelled names excluded, fresh deletion detected, failed reads held, raw/usage/reservations preserved;0AI/0Sheet writes.');
