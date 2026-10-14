import {receiptDate} from './master-policy.mjs';

// Teacher scope: submission timestamps in Vietnam/Bangkok time, never lesson dates.
export const MASTER_SUBMISSIONS_SINCE='2026-09-01T00:00:00+07:00';
const minimum=Date.parse(MASTER_SUBMISSIONS_SINCE);
export function sourceInMasterScope(source){
 const value=source?.time??source?.at;
 if(value===undefined||value===null||value==='')return false;
 return receiptDate(value,new Date(0)).getTime()>=minimum;
}
export const jobInMasterScope=job=>sourceInMasterScope(job?.receipt||job?.source);
export const masterScopeAllowsJob=job=>process.env.MASTER_CROSS_CLASS_SWEEP!=='true'||jobInMasterScope(job);
