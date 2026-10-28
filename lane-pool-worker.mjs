import fs from 'node:fs';import path from 'node:path';
import {assertDelegatedWork} from './workload-lanes.mjs';
if(!process.send||!process.env.LANE_POOL_PARENT_PID||process.env.GITHUB_ACTIONS!=='true')throw Error('TRUSTED_POOL_WORKER_REQUIRED');
const root=process.cwd(),config=JSON.parse(process.env.RUNNER_CONFIG),key=process.env.GEMINI_API_KEY,sa=JSON.parse(process.env.GOOGLE_CREDENTIALS);
const {Google}=await import('./google-adapter.mjs');
process.on('message',async m=>{
 if(m.stop){process.disconnect();return;}
 process.env.LANE_POOL_JOB_ID=m.jobId;
 try{
  assertDelegatedWork(m.lane,m.jobId);const google=new Google(sa);let result;
  if(m.lane==='shadowing'){
   const {runShadowing}=await import('./shadowing-runner.mjs');
   result=runShadowing({google,config,key,root,deadline:m.deadline,emit:()=>{},maxJobs:1,maxApiCalls:1,onlySignature:m.jobId,delegated:true});
  }else if(m.lane==='ielts'){
   const {runIelts}=await import('./ielts-runner.mjs');
   result=runIelts({google,config,key,root,deadline:m.deadline,emit:()=>{},maxJobs:1,maxApiCalls:1,onlySignature:m.jobId,delegated:true});
  }else throw Error('POOL_LANE_INVALID');
  process.send({event:'RESULT',jobId:m.jobId,finished:result.finished,paidCalls:result.paidCalls,work:result.work?.find(x=>x.job.id===m.jobId)||null});
 }catch(e){process.send({event:'FAILURE',jobId:m.jobId,code:/^[A-Z0-9_]+$/.test(e.message||'')?e.message:'NATIVE_WORKER_FAILED'});}
});process.send({event:'READY'});
