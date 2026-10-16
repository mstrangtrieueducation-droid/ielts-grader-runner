import {jobInMasterScope} from './master-submission-scope.mjs';

export const SPEAKING_RETRY_POLICY='teacher-provider-retry-20261016';
const retryStates=new Set(['NEEDS_REVIEW','RETRY','PENDING_RETRY']);
// A saved response, including one in an archive, is restored rather than generated again.
export function hasSpeakingResult(value,seen=new Set()){
 if(!value||typeof value!=='object'||seen.has(value))return false;seen.add(value);
 if(value.rawId||value.gradeId||value.resultHash||value.apiUsage||value.usage||value.gradeUsable===true||value.candidates?.length||value.providerResponseReceived?.httpStatus===200)return true;
 return Object.values(value).some(v=>v&&typeof v==='object'&&hasSpeakingResult(v,seen));
}
function failureKind(j){
 if(j.error==='SPEAKING_API_HTTP_429'&&Number(j.apiFailure?.httpStatus)===429)return 'HTTP_429';
 if(j.error==='SPEAKING_API_OUTCOME_UNKNOWN'||j.error==='SPEAKING_INTERNAL_ERROR'&&/NETWORK_OUTCOME_UNKNOWN/.test(j.internalDiagnostic||''))return 'NETWORK_NO_RESPONSE';
 return null;
}
function baseEligible(j){return jobInMasterScope(j)&&!/^IELTS\s*4[0-4]$/i.test(j.source?.className||'')&&j.mode==='live'&&!hasSpeakingResult(j)&&!j.technicalInputFailure&&!j.presentationResubmissionRequired;}
export function speakingRetryAllowed(j,now=Date.now()){
 const p=j.providerRetry;
 return baseEligible(j)&&['PENDING_RETRY','QUEUED','READY','PROCESSING'].includes(j.status)&&(!j.error||!!failureKind(j))&&p?.policy===SPEAKING_RETRY_POLICY&&p.phase==='WAITING'&&p.nextAt<=now&&p.failedRequestCount===Number(j.approvedGenerateRequests||0);
}
export function pendingSpeakingRetry(j){return baseEligible(j)&&j.providerRetry?.policy===SPEAKING_RETRY_POLICY&&j.providerRetry.phase==='WAITING'&&j.status==='PENDING_RETRY'&&!!failureKind(j);}
export function scheduleSpeakingRetry(j,save,now=Date.now(),recover=false){
 if(!baseEligible(j)||!retryStates.has(j.status))return false;
 const kind=failureKind(j);if(!kind)return false;
 const prior=j.providerRetry||{},key=[j.lastAttemptAt||'',j.approvedGenerateRequests||0,j.error].join('|');
 if(recover&&prior.policy===SPEAKING_RETRY_POLICY&&prior.failureKey===key&&prior.phase==='WAITING'){j.status='PENDING_RETRY';j.nextAt=prior.nextAt;j.retryAt=new Date(prior.nextAt).toISOString();return true;}
 const failures=(prior.failures||[]).concat([{at:new Date(now).toISOString(),requestAt:j.lastAttemptAt||null,requestCount:Number(j.approvedGenerateRequests||0),error:j.error,kind,outcomeUnknown:kind==='NETWORK_NO_RESPONSE'}]);
 const delay=Math.max(failures.length===1?60000:120000,Number(j.apiFailure?.retryMs)||0);
 // Past, explicit rejections can resume immediately once their backoff already elapsed.
 const failedAt=recover?Date.parse(j.updatedAt||j.lastAttemptAt||''):now;const nextAt=Math.max(now,Number.isFinite(failedAt)?failedAt+delay:now+delay);
 j.providerRetry={policy:SPEAKING_RETRY_POLICY,phase:'WAITING',failureKey:key,failedRequestCount:Number(j.approvedGenerateRequests||0),nextAt,failures};
 j.status='PENDING_RETRY';j.nextAt=nextAt;j.retryAt=new Date(nextAt).toISOString();save();return true;
}
export function reserveSpeakingRequest(j,save,now=Date.now()){
 if(hasSpeakingResult(j))throw Error('SPEAKING_SAVED_RESULT_NO_RECALL');
 const previous=Number(j.approvedGenerateRequests||0);
 if(previous&&!speakingRetryAllowed(j,now))throw Error('SINGLE_PASS_ALREADY_REQUESTED');
 if(previous)j.providerRetry={...j.providerRetry,phase:'IN_FLIGHT',startedAt:new Date(now).toISOString()};
 j.approvedGenerateRequests=previous+1;save();
}
export function reconcileSpeakingRetries(items,save){
 let pending=0;for(const {job,row}of items)if(scheduleSpeakingRetry(job,()=>save(job,row),Date.now(),true))pending++;
 return {pending,providerCalls:0};
}
export function installSpeakingRetryProcess(c){
 const write=c.isgWrite_;if(write)c.isgWrite_=(job,...args)=>{if(!job.rawId||job.gradeUsable!==true)throw Error('SPEAKING_SUCCESSFUL_RESULT_REQUIRED');return write(job,...args);};
 const process=c.isgProcess_;c.isgProcess_=(table,item)=>{
  const j=item.job,save=()=>c.isgSave_(table,item.row,j);
  if(j.status==='PENDING_RETRY'){
   if(!speakingRetryAllowed(j))return j;
   j.status='QUEUED';save();
  }
  const result=process(table,item);
  if(hasSpeakingResult(j)){if(j.providerRetry?.policy===SPEAKING_RETRY_POLICY){j.providerRetry.phase='RESULT_SAVED';save();}}
  else scheduleSpeakingRetry(j,save);
  return result;
 };
}
export function nextSpeakingRetry(items){
 const times=items.map(x=>x.job||x).filter(pendingSpeakingRetry).map(j=>j.providerRetry.nextAt);
 return times.length?Math.min(...times):null;
}
