import {settleSheetTruth} from './sheet-truth-sync.mjs';
import {approvalSession} from './teacher-approval-guards.mjs';
import {enqueueSpeakingMasterRepairs} from './speaking-master-recovery.mjs';
import {installSpeakingMaster,isFoundation,reconcileFoundationFeedback} from './speaking-master-policy.mjs';
import {installSpeakingSourceHeaders} from './speaking-source-headers.mjs';
import {installSpeakingSourceGate} from './submission-source-speaking.mjs';
import {createMediaService,universalValidatedRequest,isTransient,retryPreparation} from './universal-media.mjs';
import {installFeedbackAlignment} from './feedback-alignment.mjs';
import {installSpeakingMedia} from './speaking-media-preprocessing.mjs';
import {PEDAGOGY_INSTRUCTION} from './pedagogical-language.mjs';
import {speakingRetryAllowed,reserveSpeakingRequest,reconcileSpeakingRetries,installSpeakingRetryProcess,nextSpeakingRetry} from './speaking-provider-retry.mjs';
import {ieltsAddressInstruction,installIeltsAddress,withIeltsNoticeAddress} from './ielts-address-policy.mjs';
import {installReturnedSpeakingPolicy,reconcileDeliveredSpeaking} from './speaking-returned-result-policy.mjs';
import {withSpeakingOutputReserve} from './speaking-output-reserve.mjs';
import {sourceInMasterScope,masterScopeAllowsJob} from './master-submission-scope.mjs';
import {masterSweepEnabled} from './master-cross-class-sweep.mjs';
import {prepareNativeSweep,bufferSpeakingQueue,restoreSpeakingCache} from './master-native-sweep.mjs';
import {beginMasterDestinationBatch} from './master-destination-batch.mjs';
import {validateAudioPart,repairAudioLocally,validatedAudioRequest} from './audio-payload-guard.mjs';
import {readSpeakingArtifact} from './artifact-reader.mjs';
import {installApprovedSpeakingBarem} from './speaking-barem-runtime.mjs';
import {verifyCodeFreeze} from './code-freeze.mjs';
import {nativeApprovalSession,nativeResubmission as nativeResubmissionBase,nativeOldFile,OLD_FILE_NOTICE} from './native-approval-guards.mjs';import {inspectSilence,noSpeech,SILENT_NOTICE} from './zero-cost-gates.mjs';import {decodeSavedDraft} from './saved-draft.mjs';
import fs from 'node:fs';import path from 'node:path';import vm from 'node:vm';import {randomUUID} from 'node:crypto';
import {Blob,RichBuilder,Style,request,utilities} from './google-adapter.mjs';
import {stateStore} from './runner-state.mjs';
import {assessmentInstruction} from './assessment-policy.mjs';

const nativeResubmission=withIeltsNoticeAddress(nativeResubmissionBase,SILENT_NOTICE);

