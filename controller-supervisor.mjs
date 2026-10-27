import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';

// Hosted jobs have a hard lifetime. Keep restarting a failed controller within
// that lifetime; its native handover and independent schedule retain ownership.
export async function supervise(env,{start=childEnv=>new Promise((resolve,reject)=>{
 const child=spawn(process.execPath,['continuous-dispatcher.mjs'],{env:childEnv,stdio:'inherit'});
 child.once('error',reject);child.once('exit',(code,signal)=>resolve({code,signal}));
}),sleep=ms=>new Promise(r=>setTimeout(r,ms)),now=Date.now,emit=x=>console.log(JSON.stringify(x))}={}){
 const lane=env.GRADING_LANE;
 if(env.GITHUB_ACTIONS!=='true'||!['kids','shadowing','ielts'].includes(lane)||env.GITHUB_REPOSITORY!=='mstrangtrieueducation-droid/'+lane+'-grader-runner')throw Error('UNTRUSTED_CONTROLLER_SUPERVISOR');
 const deadline=now()+315*60000;let attempts=0;
 while(now()<deadline-60000){
  attempts++;
  try{
   const result=await start({...env,WATCH_DURATION_MS:String(Math.min(300*60000,deadline-now()-60000))});
   if(result.code===0){emit({event:'CONTROLLER_NATIVE_HANDOVER_OR_DISABLED',lane,attempts,providerCalls:0});return {attempts,handover:true};}
   emit({event:'CONTROLLER_RESTART_AFTER_EXIT',lane,attempts,code:result.code,providerCalls:0});
  }catch{emit({event:'CONTROLLER_RESTART_AFTER_START_FAILURE',lane,attempts,providerCalls:0});}
  await sleep(10000);
 }
 emit({event:'CONTROLLER_HOSTED_LIFETIME_REACHED',lane,attempts,providerCalls:0});
 return {attempts,awaitScheduledSuccessor:true};
}
if(process.argv[1]===fileURLToPath(import.meta.url))await supervise(process.env);
