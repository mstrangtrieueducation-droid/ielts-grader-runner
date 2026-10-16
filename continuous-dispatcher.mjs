import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {sourceInMasterScope} from './master-submission-scope.mjs';
import {automaticEligible,mayResumeSaved} from './automatic-authorization.mjs';
import {speakingRetryAllowed,hasSpeakingResult} from './speaking-provider-retry.mjs';
const OWNER='mstrangtrieueducation-droid',REPOSITORY=OWNER+'/ielts-grader-runner',MINUTE=60000;
const spent=(j,seen=new Set())=>{
 if(!j||typeof j!=='object'||seen.has(j))return false;seen.add(j);
 if(hasSpeakingResult(j)||j.generateRequests||j.physicalGenerateRequests||j.approvedGenerateRequests||j.masterGenerationReserved||j.runnerGenerationStarted||j.generationReservation||j.singleCallPermanentlyConsumed||j.generationAttempt?.calls)return true;
 return ['previousGradingAttempts','failedAttempts','recoveryHistory','teacherApprovedHistory'].some(k=>(j[k]||[]).some(a=>spent(a,seen)||a.calls||a.previousRequests||a.oldRequests));
};
const asTime=v=>Number(v)||Date.parse(v)||0;
export function actionableCount(jobs,now=Date.now()){
 const taskKey=j=>[j.source?.className,String(j.source?.name||'').normalize('NFC').trim().toUpperCase(),j.source?.code].join('|');
 return jobs.filter(j=>{
  if(!sourceInMasterScope(j.source)||/^IELTS\s*4[0-4]$/i.test(j.source?.className||'')||j.mode!=='live'||j.technicalInputFailure||j.presentationResubmissionRequired)return false;
  if(Math.max(asTime(j.nextAt),asTime(j.retryAt),asTime(j.providerRetry?.nextAt))>now)return false;
  // A truncated paid response must never create a new call or an immediate scan loop.
  if(/RESPONSE_INCOMPLETE|RAW_TRUNCATED|JSON_INVALID|MALFORMED|TRUNCATED/.test(j.error||''))return false;
  if(!j.rawId&&!j.gradeId&&jobs.some(p=>p!==j&&taskKey(p)===taskKey(j)&&hasSpeakingResult(p)))return false;
  if(speakingRetryAllowed(j,now))return true;
  if(j.rawId||j.gradeId)return mayResumeSaved(j)&&!['DONE','COMPLETED_UNASSESSABLE'].includes(j.status);
  return !spent(j)&&automaticEligible(j,jobs);
 }).length;
}
export function queueFingerprint(jobs){
 // Routine retry timestamp refreshes on an unresolved name/file are not progress.
 // Due-time checks above still wake authorized provider retries when they mature.
 const fields=jobs.map(j=>[j.id,j.status,j.error||'',j.rawId||'',j.gradeId||'',j.resultHash||'',j.approvedGenerateRequests||0,j.providerRetry?.phase||'',j.gradeUsable||false]);
 fields.sort((a,b)=>String(a[0]).localeCompare(String(b[0])));
 return createHash('sha256').update(JSON.stringify(fields)).digest('hex');
}
export function dispatchDecision({enabled,workflow,runs,due,unchangedAfterRun=false,lastDispatchAt=0,now=Date.now(),scanEveryMs=10*MINUTE}){
 if(!enabled||workflow.state!=='active')return {action:'stop',reason:'disabled'};
 if(runs.some(r=>r.status!=='completed'))return {action:'wait',reason:'writer_or_successor_exists'};
 if(now-lastDispatchAt<2*MINUTE)return {action:'wait',reason:'dispatch_visibility_grace'};
 const latest=runs[0];
 if(latest?.display_title?.includes('enabled=false'))return {action:'stop',reason:'teacher_disabled_grading'};
 if(latest?.conclusion==='failure'&&now-Date.parse(latest.updated_at)<3*MINUTE)return {action:'wait',reason:'infrastructure_backoff'};
 if(due>0&&!unchangedAfterRun)return {action:'dispatch',reason:'eligible_backlog'};
 if(!latest||now-Date.parse(latest.created_at)>=scanEveryMs)return {action:'dispatch',reason:'scan_for_new_submissions'};
 return {action:'wait',reason:unchangedAfterRun?'unchanged_queue_wait_for_source_scan':'idle_until_next_source_scan'};
}
export async function watchLane(env,{fetcher=fetch,sleep=ms=>new Promise(r=>setTimeout(r,ms)),now=Date.now,readWork,emit=x=>console.log(JSON.stringify(x))}={}){
 if(env.GRADING_LANE!=='ielts'||env.GITHUB_REPOSITORY!==REPOSITORY||env.GITHUB_ACTIONS!=='true'||!env.GITHUB_TOKEN)throw Error('UNTRUSTED_DISPATCH_RUNTIME');
 if(typeof readWork!=='function')throw Error('QUEUE_READER_REQUIRED');
 const base='https://api.github.com/repos/'+REPOSITORY,workflow='grade_ielts.yml',started=now(),duration=Number(env.WATCH_DURATION_MS||5*60*MINUTE),state={lastDispatchAt:0,dispatchFingerprint:null},headers={Authorization:'Bearer '+env.GITHUB_TOKEN,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'};
 if(!Number.isFinite(duration)||duration<=0||duration>5*60*MINUTE)throw Error('WATCH_DURATION_INVALID');
 async function api(url,method='GET',body){const r=await fetcher(base+url,{method,headers,...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(30000)});if(!r.ok)throw Error('DISPATCH_HTTP_'+r.status);return r.status===204?null:r.json();}
 const info=await api('');if(info.private||info.owner?.login!==OWNER||env.GITHUB_REF_NAME!==info.default_branch)throw Error('DISPATCH_REPOSITORY_BINDING_FAILED');
 let failures=0,lastReason='';
 while(now()-started<duration){
  try{
   const wf=await api('/actions/workflows/'+workflow),runs=(await api('/actions/workflows/'+workflow+'/runs?per_page=100&fresh='+now())).workflow_runs;
   const busy=runs.some(r=>r.status!=='completed');
   const work=busy||env.SPEAKING_ENABLED!=='true'||wf.state!=='active'?{due:0,fingerprint:null}:await readWork();
   const unchanged=!!state.dispatchFingerprint&&work.fingerprint===state.dispatchFingerprint;
   const plan=dispatchDecision({enabled:env.SPEAKING_ENABLED==='true',workflow:wf,runs,due:work.due,unchangedAfterRun:unchanged,lastDispatchAt:state.lastDispatchAt,now:now()});
   if(plan.reason!==lastReason){emit({event:'CONTINUOUS_DISPATCH',lane:'ielts',...plan,due:work.due,providerCalls:0});lastReason=plan.reason;}
   if(plan.action==='stop')return plan;
   if(plan.action==='dispatch'){
    // Immediate recheck plus the existing workflow concurrency group protect the writer.
    const active=(await api('/actions/workflows/'+workflow+'/runs?per_page=100&fresh='+now())).workflow_runs.some(r=>r.status!=='completed');
    if(!active){state.lastDispatchAt=now();state.dispatchFingerprint=work.fingerprint;await api('/actions/workflows/'+workflow+'/dispatches','POST',{ref:info.default_branch,inputs:{mode:'grade'}});emit({event:'CONTINUOUS_SUCCESSOR_REQUESTED',lane:'ielts',reason:plan.reason,providerCalls:0});}
   }
   failures=0;
  }catch(e){failures++;emit({event:'CONTINUOUS_CHECK_DEFERRED',lane:'ielts',error:/^[A-Z0-9_]+$/.test(e.message)?e.message:'READ_CHECK_FAILED',consecutiveChecks:failures,providerCalls:0});}
  await sleep(30000);
 }
 if(env.SPEAKING_ENABLED==='true'){
  const wf=await api('/actions/workflows/'+workflow);const runs=(await api('/actions/workflows/'+workflow+'/runs?per_page=100')).workflow_runs;
  if(wf.state==='active'&&!runs[0]?.display_title?.includes('enabled=false')){
   const others=(await api('/actions/workflows/continuous_dispatch.yml/runs?per_page=100')).workflow_runs.filter(r=>String(r.id)!==env.GITHUB_RUN_ID&&r.status!=='completed');
   if(!others.length){await api('/actions/workflows/continuous_dispatch.yml/dispatches','POST',{ref:info.default_branch});emit({event:'CONTINUOUS_WATCH_HANDOVER',lane:'ielts',providerCalls:0});}
  }
 }
 return {action:'handover',providerCalls:0};
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
 try{
  const fs=await import('node:fs'),{gunzipSync}=await import('node:zlib'),{Google}=await import('./google-adapter.mjs'),env=process.env;
  if(env.GITHUB_REPOSITORY!==REPOSITORY||env.GRADING_LANE!=='ielts'||env.GITHUB_ACTIONS!=='true')throw Error('UNTRUSTED_DISPATCH_RUNTIME');
  const config=JSON.parse(gunzipSync(Buffer.from(env.IELTS_RUNNER_CONFIG_GZIP_B64||'','base64'))),sa=JSON.parse(env.GOOGLE_SERVICE_ACCOUNT_JSON||'{}');
  if(config.approvedRepository!==REPOSITORY||config.serviceAccount!==sa.client_email||!config.ielts?.controlId)throw Error('DISPATCH_PRIVATE_BINDING_FAILED');
  process.env.MASTER_CROSS_CLASS_SWEEP='true';const g=new Google(sa);
  const readWork=async()=>{const rows=g.api('https://sheets.googleapis.com/v4/spreadsheets/'+config.ielts.controlId+'/values/'+encodeURIComponent("'IELTS SPEAKING AI'!F2:F5000")).values||[],jobs=[];for(const r of rows)try{jobs.push(JSON.parse(r[0]));}catch{}return {due:actionableCount(jobs),fingerprint:queueFingerprint(jobs)};};
  await watchLane(env,{readWork});
 }catch(e){console.error(JSON.stringify({event:'CONTINUOUS_DISPATCH_FAILED',code:/^[A-Z0-9_]+$/.test(e.message)?e.message:'CONTROLLER_FAILED',providerCalls:0}));process.exitCode=1;}
}