export function runIelts({google,config,key,root,deadline,emit,audit=false,maxJobs=8,maxApiCalls=Infinity}){
 installFeedbackAlignment(google);
 verifyCodeFreeze(root);
 if(!config.ielts)return {finished:0,paidCalls:0};
 const binding={...config.ielts,model:'gemini-3.8-flash'};
 if(google.sa.client_email!==config.serviceAccount)throw Error('RUNNER_SERVICE_ACCOUNT_MISMATCH');
 const universalMedia=createMediaService({g:google,root,key});
 const properties=new Map(Object.entries({...binding.properties,IELTS_SPEAKING_CONTROL_ID:binding.controlId,IELTS_SPEAKING_ARTIFACT_FOLDER:binding.artifactFolder,IELTS_SPEAKING_GEMINI_API_KEY:key}));
 const props={getProperty:k=>properties.get(k)||null,setProperty:(k,v)=>{properties.set(k,String(v));return props;},deleteProperty:k=>{properties.delete(k);return props;},getProperties:()=>Object.fromEntries(properties)};
 let activeAudioJob;
 const c=vm.createContext({Date,PropertiesService:{getScriptProperties:()=>props},Utilities:utilities(),SpreadsheetApp:{openById:id=>google.book(id),flush:()=>{},newRichTextValue:()=>new RichBuilder(),newTextStyle:()=>new Style()},DriveApp:{getFileById:id=>google.file(id)},ScriptApp:{getOAuthToken:()=>google.token()},UrlFetchApp:{fetch:(url,o={})=>{let body=o.payload;if(url.includes(':generateContent')){const data=JSON.parse(body);data.systemInstruction={parts:[{text:(isFoundation(activeAudioJob?.source?.code)?'S01 là bài luyện nền tảng khác bài IELTS Speaking: chỉ nhận xét phát âm từ, âm đuôi/trọng âm và câu mẫu, KHÔNG cho điểm %, KHÔNG cho band, không yêu cầu trả lời Part 1 tự phát.':'S02–S31: chấm bốn tiêu chí FC/LR/GRA/PR, band 0–9 bước 0.5.')+' Chỉ chấm âm thanh thực nghe, không nhận xét mắt/tư thế. Khen và sửa tách đúng nhóm; dùng em/Em.'}]};data.systemInstruction.parts.push({text:PEDAGOGY_INSTRUCTION});data.systemInstruction.parts.push({text:ieltsAddressInstruction('IELTS')});body=universalValidatedRequest(data,activeAudioJob);}const response=request({url,method:(o.method||'GET').toUpperCase(),headers:{...(o.headers||{}),...(o.contentType?{'Content-Type':o.contentType}:{})},body});if(url.includes(':generateContent')&&response.getResponseCode()===200&&activeAudioJob)activeAudioJob.providerResponseReceived={httpStatus:200,at:new Date().toISOString()};return response;}}});
 for(const file of fs.readdirSync(path.join(root,'ielts-gas')).filter(f=>f.endsWith('.gs')))vm.runInContext(fs.readFileSync(path.join(root,'ielts-gas',file),'utf8'),c,{filename:file});
 installReturnedSpeakingPolicy(c);
 installIeltsAddress(c);
 if(process.env.SPEAKING_BAREM_CATALOG)installApprovedSpeakingBarem(c,process.env.SPEAKING_BAREM_CATALOG);
 const originalGenerationConfig=c.isgCostGenerationConfig_;c.isgCostGenerationConfig_=model=>({...withSpeakingOutputReserve(originalGenerationConfig(model),model),temperature:0.2});
 const originalPrompt=c.isgPrompt_;c.isgPrompt_=(guide,count)=>assessmentInstruction('IELTS Speaking')+'\n'+originalPrompt(guide,count);
 c.isgLock_=fn=>fn();c.isgLease_=fn=>fn();
 c.isgArtifact_=(label,value)=>{const b=google.book(binding.controlId),s=b.getSheetByName('RunnerArtifacts')||b.insertSheet('RunnerArtifacts');const id='runner:'+randomUUID(),text=JSON.stringify(value),rows=[];for(let i=0;i<text.length;i+=40000)rows.push([id,i/40000,text.slice(i,i+40000)]);s.appendRows(rows);return id;};
 c.isgReadArtifact_=id=>readSpeakingArtifact(google,binding.controlId,id);
 installSpeakingSourceHeaders(c,{emit});
 installSpeakingMaster(c);
 let speakingApproval;const preprocessing=installSpeakingMedia(c,{g:google,service:universalMedia,nativeResubmission,approval:()=>speakingApproval});
 installSpeakingSourceGate(c,{g:google,service:universalMedia,sourceId:vm.runInContext('ISG.source',c)});
 let finished=0,paidCalls=0;
 const table=c.isgTable_();
 if(audit){emit({event:'IELTS_AUDIT',counts:c.isgJobs_(table).reduce((a,x)=>(a[x.job.status]=(a[x.job.status]||0)+1,a),{})});return {finished,paidCalls};}
 const state=stateStore(google,binding.controlId);
 let destinationBatch,masterSweep,queueBuffer;
 try{
  state.acquire(deadline+60000);const manualApproval=approvalSession(google,process.env.TEACHER_APPROVAL_CONTROL_ID||config.masterApprovalControlId||config.clusters?.[0]?.controlId||binding.controlId);
  const nativeConfig=vm.runInContext('ISG',c),sweepClasses=Object.entries(nativeConfig.classes).map(([className,spreadsheetId])=>({className,spreadsheetId,sheetName:nativeConfig.tab}));
  if(masterSweepEnabled()){destinationBatch=beginMasterDestinationBatch(google,sweepClasses,root,{emit});c.isgScopeAllows_=sourceInMasterScope;queueBuffer=bufferSpeakingQueue(c,table,google,binding.controlId);}
  const sourceId=vm.runInContext('ISG.source',c),sourceTabs=vm.runInContext('ISG.sourceTabs',c);google.preloadSource(sourceId,12,sourceTabs);
  const rawRows=c.isgSourceRows_().filter(s=>!masterSweepEnabled()||sourceInMasterScope(s)),latest=c.isgLatest_(rawRows),newest=new Map(latest.map(s=>[s.className+'|'+c.isgName_(s.name)+'|'+s.code,s]));
  const getKey=s=>s.className+'|'+c.isgName_(s.name)+'|'+s.code;
  let old=0;
  for(const item of c.isgJobs_(table))if(!c.speakingSourceScanIncomplete_&&newest.get(getKey(item.job.source))?.signature!==item.job.source.signature&&!['DONE','SKIPPED_EXISTING_FEEDBACK','SKIPPED_OLD_SUBMISSION'].includes(item.job.status)){item.job.status='SKIPPED_OLD_SUBMISSION';delete item.job.retryAt;c.isgSave_(table,item.row,item.job);old++;}
  // Enqueue every valid lesson independently; a new lesson does not supersede another.
  const known=new Set(c.isgJobs_(table).map(x=>x.job.source.signature));
  const scanUntil=masterSweepEnabled()?Infinity:Math.min(deadline-90000,Date.now()+25000);let enqueued=0;
  for(const source of latest){if(Date.now()>scanUntil)break;if(known.has(source.signature)||!c.isgScopeAllows_(source))continue;c.isgEnqueue_(table,source,'live');known.add(source.signature);enqueued++;}
  if(masterSweepEnabled())emit({event:'SPEAKING_MASTER_REPAIRS',...enqueueSpeakingMasterRepairs(c,table,{inScope:masterScopeAllowsJob,isLatest:s=>newest.get(getKey(s))?.signature===s.signature,emit})});
  if(masterSweepEnabled())masterSweep=prepareNativeSweep({google,lane:'ielts',controlId:binding.controlId,classes:sweepClasses,sources:latest,jobs:c.isgJobs_(table),save:(j,row)=>c.isgSave_(table,row,j),readyStatus:'GENERATED',freshStatus:'QUEUED',isApproved:j=>{const a=manualApproval.approved.get(j.id);return !!a&&!a.automatic;},hasFeedback:text=>c.isgHasFeedback_(text),emit,resolve:s=>{const dst=c.isgTarget_(s);return {...dst,cell:dst.range};}});
  queueBuffer?.flush();
  emit({event:'S01_FEEDBACK_FORMAT_RECONCILED',...reconcileFoundationFeedback(c,c.isgJobs_(table),(j,row)=>c.isgSave_(table,row,j))});
  emit({event:'SPEAKING_EXISTING_DELIVERY_RECONCILED',...reconcileDeliveredSpeaking(c,c.isgJobs_(table),(j,row)=>c.isgSave_(table,row,j),sourceInMasterScope)});
  if(masterSweep)try{masterSweep.publish();}catch(e){emit({event:'MASTER_SWEEP_REPORT_ERROR',error:e.message});}
  // Processing performs the full target/name/guideline/file preflight before any API call.
  emit({event:'IELTS_SCAN',enqueued});
  emit({event:'IELTS_DEDUPLICATION',skippedOld:old});
  const fresh=c.isgFresh_;c.isgFresh_=source=>{google.refreshFileMetadata();google.preloadSource(sourceId,12,sourceTabs);google.books.get(vm.runInContext('ISG.classes',c)[source.className])?.cache.clear();return fresh(source);};
  c.isgIsLatestStudent_=source=>c.isgLatest_(c.isgSourceRows_()).some(s=>s.signature===source.signature);
  c.isgBindCostModel_=(job,save)=>{if(job.rawId)return;const model=binding.model||'gemini-2.5-flash';if(model==='gemini-2.5-flash'&&binding.modelAvailable===false)throw Error('SPEAKING_MODEL_UNAVAILABLE');if(job.requestModel!==model){delete job.inputHash;delete job.inputId;}job.requestModel=model;job.costPolicy='native-ielts-quality-v2';save();};
  emit({event:'SPEAKING_PENDING_RETRY',...reconcileSpeakingRetries(c.isgJobs_(table),(j,row)=>c.isgSave_(table,row,j))});
  emit({event:'SPEAKING_PREPROCESS_RECOVERY',...preprocessing.recover(c.isgJobs_(table),(j,row)=>c.isgSave_(table,row,j),j=>newest.get(getKey(j.source))?.signature===j.source.signature)});
  const approval=nativeApprovalSession(google,config,binding,'IELTS SPEAKING AI',c.isgJobs_(table),(j,row)=>c.isgSave_(table,row,j));
  speakingApproval=approval;
  const bytesCache=new Map(),audioBytes=c.isgAudioBytes_;c.isgAudioBytes_=m=>{if(!bytesCache.has(m.id)){let bytes;try{bytes=Buffer.from(audioBytes(m));validateAudioPart(m,{inlineData:{mimeType:m.mime,data:bytes.toString('base64')}},{root,materialize:true});}catch{const out=repairAudioLocally({m,job:activeAudioJob,g:google,root,ffmpeg:process.env.FFMPEG_PATH||'ffmpeg',emit});bytes=fs.readFileSync(out.file);m.mime=out.mime;validateAudioPart(m,{inlineData:{mimeType:m.mime,data:bytes.toString('base64')}},{root});}bytesCache.set(m.id,[...bytes]);}return bytesCache.get(m.id);};
  const call=c.isgCallGemini_;c.isgCallGemini_=(...args)=>{const [job,media]=args;if(!masterScopeAllowsJob(job))throw Error('SUBMISSION_BEFORE_MASTER_SCOPE');job.media=media;activeAudioJob=job;if(!approval.approved.has(job.id)||!job.teacherApproval?.approved)throw Error('TEACHER_APPROVAL_REQUIRED');if(job.approvedGenerateRequests&&!speakingRetryAllowed(job))throw Error('SINGLE_PASS_ALREADY_REQUESTED');const auditDir=path.join(root,'private','silence-audit');fs.mkdirSync(auditDir,{recursive:true});for(const m of media){const p=m.universalAudio?.fullFile||path.join(auditDir,m.id+'.audio');if(!m.universalAudio)fs.writeFileSync(p,Buffer.from(c.isgAudioBytes_(m)));m.localSilence=inspectSilence(process.env.FFMPEG_PATH||'ffmpeg',p);}if(media.every(m=>m.localSilence.silent))throw Error('LOCAL_SILENT_AUDIO');if(paidCalls>=maxApiCalls)throw Error('SPEAKING_RUN_API_LIMIT');reserveSpeakingRequest(job,args[3]);paidCalls++;const result=call(...args);emit({event:'IELTS_API_USAGE',jobId:job.id,usage:job.apiUsage});return result;};
  installSpeakingRetryProcess(c);
  for(const item of c.isgJobs_(table).filter(x=>(!masterSweep||masterSweep.allowsJob(x.job))&&masterScopeAllowsJob(x.job)&&approval.approved.has(x.job.id)).sort((a,b)=>masterSweepEnabled()?Number(!!b.job.rawId)-Number(!!a.job.rawId):0)){
   try{
   if(item.job.status==='NEEDS_REVIEW'&&item.job.error==='SPEAKING_MODEL_UNAVAILABLE'&&!item.job.rawId&&binding.modelAvailable!==false){item.job.status='QUEUED';item.job.error='';delete item.job.retryAt;c.isgSave_(table,item.row,item.job);}
   if(Date.now()>deadline-90000||finished>=maxJobs||paidCalls>=maxApiCalls)break;if(item.job.mode!=='live'||!['QUEUED','RETRY','PENDING_RETRY','GENERATED','PROCESSING','GENERATING'].includes(item.job.status))continue;
   if(masterSweepEnabled()&&(item.job.rawId||item.job.gradeId)&&restoreSpeakingCache(c,item,table,approval)){if(item.job.status==='DONE')finished++;continue;}
   const originalHasFeedback=c.isgHasFeedback_,before=c.isgTarget_(item.job.source).text;c.isgHasFeedback_=text=>masterSweepEnabled()||item.job.teacherApproval?.automatic?originalHasFeedback(text):text===before?false:originalHasFeedback(text);
   try{if(nativeOldFile(item.job,c.isgJobs_(table),google)){nativeResubmission(item.job,c.isgTarget_(item.job.source).range,()=>c.isgSave_(table,item.row,item.job),approval,OLD_FILE_NOTICE,'COMPLETED_NEEDS_RESUBMISSION');continue;}c.isgProcess_(table,item);if(item.job.error==='LOCAL_SILENT_AUDIO'||item.job.rawId&&noSpeech(decodeSavedDraft(c.isgReadArtifact_(item.job.rawId))))nativeResubmission(item.job,c.isgTarget_(item.job.source).range,()=>c.isgSave_(table,item.row,item.job),approval);if(item.job.status==='DONE'){approval.finish(item.job);c.isgSave_(table,item.row,item.job);}}finally{c.isgHasFeedback_=originalHasFeedback;}
   emit({event:'IELTS_JOB',id:item.job.id,status:item.job.status,error:item.job.error||'',className:item.job.source.className,code:item.job.source.code,cell:item.job.target?.address||''});if(item.job.status==='DONE')finished++;
   }catch(e){if(isTransient(e)){item.job.error=e.message;retryPreparation(item.job,()=>c.isgSave_(table,item.row,item.job));continue;}item.job.error=e.message;item.job.status=e.message.startsWith('SYSTEM_AUDIO_INPUT_')?'SYSTEM_AUDIO_ERROR':'RETRY';item.job.nextAt=Date.now()+60000;c.isgSave_(table,item.row,item.job);emit({event:'IELTS_JOB_ERROR',id:item.job.id,error:e.message});}finally{settleSheetTruth({job:item.job,resolve:()=>c.isgTarget_(item.job.source).range,save:()=>c.isgSave_(table,item.row,item.job),emit});if(finished&&finished%10===0)destinationBatch?.flush();}
  }
  approval.flush();emit({event:'IELTS_COMPLETE',finished,paidCalls,counts:c.isgJobs_(table).reduce((a,x)=>(a[x.job.status]=(a[x.job.status]||0)+1,a),{})});return {finished,paidCalls,nextRetryAt:nextSpeakingRetry(c.isgJobs_(table))};
 }finally{try{queueBuffer?.flush();try{destinationBatch?.flush();try{masterSweep?.publish();}catch(e){emit({event:'MASTER_SWEEP_REPORT_ERROR',error:e.message});}}finally{destinationBatch?.close();}}finally{state.release();}}
}
