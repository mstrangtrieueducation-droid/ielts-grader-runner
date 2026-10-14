import {randomUUID} from 'node:crypto';
export const RECOVERY_AUTHORIZATION='teacher-20261013-unblock-cache-v1';
export function authorizeRejectedRequest(job){
 if(job.cacheResetAuthorized!==RECOVERY_AUTHORIZATION||job.cacheResetConsumed||job.rawId||job.providerFailure?.http!==400)return false;
 job.recoveryHistory=(job.recoveryHistory||[]).concat([{at:new Date().toISOString(),reason:'teacher_authorized_new_attempt_after_definite_invalid_request',oldRequests:job.generateRequests||0}]);
 job.cacheResetConsumed=true;
 job.generationAttempt={id:randomUUID(),authorization:RECOVERY_AUTHORIZATION,calls:0};
 job.status='READY';job.error='';job.nextAt=0;
 return true;
}
export function resetAuthorizedCache(job,error){
 if(job.cacheResetAuthorized!==RECOVERY_AUTHORIZATION||job.cacheResetConsumed||!job.rawId)return false;
 const code=String(error.message||error);
 if(code==='SHADOW_AUDIO_NOT_ASSESSABLE')return false;
 job.failedAttempts=(job.failedAttempts||[]).concat([{at:new Date().toISOString(),error:code,rawId:job.rawId,usage:job.usage,verificationUsage:job.verificationUsage,model:job.requestModel,reason:'teacher_authorized_invalid_cache_reset'}]);
 job.cacheResetConsumed=true;
 job.generationAttempt={id:randomUUID(),authorization:RECOVERY_AUTHORIZATION,calls:0};
 for(const key of ['rawId','gradeId','usage','verificationRawId','verificationForRawId','verificationUsage','verificationStarted'])delete job[key];
 job.status='READY';job.error='';job.nextAt=0;
 return true;
}
