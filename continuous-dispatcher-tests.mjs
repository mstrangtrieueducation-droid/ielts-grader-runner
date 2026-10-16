import assert from 'node:assert/strict';import fs from 'node:fs';
import {actionableCount,queueFingerprint,dispatchDecision,watchLane} from './continuous-dispatcher.mjs';
const now=Date.parse('2026-10-16T15:00:00Z'),minute=60000,base={enabled:true,workflow:{state:'active'},runs:[{id:'previous',status:'completed',conclusion:'success',created_at:new Date(now-minute).toISOString(),updated_at:new Date(now-minute).toISOString()}],due:3,now};
process.env.MASTER_CROSS_CLASS_SWEEP='true';
assert.equal(dispatchDecision(base).reason,'eligible_backlog');
for(const status of ['in_progress','queued','pending','waiting','requested'])assert.equal(dispatchDecision({...base,runs:[{status}]}).action,'wait');
assert.equal(dispatchDecision({...base,enabled:false}).action,'stop');assert.equal(dispatchDecision({...base,workflow:{state:'disabled_manually'}}).action,'stop');
assert.equal(dispatchDecision({...base,runs:[{status:'completed',display_title:'Speaking grading enabled=false mode=grade'}]}).action,'stop');
assert.equal(dispatchDecision({...base,lastDispatchAt:now-30000}).reason,'dispatch_visibility_grace');
assert.equal(dispatchDecision({...base,unchangedAfterRun:true}).reason,'unchanged_queue_wait_for_source_scan');
assert.equal(dispatchDecision({...base,unchangedAfterRun:true,now:now+10*minute}).reason,'scan_for_new_submissions');
assert.equal(dispatchDecision({...base,due:0}).action,'wait');assert.equal(dispatchDecision({...base,due:0,runs:[]}).reason,'scan_for_new_submissions');
assert.equal(dispatchDecision({...base,runs:[{status:'completed',conclusion:'failure',updated_at:new Date(now-minute).toISOString()}]}).reason,'infrastructure_backoff');
const j={id:'fixture',mode:'live',status:'QUEUED',source:{at:'2026-10-16T10:00:00Z',name:'Student',className:'IELTS 48',code:'S15'},nextAt:0};
assert.equal(actionableCount([j],now),1);
for(const extra of [{approvedGenerateRequests:1},{generateRequests:1},{generationReservation:{active:true}},{providerResponseReceived:{httpStatus:200}},{failedAttempts:[{rawId:'saved'}]},{previousGradingAttempts:[{apiUsage:{paidRateEquivalentUsd:1}}]},{teacherApprovedHistory:[{oldRequests:1}]},{technicalInputFailure:{code:'missing'}},{presentationResubmissionRequired:true},{mode:'backfill'},{status:'DONE'},{status:'COMPLETED_UNASSESSABLE'},{source:{...j.source,at:'2026-08-31T16:59:59Z'}},{source:{...j.source,className:'IELTS 40'}},{nextAt:now+minute},{retryAt:new Date(now+minute).toISOString()}])assert.equal(actionableCount([{...j,...extra}],now),0,JSON.stringify(extra));
const saved={...j,status:'RETRY',rawId:'saved',approvedGenerateRequests:1};assert.equal(actionableCount([saved],now),1);
assert.equal(actionableCount([{...saved,error:'SPEAKING_RESPONSE_INCOMPLETE'}],now),0);
assert.equal(actionableCount([j,{...j,id:'other',status:'DONE',rawId:'already'}],now),0);
const retry={...j,status:'PENDING_RETRY',approvedGenerateRequests:1,error:'SPEAKING_API_HTTP_429',apiFailure:{httpStatus:429},providerRetry:{policy:'teacher-provider-retry-20261016',phase:'WAITING',nextAt:now,failedRequestCount:1}};
assert.equal(actionableCount([retry],now),1);assert.equal(actionableCount([{...retry,providerRetry:{...retry.providerRetry,nextAt:now+minute}}],now),0);assert.equal(actionableCount([{...retry,rawId:'saved'}],now),0);
assert.equal(queueFingerprint([j,{...j,id:'two'}]),queueFingerprint([{...j,id:'two'},j]));assert.equal(queueFingerprint([j]),queueFingerprint([{...j,updatedAt:'non-semantic'}]));assert.notEqual(queueFingerprint([j]),queueFingerprint([{...j,status:'DONE',rawId:'saved'}]));
const env={GITHUB_ACTIONS:'true',GITHUB_REPOSITORY:'mstrangtrieueducation-droid/ielts-grader-runner',GITHUB_REF_NAME:'main',GITHUB_RUN_ID:'controller',GITHUB_TOKEN:'fixture',GRADING_LANE:'ielts',SPEAKING_ENABLED:'true',WATCH_DURATION_MS:'60001'};
const response=(body,status=200)=>({ok:status<400,status,json:async()=>body});let time=now,posts=[],checks=0,readCount=0;
function fake({active=false,completeAfterPost=false,changed=false,race=false,uncertainPost=false,teacherOff=false,handoverPending=true}={}){
 return async(url,options)=>{assert.equal(new URL(url).hostname,'api.github.com');assert.ok(['GET','POST'].includes(options.method));const path=new URL(url).pathname;
  if(options.method==='POST'){posts.push({path,time,body:JSON.parse(options.body)});if(uncertainPost&&path.endsWith('/grade_ielts.yml/dispatches'))throw Error('NETWORK_UNCERTAIN');return response(null,204);}
  if(path.endsWith('/ielts-grader-runner'))return response({private:false,owner:{login:'mstrangtrieueducation-droid'},default_branch:'main'});
  if(path.endsWith('/grade_ielts.yml'))return response({state:'active'});
  if(path.endsWith('/continuous_dispatch.yml/runs'))return response({workflow_runs:handoverPending?[{id:'controller',status:'in_progress'},{id:'next-controller',status:'pending'}]:[{id:'controller',status:'in_progress'}]});
  if(path.endsWith('/grade_ielts.yml/runs')){checks++;const run=active||race&&checks===2||posts.length&&!completeAfterPost&&!uncertainPost?{id:'writer',status:'in_progress'}:{...base.runs[0],...(teacherOff?{display_title:'Speaking grading enabled=false mode=grade'}:{}),...(posts.length&&completeAfterPost?{id:'next',created_at:new Date(posts[0].time).toISOString()}: {})};return response({workflow_runs:[run]});}
  throw Error('UNEXPECTED_ENDPOINT');
 };
}
const readWork=async()=>{readCount++;return {due:1,fingerprint:'unchanged'};},sleep=async ms=>{assert.equal(ms,30000);time+=ms;},reset=()=>{time=now;posts=[];checks=0;readCount=0;};
await watchLane(env,{fetcher:fake(),now:()=>time,sleep,readWork,emit:()=>{}});assert.equal(posts.length,1);assert.equal(posts[0].body.inputs.mode,'grade');assert.equal(posts[0].body.ref,'main');
reset();await watchLane(env,{fetcher:fake({active:true}),now:()=>time,sleep,readWork,emit:()=>{}});assert.equal(posts.length,0);assert.equal(readCount,0);
reset();await watchLane(env,{fetcher:fake({race:true}),now:()=>time,sleep,readWork,emit:()=>{}});assert.equal(posts.filter(p=>p.path.endsWith('/grade_ielts.yml/dispatches')).length,1);assert.ok(posts[0].time>now);
reset();await watchLane({...env,SPEAKING_ENABLED:'false'},{fetcher:fake(),now:()=>time,sleep,readWork,emit:()=>{}});assert.equal(posts.length,0);assert.equal(readCount,0);
reset();await watchLane(env,{fetcher:fake({teacherOff:true}),now:()=>time,sleep,readWork,emit:()=>{}});assert.equal(posts.length,0);
reset();await watchLane({...env,WATCH_DURATION_MS:String(5*minute)},{fetcher:fake({completeAfterPost:true}),now:()=>time,sleep,readWork,emit:()=>{}});assert.equal(posts.length,1,'Unchanged held/occupied queue must not dispatch every30s');
reset();await watchLane({...env,WATCH_DURATION_MS:String(5*minute)},{fetcher:fake({completeAfterPost:true}),now:()=>time,sleep,readWork:async()=>({due:1,fingerprint:posts.length?'changed':'initial'}),emit:()=>{}});assert.equal(posts.length,2,'Progress should permit next batch without waiting for cron');
reset();await watchLane({...env,WATCH_DURATION_MS:String(minute)},{fetcher:fake({uncertainPost:true}),now:()=>time,sleep,readWork,emit:()=>{}});assert.equal(posts.length,1,'Unknown dispatch outcome retains visibility grace');
reset();await watchLane({...env,WATCH_DURATION_MS:'1'},{fetcher:fake({active:true,handoverPending:false}),now:()=>time,sleep,readWork,emit:()=>{}});assert.equal(posts.length,1);assert.ok(posts[0].path.endsWith('/continuous_dispatch.yml/dispatches'));
reset();await watchLane({...env,WATCH_DURATION_MS:'1'},{fetcher:fake({active:true}),now:()=>time,sleep,readWork,emit:()=>{}});assert.equal(posts.length,0,'Existing pending controller owns handover');
await assert.rejects(()=>watchLane({...env,GITHUB_REPOSITORY:'other/repo'},{readWork}),/UNTRUSTED/);await assert.rejects(()=>watchLane({...env,WATCH_DURATION_MS:'Infinity'},{readWork}),/DURATION/);
const workflow=fs.readFileSync('.github/workflows/continuous_dispatch.yml','utf8'),grade=fs.readFileSync('.github/workflows/grade_ielts.yml','utf8');assert.ok(workflow.includes('actions: write'));assert.ok(workflow.includes('ielts-speaking-continuous-controller'));assert.ok(workflow.includes("vars.SPEAKING_ENABLED == 'true'"));assert.ok(!/GEMINI_KEY|BAREM_GZIP/.test(workflow));assert.ok(!/\bschedule:/.test(grade));assert.ok(grade.includes('group: ielts-speaking-single-writer'));assert.ok(grade.includes('cancel-in-progress: false'));assert.ok(grade.includes('enabled=${{ vars.SPEAKING_ENABLED }}'));
console.log('Speaking controller: one writer, race/visibility/unknown-POST guards, live disabled switch, progress continuation, unchanged-queue cooldown, 10min source scans, 5h handover, paid/raw/archive/retired/Sep1 guards and workflow credential isolation passed;0 provider calls.');
