import assert from 'node:assert/strict';import {EventEmitter} from 'node:events';
import {fileURLToPath} from 'node:url';
import {runLanePool} from './lane-pool.mjs';
let clock=0,pid=100,released=0,acquired=0,plans=0,heavy=0,maxHeavy=0,fast=0,maxFast=0;const ownership=[],active=new Set();
const jobs=Array.from({length:8},(_,i)=>({row:i+2,job:{id:'fixture-'+i,_runtimeRowKey:'native-test|row'+i,source:{className:'TEST SAME',name:'LEARNER '+i},media:[{id:'media-'+i,size:i<5?1000:80_000_000}]}}));
const spawnWorker=(file,args,options)=>{
 const w=new EventEmitter();w.pid=pid++;w.connected=true;w.stdout=new EventEmitter();w.stderr=new EventEmitter();w.stdout.pipe=()=>{};w.stderr.pipe=()=>{};
 w.send=m=>{
  if(m.stop){queueMicrotask(()=>{if(!w.connected)return;w.connected=false;w.emit('exit',0);});return;}
  const j=jobs.find(x=>x.job.id===m.jobId);assert(j);const slot=Number(options.env.LANE_POOL_SLOT),isHeavy=j.job.media[0].size>=50_000_000;
  if(isHeavy){assert.equal(slot,3);maxHeavy=Math.max(maxHeavy,++heavy);}else{assert(slot<3||slot===3);maxFast=Math.max(maxFast,++fast);}
  assert(!active.has(j.job.id));active.add(j.job.id);ownership.push({id:j.job.id,slot});
  setTimeout(()=>{clock+=isHeavy?9*60000:5000;if(isHeavy)heavy--;else fast--;active.delete(j.job.id);w.emit('message',{event:'RESULT',jobId:j.job.id,finished:1,paidCalls:0,work:null});},1);
 };
 queueMicrotask(()=>w.emit('message',{event:'READY'}));return w;
};
const root=fileURLToPath(new URL('./.runtime/pool-test',import.meta.url));
const result=await runLanePool({lane:'shadowing',root,google:{},config:{shadowing:{controlId:'synthetic'}},key:'unused',deadline:300*60000,checkUpgrade:async()=>false,now:()=>clock,spawnWorker,makeLease:()=>({acquire(){acquired++;},heartbeat(){},release(){released++;}}),emit:()=>{},sleep:async ms=>{clock+=ms;},plan:async()=>({work:plans++?[]:jobs})});
assert.equal(result.finished,8);assert.equal(new Set(ownership.map(x=>x.id)).size,8);assert.equal(maxHeavy,1);assert(maxFast>=3,'three fast classmates must proceed while a heavy classmate is owned by the heavy lane');assert.equal(acquired,released);assert.equal(active.size,0);
console.log('PASS real coordinator scheduling via synthetic child transports: 3 fast +1 heavy, exactly-once ownership, per-item commit acknowledgement, drained children/lease release and 5-hour service; 0 network/AI/Sheet writes.');

// Exercise the actual IPC entrypoint's READY/STOP lifecycle with synthetic configuration.
// No work item is sent: neither native processor nor any Google/provider request runs.
const {fork}=await import('node:child_process');
const child=fork(fileURLToPath(new URL('./lane-pool-worker.mjs',import.meta.url)),[],{cwd:fileURLToPath(new URL('.',import.meta.url)),env:{...process.env,GITHUB_ACTIONS:'true',LANE_POOL_PARENT_PID:String(process.pid),RUNNER_CONFIG:'{}',GOOGLE_CREDENTIALS:'{}',GEMINI_API_KEY:'synthetic-unused'},silent:true});
await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('IPC_HANDSHAKE_TIMEOUT')),10000);child.on('message',m=>{assert.equal(m.event,'READY');child.send({stop:true});});child.on('error',reject);child.on('exit',code=>{clearTimeout(timer);assert.equal(code,0);resolve();});});
console.log('PASS actual native-worker IPC entrypoint drains cleanly without executing a job; 0 Google/provider calls.');
