import {assertNativeEvidence,refreshNativeIntake} from './native-youtube.mjs';
import {sourceInMasterScope} from './master-submission-scope.mjs';
import {hasSavedResult,hasRequest,preprocessingRecoverable,retryPreparation,isTransient,EMPTY_LINK_NOTICE,YOUTUBE_NOTICE,PREPROCESS_VERSION,universalValidatedRequest} from './universal-media.mjs';

export function installKidsPreprocessing(c,{g,service,isLatest,emit=()=>{}}){
 const oldMeta=c.fileMeta_;c.driveIds_=text=>service.ids(text);
 c.fileMeta_=(id,isReference)=>{
  if(isReference===true)return oldMeta(id,isReference);const m=g.fileMeta(id);
  if(m.nativeYouTube){assertNativeEvidence(m.nativeYouTube,{id});return {id,mime:m.mimeType,size:0,modified:m.modifiedTime,nativeYouTube:m.nativeYouTube};}
  if(m.trashed||!Number(m.size))throw Error('PREFLIGHT_FILE_MISSING_OR_INVALID');
  const mime=/^(audio|video)\//.test(m.mimeType)?m.mimeType:/\.(?:mp4|mov|m4a|mp3|wav|aac|ogg|flac|webm)$/i.test(m.name||'')?'audio/unknown':null;
  if(!mime)throw Error('UNSUPPORTED_MEDIA');return {id,mime,size:Number(m.size),modified:m.modifiedTime};
 };
 function notice(j,row,text){
  if(!sourceInMasterScope(j.receipt)||hasSavedResult(j)||hasRequest(j)||!isLatest(j))return false;
  const cell=c.destination_(j.cls,j.route,j.receipt.student).cell;
  if(cell.getFormula()||cell.getDataValidation()||c.hasFeedback_(cell.getDisplayValue()))return false;
  j.pendingInputNotice={version:PREPROCESS_VERSION,text};c.persist_(j,row);
  cell.setRichTextValue(c.coloredFeedback_(cell,text,null));j.autoNotice=text;j.cell=cell.getA1Notation();j.status='COMPLETED_NEEDS_RESUBMISSION';j.error='';j.nextAt=0;j.inputNoticeVersion=PREPROCESS_VERSION;delete j.pendingInputNotice;c.teacherApprovalSession_?.finish(j);c.persist_(j,row);return true;
 }
 const step=c.step_;c.step_=(j,row,...args)=>{
  if(!sourceInMasterScope(j.receipt))return;
  if(!hasSavedResult(j)&&!hasRequest(j)&&!String(j.receipt?.links||'').trim()&&notice(j,row,EMPTY_LINK_NOTICE))return;
  return step(j,row,...args);
 };
 const handle=c.handleError_;c.handleError_=(j,row,e)=>{
  if(e.message==='YOUTUBE_UNAVAILABLE')e=Error('TRANSIENT_MEDIA_YOUTUBE_OUTPUT_MISSING');
  if(isTransient(e)&&!hasRequest(j)&&!hasSavedResult(j)){j.error=e.message;retryPreparation(j,()=>c.persist_(j,row));return;}
  return handle(j,row,e);
 };
 c.recoverUniversalPreprocessing_=()=>{let recovered=0;for(const {job:j,row}of c.loadJobs_()){
  if(!sourceInMasterScope(j.receipt)||!preprocessingRecoverable(j)||j.preprocessorRecovery===PREPROCESS_VERSION&&j.error!=='GOOGLE_HTTP_429'||!isLatest(j)||Number(j.nextAt)>Date.now())continue;
  j.preprocessHistory=(j.preprocessHistory||[]).concat([{status:j.status,error:j.error,at:new Date().toISOString()}]);j.preprocessorRecovery=PREPROCESS_VERSION;j.status='WAITING_INPUT';j.error='';j.nextAt=0;c.persist_(j,row);recovered++;
 }return {recovered,providerCalls:0};};
 const mediaPart=c.mediaPart_;if(mediaPart)c.mediaPart_=(j,m,save,deadline)=>{if(m.nativeYouTube){const part=service.nativePart(m);refreshNativeIntake(j,m);save();return part;}return mediaPart(j,m,save,deadline);};
 const fetch=c.UrlFetchApp.fetch;c.UrlFetchApp.fetch=(url,options={})=>{
  if(String(url).includes(':generateContent')&&c.activeAudioPayloadJob_)options={...options,payload:universalValidatedRequest(JSON.parse(options.payload),c.activeAudioPayloadJob_)};
  return fetch(url,options);
 };
 emit({event:'UNIVERSAL_PREPROCESSING_INSTALLED',version:PREPROCESS_VERSION,providerCalls:0});
}

export function resumeUncalledPreprocessing(items,{scope=sourceInMasterScope,isLatest,save,readyStatus='READY'}){
 let recovered=0;for(const {job:j,row}of items){
  if(/^IELTS\s*4[0-4]$/i.test(j.source?.className||j.cls?.className||'')||!scope(j.source||j.receipt)||!preprocessingRecoverable(j)||j.preprocessorRecovery===PREPROCESS_VERSION&&j.error!=='GOOGLE_HTTP_429'||!isLatest(j)||Number(j.nextAt)>Date.now())continue;
  j.preprocessHistory=(j.preprocessHistory||[]).concat([{status:j.status,error:j.error,inputId:j.inputId,inputHash:j.inputHash,at:new Date().toISOString()}]);
  j.preprocessorRecovery=PREPROCESS_VERSION;j.status=readyStatus;j.error='';j.nextAt=0;delete j.retryAt;delete j.inputId;delete j.inputHash;save(j,row);recovered++;
 }return {recovered,providerCalls:0};
}
