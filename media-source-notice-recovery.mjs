// Teacher-authorized recovery of source-transport notices only. No pupil IDs,
// receipt matching, grading, source rewriting or generation occurs here.
import {createHash} from 'node:crypto';
import {submissionUrls} from './ingestion-policy.mjs';
import {sourceInMasterScope} from './master-submission-scope.mjs';
import {receiptTimeFromCell,sourceTime} from './sheet-truth-state.mjs';
import {receiptOnlyCell} from './teacher-feedback-state.mjs';
import {recoverArchivedRaw,truthRich,truthNoticeText} from './sheet-truth-sync.mjs';
export const MEDIA_NOTICE_RECOVERY='teacher-shared-media-resolver-20261027';
const hash=x=>createHash('sha256').update(String(x)).digest('hex');
export function mediaSourceText(s){return String(s?.links??s?.link??s?.inputLinks??(s?.fileIds||[]).map(id=>id.startsWith('yt_')?'https://www.youtube.com/watch?v='+id.slice(3):'https://drive.google.com/file/d/'+id+'/view').join(' '));}
export function sourceNoticeBody(text){
 const value=String(text||''),marker=/NHẬN XÉT GV[\t —–-]*/iu.exec(value),start=marker?marker.index+marker[0].length:value.search(/❌\s*CẦN NỘP LẠI/u);
 if(start<0)return null;const body=value.slice(start).trim();
 if(!/^❌\s*CẦN NỘP LẠI\s*[:—–-]\s*Link\b/iu.test(body)||!/không hợp lệ|không đúng định dạng|YouTube.*(?:riêng tư|quyền xem)/iu.test(body)||/Chất lượng|Overall|\bBand\b|\d+\s*%|\d(?:\.\d)?\s*\/\s*9/iu.test(body))return null;
 const prefix=value.slice(0,start).trimEnd();if(!receiptOnlyCell(prefix))return null;
 return {body,prefix,hash:hash(value)};
}
function evidence(x,seen=new Set()){
 if(!x||typeof x!=='object'||seen.has(x))return {paid:false,saved:false};seen.add(x);
 let paid=!!(Number(x.generateRequests||x.approvedGenerateRequests||x.physicalGenerateRequests||0)>0||x.masterGenerationReserved||x.runnerGenerationStarted||x.generationReservation||x.generationAttempt?.calls||x.apiUsage||x.usage||x.providerResponseReceived?.httpStatus===200);
 let saved=!!(x.rawId||x.gradeId||x.verificationRawId||x.verificationUsage||x.gradeUsable||x.candidates?.length||x.resultHash&&!sourceNoticeBody(x.autoNotice||''));
 for(const value of Object.values(x))if(value&&typeof value==='object'){const e=evidence(value,seen);paid ||= e.paid;saved ||= e.saved;}
 return {paid,saved};
}
export function repairMediaSourceNotice({source,existing,cell,service,metadata,create,save,readyStatus='READY',freshStatus='READY'}){
 if(!service||!cell||!sourceInMasterScope(source)||cell.getFormula?.()||cell.getDataValidation?.())return {recovered:false};
 const before=cell.getDisplayValue(),notice=sourceNoticeBody(before);if(!notice)return {recovered:false};
 if(receiptTimeFromCell(before)>sourceTime(source)+1000)return {recovered:false,held:'NEWER_RECEIPT_ON_SHEET'};
 const original=existing?.job;
 if(original?.presentationResubmissionRequired||original?.sourceIntake?.reason==='YOUTUBE_PRIVATE_CONFIRMED')return {recovered:false};
 if(original){const e=evidence(original);if(e.paid&&!e.saved)return {recovered:false,held:'UNCERTAIN_PAID_HISTORY'};}
 const text=mediaSourceText(source),urls=submissionUrls(text);
 try{
  const ids=service.ids(text);if(!ids.length)return {recovered:false};
  const metas=ids.map(id=>metadata(id));
  const advanced=service.resolutionInfo?.(text)?.hasFolder||urls.length>1||urls.some(x=>/\/folders\/|(?:youtu\.be|youtube\.com)\//i.test(x))||ids.length>1||metas.some(m=>Number(m.size)>100*1024*1024)||original?.media?.some(m=>m.mime==='application/vnd.google-apps.folder');
  if(!advanced)return {recovered:false};
  if(metas.some(m=>m.trashed||!m.nativeYouTube&&(!(Number(m.size)>0)||!(/^(audio|video)\//.test(m.mimeType||m.mime||'')||/\.(?:mp4|mov|m4a|mp3|wav|aac|ogg|flac|webm|avi|mkv)$/i.test(m.name||'')))))return {recovered:false};
  if(cell.getDisplayValue()!==before)throw Error('DESTINATION_CHANGED');
  const entry=existing||create(),j=entry.job;
  const e=evidence(j);recoverArchivedRaw(j);
  if(e.saved&&!j.rawId&&!j.gradeId)return {recovered:false,held:'SAVED_HISTORY_REQUIRES_RECONCILIATION'};
  if(e.paid&&!j.rawId&&!j.gradeId)return {recovered:false,held:'UNCERTAIN_PAID_HISTORY'};
  j.mediaResolverRecovery={version:MEDIA_NOTICE_RECOVERY,at:new Date().toISOString(),previousNoticeText:before,previousNoticeHash:notice.hash,sourceTextHash:hash(text),previousStatus:j.status,previousError:j.error||'',previousSourceIntake:j.sourceIntake||null,resolvedFileIds:ids,providerCalls:0,mode:j.rawId||j.gradeId?'SAVED_RESULT_ONLY':'UNCALLED_SOURCE_REPAIR'};
  // Preserve requests, raw, usage and reservations. Only the obsolete source
  // notice and its render hash are retired; they are not an assessment result.
  delete j.autoNotice;if(!j.rawId&&!j.gradeId)delete j.resultHash;delete j.sourceIntake;
  if(!e.paid&&!j.rawId&&!j.gradeId){
   j.mediaResolverRecovery.previousPrepared={inputId:j.inputId,inputHash:j.inputHash,snapshotId:j.snapshotId,sourceHash:j.sourceHash,studentFileCount:j.studentFileCount,media:(j.media||[]).map(m=>({id:m.id,mime:m.mime,size:m.size,modified:m.modified,isReference:m.isReference}))};
   for(const key of ['inputId','inputHash','snapshotId','sourceHash','studentFileCount','studentMediaBytes','forceFiles','media'])delete j[key];
  }

  j.status=j.rawId||j.gradeId?readyStatus:freshStatus;j.error='';j.nextAt=0;delete j.retryAt;
  j.sheetTruth={...j.sheetTruth,state:'PENDING',reopenedBy:MEDIA_NOTICE_RECOVERY,reopenedFor:Date.parse(source.time||source.at)};
  save(j,entry.row);
  const prefix=notice.prefix||truthNoticeText(source,'','');
  cell.setRichTextValue(truthRich(prefix));
  return {recovered:true,entry,providerCalls:0};
 }catch(error){return {recovered:false,deferred:true,error:/^[A-Z0-9_]+$/.test(error.message||'')?error.message:'SOURCE_RESOLVER_RECHECK_FAILED'};}
}
