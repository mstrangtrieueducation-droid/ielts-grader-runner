import {normalizeName} from './master-policy.mjs';
import {hasRequest,hasSavedResult} from './universal-media.mjs';
export const ROSTER_POLICY='teacher-current-roster-20261024';
export function rosterContains(rows,source){
 const name=normalizeName(source.student||source.name);if(!name)throw Error('STUDENT_NAME_MISSING');
 const ielts=/^IELTS\s/i.test(source.className||'');
 return rows.some((r,i)=>i>=(ielts?6:3)&&(!ielts||/^\d+$/.test(String(r[0]))&&Number(r[0])>0)&&[r[1],r[2]].some(v=>normalizeName(v)===name));
}
export function createCurrentRosterCheck(google,classes,{now=Date.now,ttl=Infinity}={}){
 const cache=new Map();
 return (source,{fresh=false}={})=>{
  const cls=classes.find(x=>normalizeName(x.className)===normalizeName(source.className));if(!cls)throw Error('CLASS_NOT_CONFIGURED');
  let saved=cache.get(cls.spreadsheetId);if(fresh||!saved||saved.until<=now()){
   const book=google.book(cls.spreadsheetId),sheet=book.getSheetByName(cls.sheetName||'THEO DÕI TOÀN DIỆN');if(!sheet)throw Error('TARGET_TAB_MISSING');
   const range="'"+sheet.getName().replaceAll("'","''")+"'!A1:C"+sheet.meta.properties.gridProperties.rowCount;
   const result=google.api('https://sheets.googleapis.com/v4/spreadsheets/'+cls.spreadsheetId+'/values/'+encodeURIComponent(range));
   // A failed/empty roster read is a technical hold, never proof of withdrawal.
   if(!Array.isArray(result.values)||!result.values.some((r,i)=>i>=3&&[r[1],r[2]].some(v=>String(v||'').trim())))throw Error('CURRENT_ROSTER_UNAVAILABLE');
   saved={rows:result.values,until:now()+ttl};cache.set(cls.spreadsheetId,saved);
  }
  return rosterContains(saved.rows,source);
 };
}
export function markNotCurrent(job,save){
 const preserve=hasRequest(job)||hasSavedResult(job);
 if(job.rosterEligibility?.version===ROSTER_POLICY&&job.rosterEligibility.state==='NOT_IN_CURRENT_ROSTER'&&(preserve||job.status==='SKIPPED_NOT_IN_CURRENT_ROSTER'))return false;
 job.rosterEligibility={version:ROSTER_POLICY,state:'NOT_IN_CURRENT_ROSTER',checkedAt:new Date().toISOString()};
 // Preserve paid outcomes and uncertain reservations exactly; never reset/retry them.
 if(!preserve){job.status='SKIPPED_NOT_IN_CURRENT_ROSTER';job.error='';job.nextAt=0;}
 save();return false;
}
