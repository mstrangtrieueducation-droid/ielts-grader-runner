import {submissionUrls,youtubeDownloadArgs,driveErrorEvidence} from './ingestion-policy.mjs';
import {nativeYoutubeEnabled,checkNativeYouTube,assertNativeEvidence,nativeYouTubePart} from './native-youtube.mjs';
import {classifyYouTubeFailure} from './submission-source-policy.mjs';
import {sheetTruthEnabled} from './sheet-truth-state.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {request,pause} from './google-adapter.mjs';
import {sheetsGate} from './shared-gate.mjs';
import {audioStreams,streamSelection} from './student-audio.mjs';
import {validatedAudioRequest,validateAudioPart} from './audio-payload-guard.mjs';

export const MEDIA_RESOLVER_VERSION='universal-media-resolver-20261027';
export const PREPROCESS_VERSION='teacher-universal-preprocess-20261017';
export const MAX_PART_BYTES=5*1024*1024;
export const EMPTY_LINK_NOTICE='❌ CẦN NỘP LẠI — Bài nộp chưa đính kèm link video/file. Con kiểm tra và nộp lại link nhé!';
export function reusePreparedDownload(service,media,destination,{link=fs.linkSync,copy=fs.copyFileSync}={}){
 if(fs.existsSync(destination)&&fs.statSync(destination).size===Number(media.size))return destination;
 const source=service.localFile(media);if(!fs.existsSync(source)||fs.statSync(source).size!==Number(media.size))throw Error('TRANSIENT_MEDIA_DOWNLOAD_SIZE');
 try{link(source,destination);}catch(error){if(!['EXDEV','EPERM','EOPNOTSUPP','ENOSYS'].includes(error.code))throw error;copy(source,destination);}
 if(fs.statSync(destination).size!==Number(media.size))throw Error('TRANSIENT_MEDIA_DOWNLOAD_SIZE');return destination;
}
export const YOUTUBE_NOTICE='❌ CẦN NỘP LẠI — Link YouTube của con ở chế độ riêng tư hoặc chưa mở quyền xem. Con mở công khai/bất kỳ ai có link đều xem được để cô nhận xét nhé!';
const sha=b=>createHash('sha256').update(b).digest('hex');
const transient=/GOOGLE_HTTP_429|HTTP[_ ](?:500|502|503|504)|NETWORK_OUTCOME_UNKNOWN|CONNECTION_TIMEOUT|ETIMEDOUT|ECONNRESET|TRANSIENT_MEDIA/;
export const isTransient=e=>transient.test(String(e?.message||e));
export function retryTransient(fn,{sleep=pause,retries=2}={}){
 for(let n=0;;n++)try{return fn();}catch(e){if(!isTransient(e)||n>=retries)throw e;sleep(5000);}
}
// Generation is deliberately NOT retried at transport level: its durable
// reservation and response ledger must be saved between each provider attempt.
export function installTransientGoogle(g,{transport=request,sleep=pause}={}){
 if(g.universalTransientInstalled)return;g.universalTransientInstalled=true;
 const api=g.api.bind(g);g.api=(url,method='GET',data)=>{
  const verb=method.toUpperCase(),safe=verb==='GET'||verb==='PUT'||verb==='POST'&&/\/values:batchUpdate$/.test(url);
  if(!safe)return api(url,method,data);
  return retryTransient(()=>{
   if(url.startsWith('https://sheets.googleapis.com/')){if(process.env.GOOGLE_RATE_GATE_FILE)sheetsGate(process.env.GOOGLE_RATE_GATE_FILE,verb==='GET'?'read':'write');else{pause(Math.max(0,(g.nextSheetAt||0)-Date.now()));g.nextSheetAt=Date.now()+1800;}if(g.metrics)g.metrics.sheetCalls++;}
   let response;for(let quotaAttempt=0;quotaAttempt<6;quotaAttempt++){if(quotaAttempt&&url.startsWith('https://sheets.googleapis.com/')&&process.env.GOOGLE_RATE_GATE_FILE)sheetsGate(process.env.GOOGLE_RATE_GATE_FILE,verb==='GET'?'read':'write');response=transport({url,method:verb,headers:{Authorization:'Bearer '+g.token(),'Content-Type':'application/json',...(/^https:\/\/(?:www\.)?googleapis.com\/drive\//.test(url)&&g.driveResourceKeys?.size?{'X-Goog-Drive-Resource-Keys':[...g.driveResourceKeys].map(([id,key])=>id+'/'+key).join(',')}:{})},body:data===undefined?undefined:JSON.stringify(data),timeoutMs:30000});if(response.getResponseCode()!==429||quotaAttempt===5)break;const retryAfter=Number(response.getAllHeaders?.()['retry-after']||0)*1000;sleep(Math.max([5000,10000,20000,40000,60000][quotaAttempt],Math.min(120000,retryAfter||0)));}const status=response.getResponseCode();
   if(status<200||status>299){let details={};try{details=JSON.parse(response.getContentText()||'{}');}catch{}const e=Error('GOOGLE_HTTP_'+status);e.httpCode=status;e.driveEvidence=driveErrorEvidence(status,details);throw e;}
   return JSON.parse(response.getContentText()||'{}');
  },{sleep});
 };
}
export function downloadWithRetry(q,download=request,options={}){
 const initial=q.append&&fs.existsSync(q.outputFile)?fs.statSync(q.outputFile).size:0;
 return retryTransient(()=>{
  if(q.outputFile&&fs.existsSync(q.outputFile))fs.truncateSync(q.outputFile,initial);
  const response=download(q);if([500,502,503,504].includes(response.getResponseCode()))throw Error('GOOGLE_HTTP_'+response.getResponseCode());return response;
 },options);
}
export function hasSavedResult(x,seen=new Set()){
 if(!x||typeof x!=='object'||seen.has(x))return false;seen.add(x);
 if(['rawId','gradeId','resultHash','usage','apiUsage','verificationRawId','verificationUsage','autoNotice','pendingFeedback','pendingFeedbackRender','pendingMasterFeedback','pendingMasterReading'].some(k=>!!x[k])||x.providerResponseReceived?.httpStatus===200||x.gradeUsable===true||x.candidates?.length)return true;
 return Object.values(x).some(v=>v&&typeof v==='object'&&hasSavedResult(v,seen));
}
export function hasRequest(x,seen=new Set()){
 if(!x||typeof x!=='object'||seen.has(x))return false;seen.add(x);
 if(Number(x.generateRequests||x.approvedGenerateRequests||x.physicalGenerateRequests||0)>0||x.masterGenerationReserved||x.runnerGenerationStarted||x.generationReservation||x.generationAttempt?.calls)return true;
 return Object.values(x).some(v=>v&&typeof v==='object'&&hasRequest(v,seen));
}
export function retryPreparation(job,save,now=Date.now()){
 const previous=job.error||job.internalDiagnostic||'';
 job.preprocessRetry={version:PREPROCESS_VERSION,lastError:previous,failedAt:new Date(now).toISOString(),attempts:(job.preprocessRetry?.attempts||0)+1};
 job.status='RETRY';job.error='';job.nextAt=now+60000;job.retryAt=new Date(job.nextAt).toISOString();save();
}
export function preprocessingRecoverable(j){
 return !hasSavedResult(j)&&!hasRequest(j)&&!j.presentationResubmissionRequired&&
  /SYSTEM_AUDIO_INPUT_(?:SOURCE_UNAVAILABLE|UNSUPPORTED_EXTERNAL_SOURCE|LOCAL_REPAIR_FAILED)|SPEAKING_AUDIO_(?:REQUIRED|TOTAL_OVER_12_MIB|FORMAT_UNSUPPORTED)|GOOGLE_HTTP_(?:429|500|503)|TRANSIENT_MEDIA/.test(j.error||j.preprocessRetry?.lastError||'');
}
export function youtubeId(url){
 let u;try{u=new URL(url);}catch{return null;}
 if(u.protocol!=='https:')return null;
 const host=u.hostname.toLowerCase();let id;
 if(host==='youtu.be')id=u.pathname.slice(1).split('/')[0];
 else if(['youtube.com','www.youtube.com','m.youtube.com'].includes(host))id=u.searchParams.get('v')||u.pathname.match(/^\/(?:shorts|embed|live)\/([^/]+)/)?.[1];
 return /^[A-Za-z0-9_-]{11}$/.test(id||'')?id:null;
}
export function sourceIds(text,register=()=>{}){
 const urls=submissionUrls(text),ids=[];
 if(!urls.length&&/^[-\w]{15,}(?:[\s,;]+[-\w]{15,})*$/.test(String(text||'').trim()))return [...new Set(String(text).trim().split(/[\s,;]+/))];
 for(const raw of urls){const url=raw.replace(/[).;]+$/,'');const yt=youtubeId(url);if(yt){const id='yt_'+yt;register(id,'https://www.youtube.com/watch?v='+yt);ids.push(id);continue;}
  const u=new URL(url);if(u.protocol!=='https:'||!['drive.google.com','docs.google.com'].includes(u.hostname.toLowerCase()))throw Error('UNSUPPORTED_LINK');
  const id=url.match(/(?:\/(?:d|folders)\/|[?&]id=)([-\w]{15,})/)?.[1];if(!id)throw Error('INVALID_DRIVE_LINK');ids.push(id);
 }return [...new Set(ids)];
}

export function fileDigest(file){const h=createHash('sha256'),fd=fs.openSync(file,'r'),buffer=Buffer.alloc(1024*1024);try{let count;while((count=fs.readSync(fd,buffer,0,buffer.length,null))>0)h.update(buffer.subarray(0,count));return h.digest('hex');}finally{fs.closeSync(fd);}}
export function driveConfirmation(html,headers,id){
 const decode=x=>String(x||'').replaceAll('&amp;','&').replaceAll('&#39;',"'").replaceAll('&quot;','"');
 const form=String(html||'').match(/<form\b([^>]*)>([\s\S]*?)<\/form>/i);if(!form)return null;
 const attr=(s,n)=>s.match(new RegExp('\\b'+n+'\\s*=\\s*["\\\']([^"\\\']*)["\\\']','i'))?.[1];
 let url;try{url=new URL(decode(attr(form[1],'action')),'https://drive.google.com');}catch{return null;}
 if(url.protocol!=='https:'||!['drive.google.com','drive.usercontent.google.com','docs.google.com'].includes(url.hostname))return null;
 for(const match of form[2].matchAll(/<input\b([^>]*)>/gi)){const name=attr(match[1],'name'),value=attr(match[1],'value');if(name&&value!==undefined)url.searchParams.set(name,decode(value));}
 if(url.searchParams.get('id')&&url.searchParams.get('id')!==id)return null;
 url.searchParams.set('id',id);if(!url.searchParams.has('confirm'))url.searchParams.set('confirm','t');
 const raw=String(headers?.['set-cookie']||''),cookies=[...raw.matchAll(/(?:^|,\s*)(download_warning[^=;\s]*)=([^;]+)/g)].map(x=>x[1]+'='+x[2]).join('; ');
 return {url:url.href,...(cookies?{headers:{Cookie:cookies}}:{})};
}
function duration(stderr){const m=String(stderr).match(/Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)/);return m?+m[1]*3600 + +m[2]*60 + +m[3]:NaN;}
function probe(ffmpeg,file,run){const r=run(ffmpeg,['-nostdin','-hide_banner','-i',file],{encoding:'utf8',windowsHide:true,timeout:60000});if(r.error)throw Error('TRANSIENT_MEDIA_PROBE');return {stderr:r.stderr||'',seconds:duration(r.stderr)};}
function selection(stderr){
 const streams=audioStreams(stderr),aac=streams.filter(t=>/Audio: aac\b/.test(t.description)&&/stereo/.test(t.description)&&/\(default\)/.test(t.description));
 if(streams.length===2&&aac.length===1&&streams.some(t=>/Audio: none \(apac\b/.test(t.description))&&/com\.apple\.quicktime\.make\s*:\s*Apple/.test(stderr))return {args:['-map','0:'+aac[0].index],mode:'apple_aac_compatibility',indices:[aac[0].index]};
 return streamSelection(streams);
}
export function decodedSampleClockArgs(selected){
 const args=selected.slice(),complex=args.indexOf('-filter_complex');
 if(complex<0)return [...args,'-af','asetpts=N/SR/TB'];
 const map=args.indexOf('-map'),label=args[map+1];if(map<0||!/^\[[\w]+\]$/.test(label||''))throw Error('TRANSIENT_MEDIA_AUDIO_CLOCK_SELECTION');
 args[complex+1]+=';'+label+'asetpts=N/SR/TB[decoded_sample_clock]';args[map+1]='[decoded_sample_clock]';return args;
}
export function transcodeUniversal({input,output,ffmpeg=process.env.FFMPEG_PATH||'ffmpeg',run=spawnSync,sourceId,modified,sourceSize}){
 fs.mkdirSync(path.dirname(output),{recursive:true});const manifest=output+'.universal.json';
 if(fs.existsSync(manifest))try{const m=JSON.parse(fs.readFileSync(manifest));if(m.version===PREPROCESS_VERSION&&m.modified===modified&&m.sourceSize===sourceSize&&[m.fullFile,...m.segments.map(s=>s.file)].every(f=>fs.existsSync(f))&&m.segments.every(s=>fs.statSync(s.file).size===s.bytes&&s.bytes>10240&&s.bytes<MAX_PART_BYTES&&sha(fs.readFileSync(s.file))===s.sha256))return m;}catch{}
 const before=probe(ffmpeg,input,run),chosen=selection(before.stderr),working=output+'.working.mp3';
 const r=run(ffmpeg,['-nostdin','-v','error','-i',input,...chosen.args,'-vn','-ar','16000','-ac','1','-c:a','libmp3lame','-b:a','64k','-y',working],{encoding:'utf8',windowsHide:true,timeout:20*60000});
 if(r.status!==0||!fs.existsSync(working)||fs.statSync(working).size<=10240)throw Error('TRANSIENT_MEDIA_TRANSCODE');
 const after=probe(ffmpeg,working,run);if(!Number.isFinite(after.seconds))throw Error('TRANSIENT_MEDIA_INCOMPLETE_AUDIO');
 // Container/video duration and decoded packet timestamps may include a late
 // audio start or timestamp gaps. Measure consumed samples from zero instead;
 // comparing their final source PTS falsely rejects a complete normalized MP3.
 // Only the validation clock changes. Conversion bytes/stream selection stay.
 if(Number.isFinite(before.seconds)&&after.seconds+0.25<before.seconds){
  const decoded=run(ffmpeg,['-nostdin','-v','error','-nostats','-progress','pipe:1','-i',input,...decodedSampleClockArgs(chosen.args),'-vn','-f','null','-'],{encoding:'utf8',windowsHide:true,timeout:20*60000});
  const times=[...String(decoded.stdout||'').matchAll(/out_time_us=(\d+)/g)].map(x=>Number(x[1])/1e6),audioSeconds=times.at(-1);
  if(decoded.status!==0||!Number.isFinite(audioSeconds)||after.seconds+0.25<audioSeconds)throw Error('TRANSIENT_MEDIA_INCOMPLETE_AUDIO');
 }
 fs.renameSync(working,output);const total=after.seconds,count=Math.max(1,Math.ceil(fs.statSync(output).size/(MAX_PART_BYTES-256000)),Math.ceil(total/540)),segments=[];
 for(let i=0;i<count;i++){
  const offset=i*total/count,file=count===1?output:output+'.segment-'+String(i).padStart(4,'0')+'.mp3';
  if(count>1){const result=run(ffmpeg,['-nostdin','-v','error','-ss',String(offset),'-i',output,...(i<count-1?['-t',String(total/count)]:[]),'-vn','-ar','16000','-ac','1','-c:a','libmp3lame','-b:a','64k','-y',file],{encoding:'utf8',windowsHide:true,timeout:20*60000});if(result.status!==0)throw Error('TRANSIENT_MEDIA_SEGMENT');}
  const bytes=fs.statSync(file).size;if(bytes<=10240||bytes>=MAX_PART_BYTES)throw Error('TRANSIENT_MEDIA_SEGMENT_SIZE');
  segments.push({file,bytes,sha256:sha(fs.readFileSync(file)),offsetSeconds:offset,durationSeconds:probe(ffmpeg,file,run).seconds,sourceId,mime:'audio/mpeg'});
 }
 if(segments.reduce((n,s)=>n+s.durationSeconds,0)+0.3<total)throw Error('TRANSIENT_MEDIA_INCOMPLETE_AUDIO');
 const result={version:PREPROCESS_VERSION,sourceId,modified,sourceSize,fullFile:output,durationSeconds:total,sampleRate:16000,channels:1,bitrate:64000,selection:chosen,segments};fs.writeFileSync(manifest,JSON.stringify(result));return result;
}
export function firstUniversalPart(m,result){
 m.universalAudio=result;m.audioSelection=result.selection;const first=result.segments[0];
 m.audioPayloadProof={...first,version:'disk-and-wire-audio-v1-20261014',uri:first.fileUri||null};m.runnerAudio={mime:'audio/mpeg',bytes:first.bytes,sha256:first.sha256,originalBytes:result.sourceSize||m.size,copy:false};
 return first.fileUri?{fileData:{mimeType:'audio/mpeg',fileUri:first.fileUri}}:{inlineData:{mimeType:'audio/mpeg',data:fs.readFileSync(first.file).toString('base64')}};
}
export function universalValidatedRequest(payload,job){
 const replacements=new Map(),media=[];
 for(const m of (job?.media||[]).filter(m=>!m.isReference)){
  const segments=m.universalAudio?.version===PREPROCESS_VERSION?m.universalAudio.segments:null;
  const key=m.audioPayloadProof?.uri||m.audioPayloadProof?.sha256,list=replacements.get(key)||[];list.push({m,segments});replacements.set(key,list);
  if(!segments||segments.length===1){media.push(m);continue;}
  for(const s of segments)media.push({...m,universalAudio:undefined,audioPayloadProof:{...s,version:'disk-and-wire-audio-v1-20261014',uri:s.fileUri||null}});
 }
 const contents=(payload.contents||[]).map(c=>({...c,parts:(c.parts||[]).flatMap(p=>{
  if(!(p.inlineData?.mimeType||p.fileData?.mimeType||'').startsWith('audio/'))return [p];
  const item=replacements.get(p.fileData?.fileUri||sha(Buffer.from(p.inlineData?.data||'','base64')))?.shift();if(!item?.segments||item.segments.length===1)return [p];
  return item.segments.flatMap((s,i)=>[{text:'CÙNG MỘT FILE HỌC SINH, đoạn '+(i+1)+'/'+item.segments.length+', bắt đầu tại '+s.offsetSeconds.toFixed(3)+' giây trong file gốc. Nghe đủ mọi đoạn theo thứ tự; cộng độ lệch này khi ghi mốc lỗi của file gốc.'},s.fileUri?{fileData:{mimeType:'audio/mpeg',fileUri:s.fileUri}}:{inlineData:{mimeType:'audio/mpeg',data:fs.readFileSync(s.file).toString('base64')}}]);
 })}));
 const expanded={...payload,contents},check={...job,media};const body=validatedAudioRequest(expanded,check);job.lastPayloadValidation=check.lastPayloadValidation;return body;
}
export function createMediaService({g,root,key=process.env.GEMINI_API_KEY,ffmpeg=process.env.FFMPEG_PATH||'ffmpeg',run=spawnSync,download=request,nativeYouTube=true,youtubeDownloadFirst=true}){
 installTransientGoogle(g);const dir=path.join(root,'private','universal-media');fs.mkdirSync(dir,{recursive:true});const urls=new Map(),prepared=new Map(),nativeCache=new Map();
 const register=(id,url)=>urls.set(id,url);

 const sourceKeys=g.driveResourceKeys ||= new Map();
 const rememberKeys=text=>{for(const url of submissionUrls(text)){try{const u=new URL(url),id=u.pathname.match(/\/(?:d|folders)\/([-\w]{15,})/)?.[1]||u.searchParams.get('id'),key=u.searchParams.get('resourcekey');if(id&&key&&/^[-\w]+$/.test(key))sourceKeys.set(id,key);}catch{}}};
 const folderMime='application/vnd.google-apps.folder',shortcutMime='application/vnd.google-apps.shortcut';
 const playable=f=>/^(audio|video)\//.test(f.mimeType||'')||/\.(?:mp4|mov|m4a|mp3|wav|aac|ogg|flac|webm|avi|mkv)$/i.test(f.name||'');
 const children=id=>{const files=[];let page;do{
  const data=g.api('https://www.googleapis.com/drive/v3/files?'+new URLSearchParams({q:"'"+id+"' in parents and trashed = false",fields:'nextPageToken,files(id,name,mimeType,size,createdTime,modifiedTime,trashed,resourceKey,shortcutDetails(targetId,targetMimeType))',pageSize:'100',orderBy:'name',supportsAllDrives:'true',includeItemsFromAllDrives:'true',...(page?{pageToken:page}:{})}));
  files.push(...data.files||[]);page=data.nextPageToken;
 }while(page);return files;};
 const compare=(a,b)=>String(a.name||'').localeCompare(String(b.name||''),'en',{numeric:true,sensitivity:'base'})||String(a.createdTime||a.modifiedTime||'').localeCompare(String(b.createdTime||b.modifiedTime||''))||String(a.id).localeCompare(String(b.id));
 const resolvedInputs=new Map();
 const ids=text=>{
  rememberKeys(text);const out=[],visited=new Set();let hasFolder=false;
  const visit=(id,known)=>{if(visited.has(id))return;visited.add(id);
   if(id.startsWith('yt_')){out.push(id);return;}
   const meta=known||g.fileMeta(id);if(meta.trashed)return;
   if(meta.resourceKey)sourceKeys.set(id,meta.resourceKey);
   if(meta.mimeType===shortcutMime){const target=meta.shortcutDetails?.targetId||g.api('https://www.googleapis.com/drive/v3/files/'+id+'?fields=shortcutDetails&supportsAllDrives=true').shortcutDetails?.targetId;if(!target)throw Error('TRANSIENT_MEDIA_SHORTCUT_UNRESOLVED');visit(target);return;}
   if(meta.mimeType!==folderMime){out.push(id);return;}
   hasFolder=true;for(const f of children(id).filter(x=>!x.trashed).sort(compare)){
    if(f.resourceKey)sourceKeys.set(f.id,f.resourceKey);
    if(f.mimeType===folderMime||f.mimeType===shortcutMime)visit(f.id,f);
    else if(playable(f)&&!visited.has(f.id)){visited.add(f.id);out.push(f.id);}
   }
  };
  const list=sourceIds(text,register);for(const id of list)visit(id);
  if(!out.length&&list.length)throw Error('TRANSIENT_MEDIA_FOLDER_EMPTY');resolvedInputs.set(String(text),{hasFolder,ids:out.slice()});return out;
 };
 // Speaking source signatures retain the pre-upgrade native ID projection.
 // Real downloads expand MIME-identified folders through ids(), not this view.
 const legacySourceIds=text=>{
  rememberKeys(text);const legacyUrls=(String(text||'').replace(/\\n/g,'\n').match(/https?:\/\/[^\s,<>"']+/gi)||[]).map(x=>x.replace(/[).;\]}]+$/,''));
  const list=[];for(const raw of legacyUrls){const url=raw.replace(/[).;]+$/,''),yt=youtubeId(url);if(yt){const id='yt_'+yt;register(id,'https://www.youtube.com/watch?v='+yt);list.push(id);continue;}const u=new URL(url);if(u.protocol!=='https:'||!['drive.google.com','docs.google.com'].includes(u.hostname.toLowerCase()))throw Error('UNSUPPORTED_LINK');const id=url.match(/(?:\/(?:d|folders)\/|[?&]id=)([-\w]{15,})/)?.[1];if(!id)throw Error('INVALID_DRIVE_LINK');list.push(id);}const out=[],folders=new Set(legacyUrls.filter(u=>/drive\.google\.com\/drive\/(?:u\/\d+\/)?folders\//.test(u)).map(u=>u.match(/folders\/([-\w]+)/)?.[1]));
  for(const id of list){if(!folders.has(id)){out.push(id);continue;}g.fileMeta(id);out.push(...children(id).filter(f=>/^(audio|video)\//.test(f.mimeType||'')).map(f=>f.id));}
  return [...new Set(out)];
 };
 function nativeMetadata(id){let proof=nativeCache.get(id);try{assertNativeEvidence(proof,{id});}catch{proof=checkNativeYouTube(id,{key,transport:download});nativeCache.set(id,proof);}return {id,name:id,mimeType:'video/mp4',size:null,modifiedTime:proof.identity,nativeYouTube:proof,trashed:false};}
 function nativePart(m){const meta=nativeMetadata(m.id);if(m.modified&&m.modified!==meta.modifiedTime)throw Error('SOURCE_INPUT_CHANGED');m.nativeYouTube=meta.nativeYouTube;m.modified=meta.modifiedTime;return nativeYouTubePart(m);}
 function youtube(id){
  if(!youtubeDownloadFirst&&nativeYouTube&&nativeYoutubeEnabled()){try{return nativeMetadata(id);}catch(e){if(!/^TRANSIENT_MEDIA_YOUTUBE_NATIVE_/.test(e.message))throw e;/* Unsupported native input may still be downloadable as ordinary MP3. */}}
  if(!/^yt_[\w-]{11}$/.test(id))throw Error('INVALID_YOUTUBE_ID');const url=urls.get(id)||'https://www.youtube.com/watch?v='+id.slice(3),file=path.join(dir,id.slice(3)+'.mp3'),meta=path.join(dir,id+'.mp3.json');
  if(fs.existsSync(file)&&fs.existsSync(meta))return JSON.parse(fs.readFileSync(meta));
  const python=process.env.PYTHON_PATH||(process.platform==='win32'?'python':'python3');
  const until=Date.now()+(sheetTruthEnabled()?30000:120000);let failure;
  for(const client of ['android,web','android_vr,web_embedded','']){
   const left=until-Date.now();if(left<=0)break;
   let r;try{r=run(python,youtubeDownloadArgs({url,node:process.execPath,output:path.join(dir,'%(id)s.%(ext)s'),client}),{encoding:'utf8',windowsHide:true,timeout:Math.min(left,client?15000:30000)});}catch(error){r={status:1,error};}
   if(r.status===0){failure=null;break;}failure=classifyYouTubeFailure(r);if(['YOUTUBE_PRIVATE','SOURCE_NOT_FOUND'].includes(failure))break;
  }
  if(failure){if(nativeYouTube&&nativeYoutubeEnabled()&&/^TRANSIENT_MEDIA_/.test(failure))return nativeMetadata(id);throw Error(failure);}

  if(!fs.existsSync(file)||!fs.statSync(file).size)throw Error('TRANSIENT_MEDIA_YOUTUBE_OUTPUT_MISSING');
  const result={id,name:id+'.mp3',mimeType:'audio/mpeg',size:String(fs.statSync(file).size),modifiedTime:fs.statSync(file).mtime.toISOString(),localFile:file,originalUrl:url,trashed:false};fs.writeFileSync(meta,JSON.stringify(result));return result;
 }
 const preparedPublic=new Map();const originalMeta=g.fileMeta.bind(g);g.fileMeta=id=>{
  if(id.startsWith('yt_'))return youtube(id);if(preparedPublic.has(id))return preparedPublic.get(id);
  try{return originalMeta(id);}catch(error){
   if(![403,404].includes(Number(error.httpCode))||error.driveEvidence?.technical)throw error;
   const file=path.join(dir,id+'.public.original');
   let r=download({url:'https://drive.google.com/uc?export=download&confirm=t&id='+encodeURIComponent(id)+(sourceKeys.has(id)?'&resourcekey='+encodeURIComponent(sourceKeys.get(id)):''),outputFile:file,timeoutMs:30000});
   let type=String(r.getAllHeaders?.()['content-type']||'').split(';')[0];
   if(r.getResponseCode()===200&&/text\/html/i.test(type)){
    const html=fs.existsSync(file)&&fs.statSync(file).size<2*1024*1024?fs.readFileSync(file,'utf8'):r.getContentText?.()||'';
    const confirmation=driveConfirmation(html,r.getAllHeaders?.(),id);
    if(confirmation){r=download({...confirmation,outputFile:file,timeoutMs:30000});type=String(r.getAllHeaders?.()['content-type']||'').split(';')[0];}
   }
   if(r.getResponseCode()===200&&/^(audio|video)\//.test(type)&&fs.existsSync(file)&&fs.statSync(file).size>10240){const meta={id,name:id+'.original',mimeType:type,size:String(fs.statSync(file).size),modifiedTime:fs.statSync(file).mtime.toISOString(),localFile:file,publicDownloadVerified:true,trashed:false};preparedPublic.set(id,meta);return meta;}
   throw error;
  }
 };
 function localFile(m){
  const downloadDeadline=Date.now()+(Number(m.size)>=50_000_000?300000:30000);
  if(m.id.startsWith('yt_'))return youtube(m.id).localFile;
  if(preparedPublic.has(m.id))return preparedPublic.get(m.id).localFile;
  const tag=m.id+'-'+sha(Buffer.from(String(m.modified))).slice(0,10),existing=path.join(root,'private','cache',tag+'.original');
  if(fs.existsSync(existing)&&fs.statSync(existing).size===m.size)return existing;
  const out=path.join(dir,tag+'.original');if(fs.existsSync(out)&&fs.statSync(out).size===m.size)return out;
  const partial=out+'.part';let offset=fs.existsSync(partial)?fs.statSync(partial).size:0;if(offset>m.size){fs.unlinkSync(partial);offset=0;}
  while(offset<m.size){if(sheetTruthEnabled()&&Date.now()>=downloadDeadline)throw Error('TRANSIENT_MEDIA_DOWNLOAD_TIMEOUT');const end=Math.min(m.size-1,offset+8*1024*1024-1),range='bytes '+offset+'-'+end+'/'+m.size;
   let response;try{response=downloadWithRetry({url:'https://www.googleapis.com/drive/v3/files/'+m.id+'?alt=media&supportsAllDrives=true',headers:{Authorization:'Bearer '+g.token(),Range:'bytes='+offset+'-'+end,'Accept-Encoding':'identity',...(sourceKeys.has(m.id)?{'X-Goog-Drive-Resource-Keys':m.id+'/'+sourceKeys.get(m.id)}:{})},outputFile:partial,append:offset>0,expectedContentRange:range,timeoutMs:sheetTruthEnabled()?Math.max(1,downloadDeadline-Date.now()):120000},download,sheetTruthEnabled()?{retries:0}:{});}catch(error){
    // The bridge validates Content-Range before appending. An interrupted body
    // can still have made durable progress; resume those bytes on the next
    // unpaid preparation turn instead of imposing a five-minute source hold.
    const bytes=fs.existsSync(partial)?fs.statSync(partial).size:offset;
    if(sheetTruthEnabled()&&error.message==='NETWORK_OUTCOME_UNKNOWN'&&bytes>offset&&bytes<=end+1)throw Error('TRANSIENT_MEDIA_DOWNLOAD_TIMEOUT');
    throw error;
   }if([401,403,404,410].includes(response.getResponseCode())){const e=Error('SOURCE_HTTP_'+response.getResponseCode());e.httpCode=response.getResponseCode();let body={};try{body=JSON.parse(response.getContentText()||'{}');}catch{}e.driveEvidence=driveErrorEvidence(e.httpCode,body);throw e;}if(response.getResponseCode()!==206||response.getAllHeaders()['content-range']!==range)throw Error('TRANSIENT_MEDIA_SOURCE_DOWNLOAD_FAILED');
   offset=fs.statSync(partial).size;if(offset!==end+1)throw Error('TRANSIENT_MEDIA_DOWNLOAD_SIZE');
  }fs.renameSync(partial,out);return out;
 }
 function uploadSegments(result){
  if(!key)throw Error('TRANSIENT_MEDIA_UPLOAD_KEY_MISSING');
  for(const s of result.segments){
   if(s.fileUri&&s.uploadKeyHash===sha(Buffer.from(key)))try{const check=download({url:s.fileUri,headers:{'x-goog-api-key':key},timeoutMs:30000});if(check.getResponseCode()===200&&JSON.parse(check.getContentText()).state==='ACTIVE')continue;}catch{}
   retryTransient(()=>{
    const start=download({url:'https://generativelanguage.googleapis.com/upload/v1beta/files',method:'POST',headers:{'x-goog-api-key':key,'Content-Type':'application/json','X-Goog-Upload-Protocol':'resumable','X-Goog-Upload-Command':'start','X-Goog-Upload-Header-Content-Length':String(s.bytes),'X-Goog-Upload-Header-Content-Type':'audio/mpeg'},body:JSON.stringify({file:{display_name:'student-audio-segment'}}),timeoutMs:60000});
    if([500,502,503,504].includes(start.getResponseCode()))throw Error('GOOGLE_HTTP_'+start.getResponseCode());
    const url=Object.entries(start.getAllHeaders()).find(([h])=>h.toLowerCase()==='x-goog-upload-url')?.[1];if(start.getResponseCode()!==200||!/^https:\/\/generativelanguage\.googleapis\.com\//.test(url||''))throw Error('TRANSIENT_MEDIA_UPLOAD_START');
    const uploaded=download({url,method:'POST',headers:{'x-goog-api-key':key,'Content-Type':'audio/mpeg','X-Goog-Upload-Offset':'0','X-Goog-Upload-Command':'upload, finalize'},bodyFile:s.file,timeoutMs:120000});
    if([500,502,503,504].includes(uploaded.getResponseCode()))throw Error('GOOGLE_HTTP_'+uploaded.getResponseCode());
    let file;try{file=JSON.parse(uploaded.getContentText()).file;}catch{}
    if(uploaded.getResponseCode()!==200||!file?.uri)throw Error('TRANSIENT_MEDIA_UPLOAD_FINISH');
    for(let n=0;file.state==='PROCESSING'&&n<24;n++){pause(5000);const poll=download({url:'https://generativelanguage.googleapis.com/v1beta/'+file.name,headers:{'x-goog-api-key':key},timeoutMs:30000});if(poll.getResponseCode()!==200)throw Error('GOOGLE_HTTP_'+poll.getResponseCode());file=JSON.parse(poll.getContentText());}
    if(file.state!=='ACTIVE'||!/^https:\/\/generativelanguage\.googleapis\.com\//.test(file.uri))throw Error('TRANSIENT_MEDIA_UPLOAD_PROCESSING');s.fileUri=file.uri;s.uploadKeyHash=sha(Buffer.from(key));
   });
  }
 }
 function prepare(m,{fileApi=false}={}){const tag=[m.id,m.modified,m.size].join('|');let result=prepared.get(tag);if(!result){const input=localFile(m),output=path.join(dir,m.id+'-'+sha(Buffer.from(tag)).slice(0,16)+'.mp3');result=transcodeUniversal({input,output,ffmpeg,run,sourceId:m.id,modified:m.modified,sourceSize:m.size});prepared.set(tag,result);}if(fileApi||result.segments.length>1)uploadSegments(result);return result;}
 function verifyAudio(m){
  const file=localFile(m);if(!fs.existsSync(file)||fs.statSync(file).size!==Number(m.size)||Number(m.size)<=10240)throw Error('TRANSIENT_MEDIA_PROBE_SIZE');
  const r=run(ffmpeg,['-nostdin','-hide_banner','-i',file],{encoding:'utf8',windowsHide:true,timeout:30000});if(r.error)throw Error('TRANSIENT_MEDIA_PROBE');
  const text=String(r.stderr||''),seconds=duration(text),streams=audioStreams(text);
  return {version:'decoded-source-audio-proof-20261027',sourceId:m.id,modified:m.modified,size:Number(m.size),sha256:fileDigest(file),audioStreams:streams.length,durationSeconds:Number.isFinite(seconds)?seconds:null,confirmedAbsent:streams.length===0&&seconds>0&&/Stream #0:\d+[^\n]*Video:/.test(text),at:new Date().toISOString()};
 }
 function verifyDownload(m){const file=localFile(m),bytes=fs.statSync(file).size;return {complete:bytes===m.size&&bytes>0,bytes};}
 const downloadProgress=()=>fs.readdirSync(dir).filter(n=>n.endsWith('.part')).sort().map(n=>[n,fs.statSync(path.join(dir,n)).size]);
 const service={ids,legacySourceIds,resolutionInfo:text=>resolvedInputs.get(String(text)),register,youtube,nativePart,localFile,verifyDownload,verifyAudio,prepare,ffmpeg,downloadProgress};g.mediaResolverService=service;return service;
}
