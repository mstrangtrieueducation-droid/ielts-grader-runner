import {RECOVERY_AUTHORIZATION} from './shadowing-cache-policy.mjs';
export const MAX_RETRIES = 0;
const blockedCount=value=>!Number.isSafeInteger(Number(value??0))||Number(value??0)<0||Number(value??0)>MAX_RETRIES;
export function assertShadowSingleCall(job){if(job.generationAttempt){if(job.generationAttempt.authorization!==RECOVERY_AUTHORIZATION||!job.cacheResetConsumed||blockedCount(job.generationAttempt.calls)||job.rawId||job.usage)throw Error('SHADOW_ONE_CALL_LIMIT');return;}if(blockedCount(job.generateRequests)||job.rawId||job.usage||(job.failedAttempts||[]).some(a=>a.rawId||a.usage))throw Error('SHADOW_ONE_CALL_LIMIT');}
