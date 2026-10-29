// Operational sidecar only: never clears a paid reservation, raw, usage or native status.
export const QUEUE_POLICY='teacher-dead-letter-20261029';
export const COOLDOWN_MS=30*60000, CLAIM_TTL_MS=10*60000;
const transient=/TIMEOUT|TIMED_OUT|TRANSIENT|HTTP_429|HTTP_50[0234]|CONNECTION|NETWORK|SOURCE_INPUT_PENDING/;
const invalid=/PROVIDER_RESPONSE_|STUDENT_MEDIA_NOT_IN_PROVIDER_INPUT|RESPONSE_VISUAL_INPUT_CONTRADICTION|NATIVE_HISTORY_REQUIRES_RECONCILIATION|UNCERTAIN_GENERATION|FAILED_NO_RESULT_SINGLE_CALL_LOCKED|PAID_HISTORY_NO_SAVED_RESULT/;
export function attemptCount(item){return Math.max(Number(item.attempt_count)||0,(item.attempts||[]).filter(a=>['HELD','QUARANTINED'].includes(a.state)||a.failure===true).length);}
export function quarantineReason(item,job={}){
 const error=String(item.error||job.error||'');
 if(invalid.test(error)||job.status==='FAILED_NO_RESULT_SINGLE_CALL_LOCKED')return error||job.status;
 if(item.state==='HELD'&&!transient.test(error))return error||'NATIVE_RECONCILIATION_REQUIRED';
 if(attemptCount(item)>=2&&!job.rawId&&!job.gradeId)return error||'PREPARATION_ATTEMPTS_EXHAUSTED';
 return null;
}
export function isolateItem(item,job,{now=Date.now(),activeRun}={}){
 if(['VERIFIED_WRITTEN','ALREADY_PRESENT','PROTECTED','SKIPPED_NOT_IN_CURRENT_ROSTER','QUARANTINED'].includes(item.state))return false;
 // An active hosted owner, even with an old timestamp, must drain its paid call.
 if(item.state==='CLAIMED'&&item.claim?.runId===activeRun)return false;
 if(item.state==='CLAIMED'&&now-Date.parse(item.locked_at||item.claim?.at||new Date(now).toISOString())<CLAIM_TTL_MS)return false;
 const reason=quarantineReason(item,job);
 if(reason){item.queueQuarantine={policy:QUEUE_POLICY,at:new Date(now).toISOString(),reason,previousState:item.state,rawId:job.rawId||null,gradeId:job.gradeId||null,paidHistoryPreserved:true};item.state='QUARANTINED';item.attempt_count=Math.max(1,attemptCount(item));item.error=reason;item.nextAt=0;return true;}
 if(item.state==='CLAIMED'){item.attempt_count=attemptCount(item)+1;item.expiredClaim={...item.claim,releasedAt:new Date(now).toISOString()};item.state='PENDING_VALIDATION';item.nextAt=0;return true;}
 if(item.error&&transient.test(item.error)&&['RETRY','PENDING_VALIDATION'].includes(item.state)&&!job.rawId&&!job.gradeId){const retryAt=Date.parse(item.attempts?.at(-1)?.at||new Date(now).toISOString())+COOLDOWN_MS;if(Number(item.nextAt)<retryAt){item.nextAt=retryAt;item.queuePriority='back';return true;}}
 return false;
}
export function isolateNativeJobs(entries,save,{now=Date.now()}={}){
 let count=0;
 for(const {job,row} of entries){
  if(job.queueQuarantine)continue;
  const missing=job.status==='READY'&&!job.rawId&&!job.gradeId&&(Number(job.generateRequests)>0||Number(job.physicalGenerateRequests)>0||Number(job.generationAttempt?.calls)>0);
  if(!missing&&!['FAILED_NO_RESULT_SINGLE_CALL_LOCKED','SYSTEM_GRADING_ERROR','NEEDS_REVIEW'].includes(job.status))continue;
  const reason=missing?'PAID_HISTORY_NO_SAVED_RESULT':quarantineReason({state:job.status==='NEEDS_REVIEW'?'PENDING_VALIDATION':'HELD',error:job.error},job);
  if(!reason)continue;
  job.queueQuarantine={policy:QUEUE_POLICY,at:new Date(now).toISOString(),reason,nativeStatus:job.status,paidHistoryPreserved:true};
  job.attempt_count=Math.max(Number(job.attempt_count)||0,1);save(job,row);count++;
 }
 return count;
}
export function deferredAfterResult(job,before,{now=Date.now()}={}){
 const changed=JSON.stringify([job.status,job.rawId,job.gradeId,job.media,job.sourceIntake])!==JSON.stringify([before.status,before.rawId,before.gradeId,before.media,before.sourceIntake]);
 return changed&&!job.error?Math.max(now+5000,Number(job.nextAt)||0):Math.max(now+COOLDOWN_MS,Number(job.nextAt)||0);
}
