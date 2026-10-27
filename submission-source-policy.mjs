import {submissionUrls} from './ingestion-policy.mjs';
import {assertNativeEvidence} from './native-youtube.mjs';
// Receipt acknowledgement is independent of source availability and assessment.
export const SOURCE_VERSION='submission-source-v1';
export const SOURCE_LABELS=Object.freeze({missing:'ĐÃ NỘP — Chưa có link',access:'ĐÃ NỘP — Link cần mở quyền xem',invalid:'ĐÃ NỘP — Link không hợp lệ',valid:'ĐÃ NỘP — Link hợp lệ',pending:'ĐÃ NỘP — Chờ kiểm tra link'});
export const normalizeInput=value=>String(value||'').replace(/\s+/g,' ').trim();
export function sourceResult(state,reason,extra={}){return {schema:1,version:SOURCE_VERSION,state,label:SOURCE_LABELS[state],aiEligible:state==='valid',reason,...extra};}
export function sourceFailure(error){
 if(error?.driveEvidence&&(error.driveEvidence.technical||!error.driveEvidence.permissionConfirmed&&!error.driveEvidence.missingConfirmed)||Number(error?.httpCode)===401)return sourceResult('pending','SOURCE_CHECK_RETRY');
 const message=String(error?.message||error||''),code=Number(error?.httpCode||message.match(/(?:HTTP[_ ]|SOURCE_HTTP_)(\d{3})/)?.[1]||0);
 if(process.env.SHEET_TRUTH_SYNC==='true'&&/TRANSIENT_MEDIA_DOWNLOAD_TIMEOUT/.test(message))return sourceResult('pending','DOWNLOAD_IN_PROGRESS',{retryAfterMs:2000});
 if(/^TRANSIENT_MEDIA_YOUTUBE_[A-Z_]+$/.test(message))return sourceResult('pending',message,{retryAfterMs:120000});
 if(/rateLimitExceeded|quota|dailyLimit|too many requests/i.test(message)||code===429||code>=500)return sourceResult('pending','SOURCE_CHECK_RETRY');
 if(message==='YOUTUBE_PRIVATE')return sourceResult('access','YOUTUBE_PRIVATE_CONFIRMED');
 if(code===401||code===403||/SOURCE_ACCESS_REQUIRED/.test(message))return sourceResult('access','ACCESS_DENIED');
 if(code===404||code===410||/SOURCE_INVALID|INVALID_DRIVE_LINK|INVALID_YOUTUBE|SOURCE_NOT_FOUND|PREFLIGHT_FILE_MISSING_OR_INVALID|UNSUPPORTED_MEDIA|SPEAKING_AUDIO_EMPTY/.test(message))return sourceResult('invalid','MISSING_OR_INVALID_FILE');
 // Quota/rate limits, transport errors and unsupported providers are not proof
 // of an invalid pupil link. Hold without a paid call; retry next scan.
 return sourceResult('pending',/UNSUPPORTED_LINK/.test(message)?'PROVIDER_NOT_SUPPORTED':'SOURCE_CHECK_RETRY');
}
export function sourceInput(text){
 const input=normalizeInput(text);if(!input)return sourceResult('missing','NO_LINK');
 const raw=submissionUrls(input);
 if(!raw.length){if(/^[-\w]{15,}(?:[\s,;]+[-\w]{15,})*$/.test(input))return {input,urls:[],driveIds:input.split(/[\s,;]+/)};return sourceResult('invalid','MALFORMED_URL');}
 const urls=[];
 for(const value of raw){let u;try{u=new URL(value.replace(/[),.;\]}]+$/,''));}catch{return sourceResult('invalid','MALFORMED_URL');}
  if(u.protocol!=='https:'||u.username||u.password)return sourceResult('invalid','UNSAFE_URL');
  urls.push(u.href);
 }
 return {input,urls};
}
export function inspectSubmissionSource({text,ids,service,metadata}){
 const syntax=ids?null:sourceInput(text);if(syntax?.state)return syntax;
 try{
  const files=ids||service.ids(text);if(!files.length)return sourceResult('invalid','NO_EXTRACTABLE_FILE');
  const proofs=[];
  // Check every attachment before ANY Gemini upload or generation is allowed.
  for(const id of files){const m=metadata(id);if(m.nativeYouTube){if(m.trashed)throw Error('SOURCE_NOT_FOUND');const proof=assertNativeEvidence(m.nativeYouTube,{id});proofs.push({id,bytes:null,modified:m.modifiedTime||m.modified,nativeYouTube:proof});continue;}if(m.trashed||!Number(m.size))return sourceResult('invalid','EMPTY_OR_REMOVED_FILE');
   const mime=m.mimeType||m.mime;if(!/^(audio|video|image)\//.test(mime||'')&&mime!=='application/pdf'&&!/\.(?:mp4|mov|m4a|mp3|wav|aac|ogg|flac|webm)$/i.test(m.name||''))return sourceResult('invalid','UNSUPPORTED_FILE_FORMAT');
   const proof=service.verifyDownload({id,mime,size:Number(m.size),modified:m.modifiedTime||m.modified});
   if(!proof||proof.complete!==true||proof.bytes!==Number(m.size))return sourceResult('pending','DOWNLOAD_NOT_CONFIRMED');
   proofs.push({id,bytes:proof.bytes,modified:m.modifiedTime||m.modified});
  }
  return sourceResult('valid',proofs.some(f=>f.nativeYouTube)?'PROVIDER_NATIVE_MEDIA_CONFIRMED':'DOWNLOAD_CONFIRMED',{files:proofs});
 }catch(error){return sourceFailure(error);}
}
export function assertSourceReady(result){if(result?.schema!==1||result.state!=='valid'||result.aiEligible!==true||!result.files?.length||result.files.some(f=>f.nativeYouTube?!assertNativeEvidence(f.nativeYouTube,{id:f.id}):!(f.bytes>0)))throw Error('SOURCE_NOT_READY_FOR_AI');}
export function sourceNotice(result,time){return (result?.label||SOURCE_LABELS.pending)+(time?' · '+time:'');}

// A browser-playable YouTube video may fail on a hosted downloader IP. A 403,
// bot challenge, missing output, or extractor failure is not privacy evidence.
export function classifyYouTubeFailure(result){
 const text=String(result?.stderr||'')+' '+String(result?.error?.message||'');
 if(result?.error?.code==='ETIMEDOUT')return 'TRANSIENT_MEDIA_DOWNLOAD_TIMEOUT';
 if(/No module named|command not found|ENOENT/.test(text))return 'TRANSIENT_MEDIA_YTDLP_UNAVAILABLE';
 if(/private video|this video is private|sign in.*(?:granted access|private video)/i.test(text))return 'YOUTUBE_PRIVATE';
 if(/(?:video (?:has been|was) (?:removed|deleted)|video does not exist|HTTP Error (404|410))/i.test(text))return 'SOURCE_NOT_FOUND';
 if(/confirm.*not a bot|HTTP Error (401|403)|sign in/i.test(text))return 'TRANSIENT_MEDIA_YOUTUBE_AUTH_CHALLENGE';
 if(/timed?\s*out|HTTP Error (500|502|503|504)|connection (?:reset|aborted)|Temporary failure/i.test(text))return 'TRANSIENT_MEDIA_YOUTUBE_NETWORK';
 return 'TRANSIENT_MEDIA_YOUTUBE_UNCLASSIFIED';
}
const legacyYoutubeBody='❌ CẦN NỘP LẠI — Link YouTube của con ở chế độ riêng tư hoặc chưa mở quyền xem. Con mở công khai/bất kỳ ai có link đều xem được để cô nhận xét nhé!';
export const isUnprovenYouTubeNotice=text=>String(text||'').trim().endsWith(legacyYoutubeBody);
export function canRecheckYouTubeNotice(job,text){
 if(!isUnprovenYouTubeNotice(text)||!isUnprovenYouTubeNotice(job?.autoNotice)||!/https?:\/\/(?:www\.)?(?:youtu\.be|youtube\.com)\//i.test(job?.receipt?.links||job?.source?.links||job?.source?.link||''))return false;
 if(job.sourceIntake?.reason==='YOUTUBE_PRIVATE_CONFIRMED')return false;
 const seen=new Set();function spent(x,root=false){if(!x||typeof x!=='object'||seen.has(x))return false;seen.add(x);
  if(x.rawId||x.gradeId||x.apiUsage||x.usage||x.verificationRawId||x.verificationUsage||x.gradeUsable===true||x.candidates?.length||x.providerResponseReceived?.httpStatus===200||Number(x.generateRequests||0)>0||Number(x.approvedGenerateRequests||0)>0||Number(x.physicalGenerateRequests||0)>0||x.masterGenerationReserved||x.runnerGenerationStarted||x.generationReservation||x.generationAttempt?.calls)return true;
  if(!root&&x.resultHash&&!isUnprovenYouTubeNotice(x.autoNotice))return true;
  return Object.values(x).some(v=>v&&typeof v==='object'&&spent(v));
 }return !spent(job,true);
}
