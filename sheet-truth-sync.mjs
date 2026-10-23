import {canRecheckYouTubeNotice} from './submission-source-policy.mjs';
import {createHash} from 'node:crypto';
import {RichBuilder,Style} from './google-adapter.mjs';
import {sourceInMasterScope} from './master-submission-scope.mjs';
import {hasTeacherReview,receiptOnlyCell,teacherFeedbackPrefix} from './teacher-feedback-state.mjs';
import {SHEET_TRUTH_VERSION,PENDING_BODY,TECHNICAL_BODY,sheetTruthEnabled,isWaitingFeedback,isResubmissionFeedback,sourceTime,sourceTask,mayReopenNotice,sourceInputReason} from './sheet-truth-state.mjs';
export {sheetTruthEnabled,isWaitingFeedback,mayReopenNotice};
const hash=t=>createHash('sha256').update(JSON.stringify(t)).digest('hex');
export function truthNoticeText(source,before,body){
 const at=sourceTime(source);if(!Number.isFinite(at)||at<=0)throw Error('SUBMISSION_TIMESTAMP_REQUIRED');
 const date=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(new Date(at)).replace(',','');
 let prefix=teacherFeedbackPrefix(before,'✅ ĐÃ NỘP '+date+'\n');if(/Lần đầu:|Lần mới:/u.test(prefix))prefix=prefix.replace(/(Lần mới:\s*)\d{1,2}\/\d{1,2}\/\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?/,(_,label)=>label+date);else if(/ĐÃ NỘP/u.test(prefix))prefix=prefix.replace(/\d{1,2}\/\d{1,2}\/\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?/,date);return isWaitingFeedback('— NHẬN XÉT GV —\n'+body)?prefix.trimEnd():prefix+'— NHẬN XÉT GV —\n'+body;
}
export const resubmissionBody=text=>{let body=String(text||'').split(/NHẬN XÉT GV\s*[—–-]*/u).pop().trim();return /^❌\s*CẦN NỘP LẠI/u.test(body)?body:'❌ CẦN NỘP LẠI: '+body;};
export function truthRich(text){const b=new RichBuilder().setText(text),marker=text.indexOf('— NHẬN XÉT GV —'),end=marker<0?0:marker+'— NHẬN XÉT GV —'.length;b.setTextStyle(new Style().setForegroundColor('#0D47A1').build());if(end<text.length)b.setTextStyle(end,text.length,new Style().setForegroundColor(isWaitingFeedback(text)?'#0D47A1':'#C2185B').build());return b.build();}
const protectedCell=cell=>cell.getFormula?.()||cell.getDataValidation?.();
const missingSource=s=>Array.isArray(s?.fileIds)?s.fileIds.length===0:!String(s?.links??s?.link??'').trim();
const spent=j=>!!(j.rawId||j.gradeId||j.apiUsage||j.usage||j.generateRequests||j.approvedGenerateRequests||j.physicalGenerateRequests||j.masterGenerationReserved||j.generationAttempt?.calls||j.providerResponseReceived?.httpStatus===200);
const waitingBody=j=>j.sourceIntake?.reason==='DOWNLOAD_IN_PROGRESS'?PENDING_BODY:spent(j)&&!j.rawId&&!j.gradeId||j.error||j.technicalInputFailure||j.sourceIntake?.state==='pending'?TECHNICAL_BODY:PENDING_BODY;
export function seedSheetTruth({source,cell,job,save,jobs=[],approved=false}){
 if(!sheetTruthEnabled()||!sourceInMasterScope(source)||protectedCell(cell))return {writable:false};
 const before=cell.getDisplayValue(),youtubeRepair=canRecheckYouTubeNotice(job,before),reopen=mayReopenNotice(source,before,jobs,approved);
 if(hasTeacherReview(before)&&!reopen||!receiptOnlyCell(before)&&!isWaitingFeedback(before)&&!reopen)return {writable:false};
 if(reopen&&!spent(job)){job.sheetTruth={...job.sheetTruth,previousSourceIntake:job.sourceIntake,...(youtubeRepair?{youtubeNoticeRepair:'teacher-youtube-download-classification-20261023',previousNoticeResultHash:job.resultHash}: {})};if(youtubeRepair)delete job.resultHash;delete job.sourceIntake;delete job.autoNotice;job.error='';job.nextAt=0;}
 if(reopen){job.sheetTruth={...job.sheetTruth,previousNotice:before,reopenedFor:sourceTime(source),reopenedBy:youtubeRepair?'youtube_download_classification_repair':approved?'teacher_checkbox':'newer_form_timestamp'};}
 if(job.sheetTruth?.reopenedFor&&job.sheetTruth.reopenedFor===sourceTime(source)&&!spent(job)){job.presentationResubmissionRequired=false;job.technicalInputFailure=false;}
 let reason=sourceInputReason(job);if(!spent(job)&&missingSource(source))reason='Bài nộp chưa đính kèm link video/file. Vui lòng kiểm tra và nộp lại link.';
 const held=!reopen&&isResubmissionFeedback(job.autoNotice||'')&&/COMPLETED|CẦN_NỘP_LẠI/.test(job.status||'');
 const body=held?resubmissionBody(job.autoNotice):reason&&!spent(job)?'❌ CẦN NỘP LẠI: '+reason:waitingBody(job);
 const finalNotice=held||!!reason&&!spent(job),text=finalNotice?truthNoticeText(source,before,body):reopen?truthNoticeText(source,before,body):isWaitingFeedback(before)?clearManagedWaitingText(before):before;
 if(before!==text)cell.setRichTextValue(truthRich(text));
 job.sheetTruth={...job.sheetTruth,version:SHEET_TRUTH_VERSION,state:finalNotice?'RESUBMISSION':'PENDING',submissionAt:sourceTime(source),pendingHash:null,actualCellCheckedAt:new Date().toISOString()};
 if(finalNotice){job.autoNotice=text;job.status='COMPLETED_NEEDS_RESUBMISSION';job.error='';job.nextAt=0;job.resultHash=hash(text);}save?.();return {writable:!finalNotice,notice:finalNotice,changed:before!==text};
}
// A saved result may live in immutable prior attempts. Only exact same submission
// identities may be used; a different lesson, older/newer upload, or unknown
// archive identity can never be substituted.
export function recoverArchivedRaw(job){
 if(job.rawId)return false;const identity=sourceTask(job.source||job.receipt),at=sourceTime(job.source||job.receipt),seen=new Set();let found;
 function walk(x){if(!x||typeof x!=='object'||seen.has(x)||found)return;seen.add(x);const s=x.source||x.receipt;if(x.rawId&&s&&sourceTask(s)===identity&&sourceTime(s)===at&&JSON.stringify(s.fileIds||s.links||s.link)===JSON.stringify((job.source||job.receipt).fileIds||(job.source||job.receipt).links||(job.source||job.receipt).link)){found=x;return;}for(const k of ['previousGradingAttempts','failedAttempts','recoveryHistory','teacherApprovedHistory','archives'])for(const v of x[k]||[])walk(v);}
 walk(job);if(!found)return false;job.rawId=found.rawId;job.sheetTruthArchiveRecovery={at:new Date().toISOString(),rawId:found.rawId,providerCalls:0};return true;
}
export function settleSheetTruth({job,resolve,save,emit=()=>{}}){
 if(!sheetTruthEnabled())return;const source=job.source||job.receipt;if(!sourceInMasterScope(source))return;
 try{const cell=resolve(),text=cell.getDisplayValue();if(protectedCell(cell))return;if(hasTeacherReview(text)){if(job.autoNotice===text&&/COMPLETED|CẦN_NỘP_LẠI/.test(job.status||'')){const value=truthNoticeText(source,text,resubmissionBody(text));if(value!==text){cell.setRichTextValue(truthRich(value));job.autoNotice=value;job.resultHash=hash(value);save();}}return;}if(!receiptOnlyCell(text)&&!isWaitingFeedback(text))return;
  const reason=sourceInputReason(job),body=reason&&!spent(job)?'❌ CẦN NỘP LẠI: '+reason:waitingBody(job),value=reason&&!spent(job)?truthNoticeText(source,text,body):isWaitingFeedback(text)?clearManagedWaitingText(text):text;if(value!==text)cell.setRichTextValue(truthRich(value));
  if(reason&&!spent(job)){job.autoNotice=value;job.resultHash=hash(value);job.status='COMPLETED_NEEDS_RESUBMISSION';job.error='';job.nextAt=0;}
  job.sheetTruth={...job.sheetTruth,version:SHEET_TRUTH_VERSION,state:reason&&!spent(job)?'RESUBMISSION':'PENDING',submissionAt:sourceTime(source),pendingHash:null};save();
 }catch(e){emit({event:'SHEET_TRUTH_DELIVERY_DEFERRED',reason:/^[A-Z0-9_]+$/.test(e.message||'')?e.message:'SHEET_UNAVAILABLE',providerCalls:0});}
}

