import fs from 'node:fs';import path from 'node:path';import {fork} from 'node:child_process';
import {stateStore} from './runner-state.mjs';
import {workerAccepts,mediaWorkload,workConflict,ITEM_MS} from './workload-lanes.mjs';
// One hosted coordinator owns the native lease. Children can only process one exact native job.
export async function runLanePool({lane,root,google,config,key,deadline,plan,now=Date.now,spawnWorker=fork,makeLease=stateStore,emit=x=>console.log(JSON.stringify(x)),sleep=ms=>new Promise(r=>setTimeout(r,ms))}){
 const binding=lane==='shadowing'?config.shadowing:config.ielts,table=lane==='shadowing'?'SHADOWING AI':'IELTS SPEAKING AI';
 let finished=0,paidCalls=0,waves=0;
 while(now()<deadline-ITEM_MS-120000){
  // Discovery/recovery is performed only with every child drained and through the original native planner.
  const planned=await plan();const work=planned.work||[];waves++;
  if(!work.length){emit({event:'CONTINUOUS_POOL_IDLE',lane,workers:4,finished,paidCalls});await sleep(Math.min(10*60000,Math.max(0,deadline-now()-ITEM_MS-120000)));continue;}
  const lease=makeLease(google,binding.controlId,lane==='shadowing'?'ShadowingState':'RunnerState');lease.acquire(deadline+60000);
  const waiting=work.slice(),active=new Map(),children=[],deferred=new Map();let lastBeat=0;
  try{
   await new Promise((resolve,reject)=>{
    let stopped=0;
    const schedule=w=>{
     if(!w.connected||active.has(w.pid))return;
     if(w.retire){w.send({stop:true});return;}
     if(now()>=deadline-ITEM_MS-120000){w.send({stop:true});return;}
     const due=waiting.filter(x=>!(Number(x.job.nextAt)>now())&&!(deferred.get(x.job.id)>now()));
     const heavyWaiting=due.some(x=>mediaWorkload(x.job).lane==='heavy');
     const candidate=due.filter(x=>workerAccepts(x.job,w.slot,{heavyWaiting})&&!([...active.values()].some(y=>workConflict(x.job,y.job)))).sort((a,b)=>Number(!!b.job.rawId||!!b.job.gradeId)-Number(!!a.job.rawId||!!a.job.gradeId)||(mediaWorkload(a.job).bytes??Infinity)-(mediaWorkload(b.job).bytes??Infinity))[0];
     if(!candidate){
      if(waiting.length||active.size){setTimeout(()=>schedule(w),1000);return;}
      w.send({stop:true});return;
     }
     waiting.splice(waiting.indexOf(candidate),1);active.set(w.pid,candidate);
     w.send({jobId:candidate.job.id,deadline:Math.min(deadline,now()+ITEM_MS),lane});
    };
    for(let slot=0;slot<4;slot++){
     const w=spawnWorker(path.join(root,'lane-pool-worker.mjs'),[],{cwd:root,env:{...process.env,LANE_POOL_PARENT_PID:String(process.pid),LANE_POOL_SLOT:String(slot)},silent:true});w.slot=slot;children.push(w);
     const file=path.join(root,'private','pool-'+lane+'-'+slot+'.log');fs.mkdirSync(path.dirname(file),{recursive:true});const log=fs.createWriteStream(file,{flags:'a'});w.stdout.pipe(log);w.stderr.pipe(log);
     w.on('message',m=>{try{
      if(m.event==='READY')schedule(w);
      if(m.event==='RESULT'){
       const owned=active.get(w.pid);if(!owned||owned.job.id!==m.jobId)throw Error('WORKER_RESULT_OWNERSHIP_INVALID');
       active.delete(w.pid);finished+=Number(m.finished)||0;paidCalls+=Number(m.paidCalls)||0;
       // Only the native selector may re-admit the exact job. Never reset a request/raw/reservation.
       if(m.work){owned.job=m.work.job;owned.row=m.work.row;deferred.set(owned.job.id,Math.max(now()+5000,Number(owned.job.nextAt)||0));waiting.push(owned);}
       emit({event:'CONTINUOUS_POOL_ITEM_SAVED',lane,worker:slot,finished,paidCalls,waiting:waiting.length,active:active.size});
       schedule(w);for(const other of children)schedule(other);
      }
      if(m.event==='FAILURE'){
       // A child failure never licenses a replacement paid call. Reconcile native durable history next wave.
       active.delete(w.pid);emit({event:'CONTINUOUS_POOL_NATIVE_RECHECK',lane,worker:slot,code:m.code});w.send({stop:true});
      }
     }catch(e){reject(e);}});
     w.on('error',reject);w.on('exit',()=>{active.delete(w.pid);stopped++;if(stopped===4)resolve();});
    }
    const beat=setInterval(()=>{try{lease.heartbeat();lastBeat=now();}catch(e){emit({event:'CONTINUOUS_POOL_LEASE_DRAIN',lane});for(const w of children)w.retire=true;}},60000);
    Promise.all(children.map(w=>new Promise(r=>w.once('exit',r)))).finally(()=>clearInterval(beat));
   });
  }finally{
   for(const w of children)w.retire=true;
   // Drain children; no timeout signal or kill is ever sent to an in-flight request/raw checkpoint.
   for(const w of children)if(w.connected&&!active.has(w.pid))w.send({stop:true});
   await Promise.all(children.filter(w=>w.connected).map(w=>new Promise(r=>w.once('exit',r))));lease.release();
  }
  emit({event:'CONTINUOUS_POOL_WAVE_COMPLETE',lane,waves,finished,paidCalls});
 }
 emit({event:'CONTINUOUS_POOL_SAFE_HOSTED_HANDOVER',lane,finished,paidCalls});return {finished,paidCalls};
}
