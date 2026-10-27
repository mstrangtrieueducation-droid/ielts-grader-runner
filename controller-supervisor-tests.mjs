import assert from 'node:assert/strict';
import {supervise} from './controller-supervisor.mjs';
const env={GITHUB_ACTIONS:'true',GITHUB_REPOSITORY:'mstrangtrieueducation-droid/kids-grader-runner',GRADING_LANE:'kids'};
let time=0,calls=0,pauses=[];
const result=await supervise(env,{start:async e=>{
 assert(Number(e.WATCH_DURATION_MS)>0&&Number(e.WATCH_DURATION_MS)<=300*60000);
 calls++;if(calls===1)throw Error('network bootstrap');if(calls===2)return {code:1};return {code:0};
},sleep:async ms=>{pauses.push(ms);time+=ms;},now:()=>time,emit:()=>{}});
assert.equal(calls,3);assert.deepEqual(pauses,[10000,10000]);assert(result.handover);
for(const lane of ['kids','shadowing','ielts'])assert((await supervise({...env,GRADING_LANE:lane,GITHUB_REPOSITORY:'mstrangtrieueducation-droid/'+lane+'-grader-runner'},{start:async()=>({code:0}),emit:()=>{}})).handover);
await assert.rejects(()=>supervise({...env,GITHUB_REPOSITORY:'other/kids-grader-runner'}),/UNTRUSTED/);
time=0;calls=0;const bounded=await supervise(env,{start:async()=>{calls++;return {code:1};},sleep:async ms=>{assert.equal(ms,10000);time+=316*60000;},now:()=>time,emit:()=>{}});
assert.equal(calls,1);assert(bounded.awaitScheduledSuccessor);
console.log('Controller bootstrap/exit failures recover after 10 seconds; native handover, repository binding and hosted lifetime retained. 0 provider calls.');