export function clearManagedWaitingText(text){
 if(!isWaitingFeedback(text))return String(text||'');
 return String(text||'').split(/NHẬN XÉT GV\s*[—–-]*/u)[0].replace(/[—–-]+\s*$/u,'').trimEnd();
}
const cleanedClassBooks=new WeakMap();
export function cleanupClassWaiting({google,classes,emit=()=>{}}){
 let seen=cleanedClassBooks.get(google);if(!seen){seen=new Set();cleanedClassBooks.set(google,seen);}let cleaned=0;const failures=[];
 for(const cls of classes){const id=cls.spreadsheetId;if(!id||seen.has(id))continue;
  try{const book=google.book(id),sheet=book.getSheetByName(cls.sheetName||'THEO DÕI TOÀN DIỆN');if(!sheet)throw Error('TARGET_TAB_MISSING');
   let master=book.cache.get(sheet.getName()+'|master');if(!master){google.preloadSource(id,sheet.meta.properties.gridProperties.columnCount,[sheet.getName()]);master=book.cache.get(sheet.getName()+'|master');}
   const cells=master.cells||[];for(let row=0;row<cells.length;row++)for(let col=0;col<(cells[row].values||[]).length;col++){const c=cells[row].values[col],text=c.formattedValue??c.userEnteredValue?.stringValue??'';
    if(!isWaitingFeedback(text)||c.userEnteredValue?.formulaValue||c.dataValidation)continue;
    sheet.getRange(row+1,col+1).setRichTextValue(truthRich(clearManagedWaitingText(text)));cleaned++;if(cleaned%10===0)book.ramBatch?.flush();
   }book.ramBatch?.flush();seen.add(id);
  }catch(e){failures.push({className:cls.className,error:e.message});}
 }emit({event:'CLASS_WAITING_CLEANUP',cleaned,failed:failures.length,providerCalls:0});return {cleaned,failures};
}
