import {isNativeYouTubePart,validateNativeYouTubePart} from './native-youtube.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {request} from './google-adapter.mjs';
import {extractStudentAudio} from './student-audio.mjs';

export const MIN_AUDIO_BYTES=10*1024;
export const AUDIO_GUARD_VERSION='disk-and-wire-audio-v1-20261014';
const digest=b=>createHash('sha256').update(b).digest('hex');
const fail=reason=>{throw Error('SYSTEM_AUDIO_INPUT_'+reason);};
export const audioPart=p=>/^audio\//.test(p?.inlineData?.mimeType||p?.fileData?.mimeType||'')||isNativeYouTubePart(p);
export function requireAudioFile(file){
 let stat;try{stat=fs.statSync(file);}catch{fail('FILE_MISSING');}
 if(!stat.isFile()||stat.size<=MIN_AUDIO_BYTES)fail('FILE_TOO_SMALL');
 return {file:path.resolve(file),bytes:stat.size,sha256:digest(fs.readFileSync(file))};
}
const safeId=m=>{if(!/^[\w-]+$/.test(m.id||''))fail('SOURCE_ID_INVALID');return m.id;};
export function audioPaths(m,root){
 const id=safeId(m),tag=id+'-'+digest(Buffer.from(String(m.modified))).slice(0,10),cache=path.join(root,'private','cache');
 return {cache,tag,original:path.join(cache,tag+'.original'),files:['.mp3','.flac','.m4a','.shadow.mp3'].map(e=>path.join(cache,tag+e))};
}
export function validateAudioPart(m,part,{root,materialize=false}={}){
 if(isNativeYouTubePart(part))return validateNativeYouTubePart(m,part);
 if(!audioPart(part))fail('PART_MISSING');
 const p=audioPaths(m,root);let bytes,proof;
 if(part.inlineData){
  const data=part.inlineData.data;if(typeof data!=='string'||!data||!/^[A-Za-z0-9+/]*={0,2}$/.test(data))fail('BASE64_INVALID');
  bytes=Buffer.from(data,'base64');if(bytes.length<=MIN_AUDIO_BYTES)fail('PAYLOAD_TOO_SMALL');
 }
 const files=[m.audioPayloadProof?.file,...p.files].filter(Boolean);
 for(const file of files)try{const f=requireAudioFile(file);if(!bytes||f.sha256===digest(bytes)){proof=f;break;}}catch{}
 if(!proof&&bytes&&materialize){
  const dir=path.join(root,'private','payload-audio');fs.mkdirSync(dir,{recursive:true});const file=path.join(dir,safeId(m)+'-'+digest(bytes).slice(0,16)+'.audio');fs.writeFileSync(file,bytes);proof=requireAudioFile(file);
 }
 if(!proof)fail('DISK_PAYLOAD_MISMATCH');
 if(part.fileData&&!/^https:\/\/generativelanguage\.googleapis\.com\//.test(part.fileData.fileUri||''))fail('FILE_URI_INVALID');
 m.audioPayloadProof={...proof,sourceId:m.id,mime:part.inlineData?.mimeType||part.fileData?.mimeType,uri:part.fileData?.fileUri||null,validatedAt:new Date().toISOString(),version:AUDIO_GUARD_VERSION};return proof;
}
// Repair is local extraction plus Drive reads; it never calls Gemini generation.
export function repairAudioLocally({m,job,g,root,ffmpeg,emit=()=>{},download=request,extract=extractStudentAudio}){
 const p=audioPaths(m,root);fs.mkdirSync(p.cache,{recursive:true});
 emit({event:'LOCAL_AUDIO_REPAIR_STARTED',id:job?.id,fileId:m.id});
 const fetchSource=()=>{
  const meta=g.fileMeta(m.id),size=Number(meta.size);if(meta.trashed||!size)fail('SOURCE_UNAVAILABLE');
  const temp=p.original+'.repair.part';
  try{const r=download({url:'https://www.googleapis.com/drive/v3/files/'+m.id+'?alt=media&supportsAllDrives=true',headers:{Authorization:'Bearer '+g.token()},outputFile:temp,timeoutMs:240000});if(r.getResponseCode()!==200||!fs.existsSync(temp)||fs.statSync(temp).size!==size)fail('SOURCE_DOWNLOAD_FAILED');fs.renameSync(temp,p.original);}catch(e){if(fs.existsSync(temp))fs.unlinkSync(temp);if(e.message.startsWith('SYSTEM_AUDIO_INPUT_'))throw e;fail('SOURCE_DOWNLOAD_FAILED');}
 };
 let out,last;for(let attempt=0;attempt<2;attempt++){
  try{if(attempt||!fs.existsSync(p.original))fetchSource();out=extract({ffmpeg,input:p.original,audio:path.join(p.cache,p.tag+'.m4a'),flac:path.join(p.cache,p.tag+'.flac'),canonicalFormat:'mp3'});requireAudioFile(out.file);break;}catch(e){last=e;out=null;}
 }
 if(!out)fail(last?.message==='AUDIO_NO_STREAM'?'SOURCE_HAS_NO_AUDIO':'LOCAL_REPAIR_FAILED');
 for(const k of ['runnerUpload','upload','localSilence','audioPayloadProof'])delete m[k];
 m.runnerAudio={...m.runnerAudio,mime:out.mime,bytes:fs.statSync(out.file).size,sha256:digest(fs.readFileSync(out.file))};m.localAudioRepair={at:new Date().toISOString(),version:AUDIO_GUARD_VERSION};
 emit({event:'LOCAL_AUDIO_REPAIR_COMPLETE',id:job?.id,fileId:m.id,bytes:m.runnerAudio.bytes});return out;
}
export function prepareAudioWithRepair({job,m,prepare,save,root,g,ffmpeg,emit=()=>{}}){
 let part,firstError;
 try{part=prepare();if(!part)return null;validateAudioPart(m,part,{root});return part;}catch(e){firstError=e;if(!/SYSTEM_AUDIO_INPUT_|AUDIO_|DRIVE_.*DOWNLOAD|PREFLIGHT_FILE_MISSING_OR_INVALID|MEDIA_PROCESSING_FAILED/.test(e.message))throw e;}
 try{repairAudioLocally({m,job,g,root,ffmpeg,emit});save();part=prepare();if(!part)return null;validateAudioPart(m,part,{root});save();return part;}catch(e){job.audioPayloadFailure={at:new Date().toISOString(),firstError:firstError.message,error:e.message,providerGenerateRequests:0};save();if(e.message.startsWith('SYSTEM_AUDIO_INPUT_'))throw e;fail('LOCAL_REPAIR_FAILED');}
}
export function assertAudioPayload(payload,job){
 const media=(job?.media||[]).filter(m=>!m.isReference),parts=(payload?.contents||[]).flatMap(c=>c.parts||[]),audio=parts.filter(audioPart);
 if(!media.length||audio.length!==media.length)fail('MISSING_STUDENT_AUDIO');
 const remaining=[...media];
 for(const part of audio){
  if(isNativeYouTubePart(part)){const i=remaining.findIndex(m=>m.nativeYouTube?.url===part.fileData.fileUri);if(i<0)fail('UNBOUND_NATIVE_MEDIA');validateNativeYouTubePart(remaining.splice(i,1)[0],part);continue;}
  const bytes=part.inlineData?Buffer.from(part.inlineData.data||'','base64'):null;if(bytes&&bytes.length<=MIN_AUDIO_BYTES)fail('PAYLOAD_TOO_SMALL');
  const match=remaining.findIndex(m=>{const p=m.audioPayloadProof;return p?.sourceId===m.id&&p.version===AUDIO_GUARD_VERSION&&p.mime===(part.inlineData?.mimeType||part.fileData?.mimeType)&&(bytes?p.sha256===digest(bytes):p.uri===part.fileData.fileUri);});
  if(match<0)fail('UNBOUND_AUDIO_PART');const m=remaining.splice(match,1)[0],disk=requireAudioFile(m.audioPayloadProof.file);if(disk.sha256!==m.audioPayloadProof.sha256)fail('FILE_CHANGED_BEFORE_SEND');
 }
 return {version:AUDIO_GUARD_VERSION,files:media.map(m=>m.nativeYouTube?{sourceId:m.id,sourceMode:'youtube_native',bytes:null,nativeYouTube:m.nativeYouTube}:{sourceId:m.id,bytes:m.audioPayloadProof.bytes,sha256:m.audioPayloadProof.sha256}),validatedAt:new Date().toISOString()};
}
export function validatedAudioRequest(payload,job){job.lastPayloadValidation=assertAudioPayload(payload,job);return JSON.stringify(payload);}
