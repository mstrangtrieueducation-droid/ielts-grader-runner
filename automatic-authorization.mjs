import {receiptDate,generationSpent} from './master-policy.mjs';
const pending=new Set(['QUEUED','READY','WAITING_MEDIA','WAITING_INPUT','WAITING_TEACHER_APPROVAL','RETRY']);
export function automaticEligible(j,all=[]){
 if(!pending.has(j.status)||j.rawId||j.gradeId||generationSpent(j)||j.approvedGenerateRequests||j.generationAttempt?.calls||j.apiUsage||j.usage||j.technicalInputFailure||j.presentationResubmissionRequired)return false;
 const key=x=>[x.cls?.spreadsheetId||x.source?.className,x.receipt?.student||x.source?.name,x.route?.code||x.source?.code].join('|');
 return !all.some(p=>key(p)===key(j)&&(p.presentationResubmissionRequired||/RESUBMISSION|UNASSESSABLE|CẦN_NỘP_LẠI|NEEDS_RESUBMISSION/.test(p.status)));
}
export function mayResumeSaved(j){return !!j.rawId&&['RETRY','PROCESSING','GRADED','GENERATED','WAITING_MEDIA'].includes(j.status)&&!j.technicalInputFailure;}
export function addAutomaticAuthorizations(session,jobs,controlId,tab,sheetId){
 const all=jobs.map(x=>x.job);let automatic=0;for(const {job:j,row}of jobs.slice().sort((a,b)=>receiptDate(b.job.receipt?.time||b.job.source?.time, new Date(0))-receiptDate(a.job.receipt?.time||a.job.source?.time, new Date(0))))if(automatic<6&&!session.approved.has(j.id)&&(automaticEligible(j,all)||mayResumeSaved(j)))(automatic++,session.approved.set(j.id,{jobId:j.id,automatic:true,authorization:'TEACHER_ENABLED_AUTOMATIC_GRADING',sourceLink:`https://docs.google.com/spreadsheets/d/${controlId}/edit#gid=${sheetId}&range=A${row}:F${row}`}));
 const finish=session.finish;session.finish=j=>{if(session.approved.get(j.id)?.automatic){j.teacherApproval={...j.teacherApproval,approved:false,completedAt:new Date().toISOString()};return;}finish(j);};return session;
}
