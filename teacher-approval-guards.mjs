import {screenGroundingSchema,SCREEN_OUTPUT_INSTRUCTION,compactWebScope} from './screen-grounding.mjs';
import fs from 'node:fs';import path from 'node:path';import {randomUUID} from 'node:crypto';
import {MASTER_TERMINAL,MASTER_MODEL,generationSpent} from './master-policy.mjs';import {STUDENT_VOICE_INSTRUCTION,voiceOrigin,audioDigest} from './student-voice-origin.mjs';
import {SILENT_NOTICE,OLD_FILE_NOTICE,oldGradedSubmission,noSpeech,inspectSilence} from './zero-cost-gates.mjs';
import {request} from './google-adapter.mjs';import {extractStudentAudio} from './student-audio.mjs';import {decodeSavedDraft} from './saved-draft.mjs';
import {STRICT_PRESENTATION_RULE,knownInvalidPresentation,confirmedPresentationMismatch,presentationNotice} from './teacher-presentation-policy.mjs';import {savedFeedbackRich,savedFeedback} from './saved-feedback.mjs';
import {prepareAudioWithRepair,validateAudioPart,assertAudioPayload} from './audio-payload-guard.mjs';
import {COMPLETION_INSTRUCTION,completionSchema,incompleteFeedback} from './content-completion-policy.mjs';
import {PEDAGOGY_INSTRUCTION} from './pedagogical-language.mjs';
export const APPROVAL_HEADER='DUYỆT CHẤM';
export function approvalSession(g,controlId){
 const book=g.book(controlId),sheet=book.getSheetByName('TIẾN ĐỘ CHUNG'),approved=new Map(),pending=new Map();if(!sheet)return {approved,finish:()=>{},flush:()=>{}};
 const range="'TIẾN ĐỘ CHUNG'!I6:K"+sheet.meta.properties.gridProperties.rowCount,rows=g.api('https://sheets.googleapis.com/v4/spreadsheets/'+controlId+'/values/'+encodeURIComponent(range)).values||[];
 if(rows[0]?.[1]!==APPROVAL_HEADER)return {approved,finish:()=>{},flush:()=>{}};
 rows.slice(1).forEach((r,i)=>{if((r[1]===true||r[1]==='TRUE')&&r[2])approved.set(r[2],{jobId:r[2],sourceLink:r[0],progressRow:i+7,progressSheetId:sheet.getSheetId(),progressControlId:controlId});});
 return {approved,finish(j){const a=approved.get(j.id);if(a)pending.set(j.id,a);j.teacherApproval={...j.teacherApproval,approved:false,completedAt:new Date().toISOString()};},flush(){if(!pending.size)return;g.api('https://sheets.googleapis.com/v4/spreadsheets/'+controlId+':batchUpdate','POST',{requests:[...pending.values()].map(a=>({updateCells:{range:{sheetId:a.progressSheetId,startRowIndex:a.progressRow-1,endRowIndex:a.progressRow,startColumnIndex:9,endColumnIndex:10},rows:[{values:[{userEnteredValue:{boolValue:false}}]}],fields:'userEnteredValue'}}))});pending.clear();}};
}
export function acceptTeacherApprovals(jobs,session,controlId,tab,save){
 for(const {job:j,row}of jobs){const a=session.approved.get(j.id);if(!a||!String(a.sourceLink).includes('/'+controlId+'/')||!String(a.sourceLink).includes('A'+row+':F'+row)){if(j.teacherApproval?.approved)j.teacherApproval.approved=false;continue;}
  if(j.teacherApproval?.approved)continue;
  if(a.automatic&&j.rawId){j.teacherApproval={...a,approved:true,acceptedAt:new Date().toISOString(),resumingSavedResult:true};j.nextAt=0;save(j,row);continue;}
  if(MASTER_TERMINAL.has(j.status)||j.status==='DONE'||generationSpent(j)){
   j.teacherApprovedHistory ||= [];j.teacherApprovedHistory.push({at:new Date().toISOString(),rawId:j.rawId,gradeId:j.gradeId,status:j.status,generateRequests:j.generateRequests,usage:j.apiUsage||j.usage,autoNotice:j.autoNotice});
   for(const k of ['rawId','gradeId','pendingFeedback','pendingFeedbackRender','pendingMasterFeedback','pendingMasterReading','generateRequests','approvedGenerateRequests','attempts','attemptsToday','verificationRawId','verificationStarted','masterGenerationReserved','runnerGenerationStarted','generationReservation','previousGradingAttempts','failedAttempts','retryGenerationAuthorized','apiUsage','usage'])delete j[k];
   j.teacherApprovalOverwrite=true;
  }
  j.teacherApproval={...a,approved:true,cycle:randomUUID(),acceptedAt:new Date().toISOString(),before:null};j.status='READY';j.error='';j.nextAt=0;save(j,row);
 }
}
export function auditPreparedPart({g,c,job,m,part,root,ffmpeg}){
 if(m.isReference||!part||m.localSilence)return;
 const cache=path.join(root,'private','cache'),tag=m.id+'-'+c.hash_(m.modified).slice(0,10);let file=['.mp3','.m4a','.flac'].map(ext=>path.join(cache,tag+ext)).find(p=>fs.existsSync(p));
 const auditDir=path.join(root,'private','silence-audit');fs.mkdirSync(auditDir,{recursive:true});
 if(!file&&part.inlineData?.mimeType?.startsWith('audio/')){file=path.join(auditDir,m.id+'.audio');fs.writeFileSync(file,Buffer.from(part.inlineData.data,'base64'));}
 if(!file){const original=path.join(auditDir,m.id+'.original');if(!fs.existsSync(original)){const r=request({url:'https://www.googleapis.com/drive/v3/files/'+m.id+'?alt=media&supportsAllDrives=true',headers:{Authorization:'Bearer '+g.token()},outputFile:original+'.partial',timeoutMs:240000});if(r.getResponseCode()!==200)throw Error('AUDIO_AUDIT_DOWNLOAD_FAILED');fs.renameSync(original+'.partial',original);}file=extractStudentAudio({ffmpeg,input:original,audio:path.join(auditDir,m.id+'.m4a'),flac:path.join(auditDir,m.id+'.flac'),canonicalFormat:'mp3'}).file;}
 m.localSilence=inspectSilence(ffmpeg,file);m.runnerAudio={...m.runnerAudio,sha256:audioDigest(fs.readFileSync(file))};
}
export function installTeacherApprovalGuards(c,{g,root,ffmpeg,session,emit=()=>{}}){
 const originalStep=c.step_,originalGenerate=c.generate_,originalError=c.handleError_,originalSystem=c.kidsSystemInstruction_,hasFeedback=c.hasFeedback_,mediaPart=c.mediaPart_;
 c.kidsSystemInstruction_=()=>originalSystem()+'\n'+STUDENT_VOICE_INSTRUCTION+'\n'+STRICT_PRESENTATION_RULE+'\n'+COMPLETION_INSTRUCTION+'\n'+PEDAGOGY_INSTRUCTION+'\n'+SCREEN_OUTPUT_INSTRUCTION;
 const schema=c.kidsEvidenceSchema_;if(schema)c.kidsEvidenceSchema_=form=>{const s=schema(form);return {...s,properties:{...s.properties,completionCheck:completionSchema,screenGrounding:screenGroundingSchema},required:[...(s.required||[]),'completionCheck','screenGrounding']};};
 c.hasFeedback_=text=>c.approvalActiveOverwrite&&text===c.approvalActiveOverwrite.before?false:hasFeedback(text);
 if(mediaPart)c.mediaPart_=(j,m,save,deadline)=>{const part=prepareAudioWithRepair({job:j,m,prepare:()=>mediaPart(j,m,save,deadline),save,root,g,ffmpeg,emit});if(part){auditPreparedPart({g,c,job:j,m,part,root,ffmpeg});save();}return part;};
 const api=c.api_;if(api)c.api_=(url,key,options)=>{if(String(url).includes(':generateContent')){const j=c.activeAudioPayloadJob_;if(!j)throw Error('SYSTEM_AUDIO_INPUT_NO_ACTIVE_JOB');j.lastPayloadValidation=assertAudioPayload(JSON.parse(options.payload),j);j.physicalGenerateRequests=(j.physicalGenerateRequests||0)+1;}return api(url,key,options);};
 function notice(j,row,text,status,sections=null){const dst=c.destination_(j.cls,j.route,j.receipt.student),cell=dst.cell;if(c.hasFeedback_(cell.getDisplayValue())||cell.getFormula()||cell.getDataValidation()){j.status='SKIPPED_ALREADY_GRADED';c.persist_(j,row);return;}cell.setRichTextValue(sections?savedFeedbackRich(c,cell,text,sections):c.coloredFeedback_(cell,text,null));j.autoNotice=text;j.cell=cell.getA1Notation();j.status=status;j.error='';j.nextAt=0;session.finish(j);c.persist_(j,row);}
 const rejectPresentation=(j,row)=>{const out=presentationNotice(j);j.presentationResubmissionRequired={invalidFileIds:(j.media||[]).filter(m=>!m.isReference).map(m=>m.id),reason:'CONFIRMED_WRONG_PRESENTATION_FORMAT',at:new Date().toISOString()};notice(j,row,out.text,out.status,out.sections);};
 const rejectIncomplete=(j,row)=>{if(!j.rawId)return false;const draft=decodeSavedDraft(c.readArtifact_(j.rawId)),snapshot=c.masterSnapshot_?.(j)||{};if(snapshot.webPracticeScope)j.verifiedWebPracticeScope=compactWebScope(snapshot.webPracticeScope);const out=incompleteFeedback(draft,j,g=>savedFeedback(g,j,'',snapshot));if(!out)return false;notice(j,row,out.text,out.status,out.sections);return true;};
 const oldFile=j=>oldGradedSubmission(j,c.teacherApprovalJobs_||[],p=>{try{return hasFeedback(c.destination_(p.cls,p.route,p.receipt.student).cell.getDisplayValue());}catch{return false;}});
 c.generate_=(j,parts,snapshot)=>{
  if(snapshot?.webPracticeScope)j.verifiedWebPracticeScope=compactWebScope(snapshot.webPracticeScope);
  if(!j.teacherApproval?.approved)throw Error('TEACHER_APPROVAL_REQUIRED');if(j.rawId)return originalGenerate(j,parts,snapshot);
  if(knownInvalidPresentation(j,c.teacherApprovalJobs_))throw Error('PRESENTATION_FORMAT_RESUBMISSION');const old=oldFile(j);if(old)throw Error('LOCAL_OLD_GRADED_FILE');
  const media=(j.media||[]).filter(m=>!m.isReference);if(!media.length)throw Error('SYSTEM_AUDIO_INPUT_MISSING_STUDENT_AUDIO');
  const positions=parts.flatMap((p,i)=>/^(audio|video)\//.test(p.inlineData?.mimeType||p.fileData?.mimeType||'')?[i]:[]);if(positions.length>media.length)throw Error('SYSTEM_AUDIO_INPUT_EXTRA_MEDIA_PARTS');
  const checked=[...parts];for(const [i,m]of media.entries()){
   let part=positions[i]===undefined?null:checked[positions[i]];
   try{validateAudioPart(m,part,{root});}catch(e){if(!c.mediaPart_)throw e;part=c.mediaPart_(j,m,()=>c.persist_(j,c.masterActiveRow),Date.now()+20*60000);if(!part)throw Error('AUDIO_LOCAL_REPAIR_PENDING');}
   if(positions[i]===undefined)checked.push(part);else checked[positions[i]]=part;
  }
  j.lastPayloadValidation=assertAudioPayload({contents:[{parts:checked}]},j);
  const origin=voiceOrigin(checked,j.media||[]);if(origin.allConfirmedPracticeOnly||media.every(m=>m.localSilence?.silent))throw Error('LOCAL_SILENT_AUDIO');
  c.activeAudioPayloadJob_=j;try{return originalGenerate(j,checked,snapshot);}finally{delete c.activeAudioPayloadJob_;}
 };
 c.step_=(j,row,deadline,options)=>{
  if(MASTER_TERMINAL.has(j.status))return;
  if(!j.teacherApproval?.approved){if(!MASTER_TERMINAL.has(j.status)){j.status='WAITING_TEACHER_APPROVAL';j.nextAt=0;c.persist_(j,row);}return;}
  try{const cell=c.destination_(j.cls,j.route,j.receipt.student).cell;if(j.teacherApprovalOverwrite)c.approvalActiveOverwrite={before:cell.getDisplayValue()};if(knownInvalidPresentation(j,c.teacherApprovalJobs_)||j.rawId&&confirmedPresentationMismatch(decodeSavedDraft(c.readArtifact_(j.rawId)),j,c.masterSnapshot_?.(j))){rejectPresentation(j,row);return;}const old=oldFile(j);if(old){notice(j,row,OLD_FILE_NOTICE,'COMPLETED_NEEDS_RESUBMISSION');return;}
   if(j.status==='SYSTEM_AUDIO_ERROR')return;
   if(rejectIncomplete(j,row))return;
   if(!j.rawId&&!generationSpent(j)){if(c.bindPoolJob_&&process.env.GEMINI_API_KEY)c.bindPoolJob_(j,{keyHash:c.hash_(process.env.GEMINI_API_KEY),model:MASTER_MODEL});if(!(j.media||[]).some(m=>!m.isReference)&&c.kidsCostPreflight_){const files=c.kidsCostPreflight_(j);j.media=files.map(m=>({...m,isReference:false}));j.studentFileCount=j.media.length;c.persist_(j,row);}}
   originalStep(j,row,deadline,options);if(MASTER_TERMINAL.has(j.status)){session.finish(j);delete j.teacherApprovalOverwrite;c.persist_(j,row);}}
  catch(e){c.handleError_(j,row,e);}finally{delete c.approvalActiveOverwrite;}
 };
 c.handleError_=(j,row,e)=>{
  emit({event:'ADDITIVE_GUARD_ERROR',id:j.id,error:e.message});
  if(e.message.startsWith('SYSTEM_AUDIO_INPUT_')&&!j.rawId){j.status='SYSTEM_AUDIO_ERROR';j.error=e.message;j.nextAt=0;j.audioPayloadFailure={...j.audioPayloadFailure,at:new Date().toISOString(),error:e.message,providerGenerateRequests:j.physicalGenerateRequests||0};c.persist_(j,row);return;}
  if(e.message==='AUDIO_LOCAL_REPAIR_PENDING'&&!j.rawId){j.status='WAITING_MEDIA';j.error=e.message;j.nextAt=Date.now()+2000;c.persist_(j,row);return;}
  if(/KEY_REMOVED|KEY_(?:PROJECT|BINDING)|POOL_|AUDIO_PAYLOAD_MISSING|AUDIO_(?:AUDIT|SILENCE_PROBE|PROBE|EXTRACTION)_|RUNNER_DISK|GOOGLE_HTTP_|NETWORK_OUTCOME_UNKNOWN/.test(e.message)&&!j.rawId){j.status='RETRY';j.error=e.message;j.nextAt=Date.now()+60000;c.persist_(j,row);return;}
  if(e.message==='TEACHER_APPROVAL_REQUIRED'){j.status='WAITING_TEACHER_APPROVAL';j.nextAt=0;c.persist_(j,row);return;}
  if(['LOCAL_SILENT_AUDIO','AUDIO_NO_STREAM'].includes(e.message)){notice(j,row,SILENT_NOTICE,'COMPLETED_UNASSESSABLE');return;}
  if(e.message==='LOCAL_OLD_GRADED_FILE'){notice(j,row,OLD_FILE_NOTICE,'COMPLETED_NEEDS_RESUBMISSION');return;}
  if(e.message==='PRESENTATION_FORMAT_RESUBMISSION'||j.rawId&&confirmedPresentationMismatch(decodeSavedDraft(c.readArtifact_(j.rawId)),j,c.masterSnapshot_?.(j))){rejectPresentation(j,row);return;}
  if(rejectIncomplete(j,row))return;
  if(j.rawId&&noSpeech(decodeSavedDraft(c.readArtifact_(j.rawId)))&&!decodeSavedDraft(c.readArtifact_(j.rawId)).presentationReadingCheck?.confirmed){notice(j,row,SILENT_NOTICE,'COMPLETED_UNASSESSABLE');return;}
  originalError(j,row,e);
 };
 emit({event:'ADDITIVE_APPROVAL_GUARDS_INSTALLED',approvalHeader:APPROVAL_HEADER,decoderReplaced:false,batchAdapterReplaced:false});
}
