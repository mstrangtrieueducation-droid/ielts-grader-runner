import assert from 'node:assert/strict';
import {checkNativeYouTube,assertNativeEvidence,nativeYouTubePart,validateNativeYouTubePart,isNativeYouTubePart,nativeInputIdentity,NATIVE_PROOF_TTL,refreshNativeIntake} from './native-youtube.mjs';
import {createMediaService,universalValidatedRequest} from './universal-media.mjs';
import {validateAudioPart,assertAudioPayload} from './audio-payload-guard.mjs';
import {inspectSubmissionSource,assertSourceReady,sourceFailure} from './submission-source-policy.mjs';
import {installKidsPreprocessing} from './automatic-preprocessing.mjs';
import vm from 'node:vm';import {auditPreparedPart} from './teacher-approval-guards.mjs';
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
const previous=process.env.NATIVE_YOUTUBE_INPUT;process.env.NATIVE_YOUTUBE_INPUT='true';let countRequests=0,downloads=0;const root=fs.mkdtempSync(path.join(os.tmpdir(),'native-youtube-test-')),id='yt_AbCdEfGhIjK';
const response=(audio=70,video=130)=>({getResponseCode:()=>200,getContentText:()=>JSON.stringify({totalTokens:audio+video+6,promptTokensDetails:[{modality:'AUDIO',tokenCount:audio},{modality:'VIDEO',tokenCount:video},{modality:'TEXT',tokenCount:6}]})});
const transport=q=>{countRequests++;assert(q.url.endsWith(':countTokens'));assert.equal(q.method,'POST');assert(q.headers['x-goog-api-key']);assert(!q.url.includes('generateContent'));assert.equal(JSON.parse(q.body).contents[0].parts[1].fileData.mimeType,'video/mp4');return response();};
try{
 const proof=checkNativeYouTube(id,{key:'fixture',transport}),m={id,mime:'video/mp4',size:0,modified:proof.identity,nativeYouTube:proof},part=nativeYouTubePart(m);
 assert(isNativeYouTubePart(part));assert.equal(validateAudioPart(m,part).audioTokens,70);assert.equal(validateNativeYouTubePart(m,part).id,id);
 assert.throws(()=>assertNativeEvidence({...proof,audioTokens:999}),/PROOF_REQUIRED/);assert.throws(()=>assertNativeEvidence(proof,{now:proof.checkedAt+NATIVE_PROOF_TTL+1}),/PROOF_REQUIRED/);
 assert.throws(()=>nativeYouTubePart({...m,id:'yt_ZyXwVuTsRqP'}),/PROOF_REQUIRED/);assert.throws(()=>validateNativeYouTubePart(m,{fileData:{mimeType:'video/mp4',fileUri:part.fileData.fileUri+'&other=1'}}),/BINDING/);
 const job={media:[m]},wire={contents:[{role:'user',parts:[{text:'Assigned rubric'},part]}]},check=assertAudioPayload(wire,job);assert.equal(check.files[0].bytes,null);assert.equal(check.files[0].sourceMode,'youtube_native');assert.equal(JSON.parse(universalValidatedRequest(wire,job)).contents[0].parts[1].fileData.fileUri,proof.url);
 assert.throws(()=>assertAudioPayload({contents:[{parts:[part,part]}]},job),/MISSING_STUDENT_AUDIO/);assert.throws(()=>assertAudioPayload({contents:[{parts:[{text:proof.url}]}]},job),/MISSING_STUDENT_AUDIO/);
 assert(!isNativeYouTubePart({fileData:{mimeType:'video/mp4',fileUri:'https://www.youtube.com.evil.test/watch?v=AbCdEfGhIjK'}}));
 assert.throws(()=>checkNativeYouTube(id,{key:'fixture',transport:()=>response(0,130)}),/MODALITIES_UNCONFIRMED/);assert.throws(()=>checkNativeYouTube(id,{key:'fixture',transport:()=>({getResponseCode:()=>403})}),/NATIVE_INPUT_UNAVAILABLE/);
 const g={api:()=>{},fileMeta:()=>{throw Error('UNEXPECTED_DRIVE');}},service=createMediaService({g,root,key:'fixture',youtubeDownloadFirst:false,download:transport,run:()=>{downloads++;throw Error('DOWNLOADER_NOT_EXPECTED');}}),meta=service.youtube(id);
 assert.equal(meta.size,null,'native inputs do not fabricate on-disk byte counts');const mm={id,mime:meta.mimeType,size:0,modified:meta.modifiedTime,nativeYouTube:meta.nativeYouTube};
 const intake=inspectSubmissionSource({ids:[id],service,metadata:g.fileMeta});assert.equal(intake.state,'valid');assert.equal(intake.reason,'PROVIDER_NATIVE_MEDIA_CONFIRMED');assert.equal(intake.reason,'PROVIDER_NATIVE_MEDIA_CONFIRMED');assert.equal(intake.reason,'PROVIDER_NATIVE_MEDIA_CONFIRMED');assertSourceReady(intake);assert.equal(intake.files[0].bytes,null);assert(intake.files[0].nativeYouTube.audioTokens>0);const j={media:[mm],sourceIntake:intake};refreshNativeIntake(j,mm);
 let saved=0;const ctx={fileMeta_:()=>{},step_:()=>{},handleError_:()=>{},UrlFetchApp:{fetch:()=>{}},mediaPart_:()=>{throw Error('LEGACY_DOWNLOAD_NOT_EXPECTED');}};
 installKidsPreprocessing(ctx,{g,service,isLatest:()=>true});assert.equal(ctx.fileMeta_(id,1).nativeYouTube.id,id,'Array.map numeric index must not be mistaken for reference=true');assert(isNativeYouTubePart(ctx.mediaPart_(j,mm,()=>saved++)));assert.equal(saved,1);
 assert.deepEqual(nativeInputIdentity(mm),nativeInputIdentity({...mm,nativeYouTube:{...mm.nativeYouTube,checkedAt:mm.nativeYouTube.checkedAt+1}}),'input identity excludes volatile preflight time');
 auditPreparedPart({g:{file:()=>{throw Error('NO_NATIVE_DRIVE_DOWNLOAD');}},c:{},job:j,m:mm,part:service.nativePart(mm),root,ffmpeg:'forbidden-offline-test'});
 if(fs.existsSync('gas/CostPolicy.gs')&&fs.readFileSync('gas/CostPolicy.gs','utf8').includes('meta.nativeYouTube||')){
  const cell={getDisplayValue:()=>'',getFormula:()=>''},context=vm.createContext({Date,require_:(ok,why)=>assert(ok,why),destination_:()=>({cell}),hasFeedback_:()=>false,driveIds_:()=>[id],fileMeta_:()=>mm,UrlFetchApp:{fetch:()=>{throw Error('NATIVE_MUST_NOT_QUERY_DRIVE_DURATION');}}});
  vm.runInContext(fs.readFileSync('gas/CostPolicy.gs','utf8'),context);const costJob={receipt:{},cls:{},route:{}};const files=context.kidsCostPreflight_(costJob);assert.equal(files[0].durationSeconds,null);assert.equal(files[0].size,0);assert.equal(costJob.costPreflight.files[0].nativeYouTube.id,id);
 }
 if(fs.existsSync('ielts-gas/SpeakingGemini.gs')){
  const seen=[],context=vm.createContext({isgKey_:()=> 'fixture',isgPrompt_:()=> 'Same approved rubric',isgNativeYouTubePart_:m=>{seen.push(m.id);return service.nativePart(m);},isgAudioBytes_:()=>{throw Error('NATIVE_MUST_NOT_FABRICATE_AUDIO_BYTES');},isgFresh_:()=>{throw Error('CHECK_BEFORE_RESERVATION');}});
  vm.runInContext(fs.readFileSync('ielts-gas/SpeakingGemini.gs','utf8'),context);assert.throws(()=>context.isgCallGemini_({source:{},target:{}},[mm],{},()=>{}),/CHECK_BEFORE_RESERVATION/);assert.deepEqual(seen,[id]);
 }
 assert.equal(downloads,0);assert.equal(sourceFailure(Error('TRANSIENT_MEDIA_YOUTUBE_NATIVE_INPUT_UNAVAILABLE')).state,'pending');
 process.env.NATIVE_YOUTUBE_INPUT='false';assert.throws(()=>validateAudioPart(mm,part),/PROOF_REQUIRED/);
 console.log(JSON.stringify({nativeSourceAdapter:true,modalityPreflight:true,sourceAndWireBound:true,forgeryAndExpiryRejected:true,noFakeBytes:true,driveGuardUnchanged:true,countRequests,generationCalls:0,sheetWrites:0}));
}finally{if(previous===undefined)delete process.env.NATIVE_YOUTUBE_INPUT;else process.env.NATIVE_YOUTUBE_INPUT=previous;fs.rmSync(root,{recursive:true,force:true});}
