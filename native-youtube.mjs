// Teacher-approved source adapter, 24 October 2026. Never generates an assessment.
import {createHash} from 'node:crypto';
import {request} from './google-adapter.mjs';
export const NATIVE_YOUTUBE_VERSION='teacher-native-youtube-20261024';
export const NATIVE_PROOF_TTL=15*60000;
const issued=new Map(),sha=x=>createHash('sha256').update(JSON.stringify(x)).digest('hex');
export const nativeYoutubeEnabled=()=>process.env.NATIVE_YOUTUBE_INPUT==='true';
export function nativeYoutubeUrl(id){if(!/^yt_[A-Za-z0-9_-]{11}$/.test(id||''))throw Error('INVALID_YOUTUBE_ID');return 'https://www.youtube.com/watch?v='+id.slice(3);}
export const isNativeYouTubePart=p=>p?.fileData?.mimeType==='video/mp4'&&/^https:\/\/www\.youtube\.com\/watch\?v=[A-Za-z0-9_-]{11}$/.test(p.fileData.fileUri||'');
export function checkNativeYouTube(id,{key,model='gemini-3.8-flash',transport=request,now=Date.now()}={}){
 const url=nativeYoutubeUrl(id);if(!key||model!=='gemini-3.8-flash')throw Error('TRANSIENT_MEDIA_YOUTUBE_NATIVE_CONFIG');
 const response=transport({url:'https://generativelanguage.googleapis.com/v1beta/models/'+model+':countTokens',method:'POST',headers:{'Content-Type':'application/json','x-goog-api-key':key},body:JSON.stringify({contents:[{role:'user',parts:[{text:'Media input preflight.'},{fileData:{mimeType:'video/mp4',fileUri:url}}]}]}),timeoutMs:30000});
 if(response.getResponseCode()!==200)throw Error('TRANSIENT_MEDIA_YOUTUBE_NATIVE_INPUT_UNAVAILABLE');
 let result;try{result=JSON.parse(response.getContentText());}catch{throw Error('TRANSIENT_MEDIA_YOUTUBE_NATIVE_INPUT_UNAVAILABLE');}
 const counts=result.promptTokensDetails||[],sum=kind=>counts.filter(x=>x.modality===kind).reduce((n,x)=>n+Number(x.tokenCount||0),0),audioTokens=sum('AUDIO'),videoTokens=sum('VIDEO');
 if(!(audioTokens>0&&videoTokens>0&&Number(result.totalTokens)>audioTokens&&Number(result.totalTokens)>=audioTokens+videoTokens))throw Error('TRANSIENT_MEDIA_YOUTUBE_NATIVE_MODALITIES_UNCONFIRMED');
 const identity=sha({id,url,model,audioTokens,videoTokens}),proof={version:NATIVE_YOUTUBE_VERSION,id,url,model,audioTokens,videoTokens,totalTokens:Number(result.totalTokens),keyHash:sha(key),identity,checkedAt:now};proof.digest=sha(proof);issued.set(proof.digest,JSON.stringify(proof));return proof;
}
export function assertNativeEvidence(proof,{id=proof?.id,now=Date.now()}={}){
 if(!nativeYoutubeEnabled()||!proof||proof.version!==NATIVE_YOUTUBE_VERSION||proof.id!==id||proof.url!==nativeYoutubeUrl(id)||proof.model!=='gemini-3.8-flash'||!(proof.audioTokens>0&&proof.videoTokens>0)||!Number.isFinite(proof.checkedAt)||now<proof.checkedAt||now-proof.checkedAt>NATIVE_PROOF_TTL||issued.get(proof.digest)!==JSON.stringify(proof))throw Error('TRANSIENT_MEDIA_YOUTUBE_NATIVE_PROOF_REQUIRED');
 return proof;
}
export function validateNativeYouTubePart(m,part){const proof=assertNativeEvidence(m?.nativeYouTube,{id:m?.id});if(!isNativeYouTubePart(part)||part.fileData.fileUri!==proof.url||m.modified!==proof.identity)throw Error('TRANSIENT_MEDIA_YOUTUBE_NATIVE_BINDING');return proof;}
export function nativeYouTubePart(m){const part={fileData:{mimeType:'video/mp4',fileUri:nativeYoutubeUrl(m.id)}};validateNativeYouTubePart(m,part);return part;}
export function refreshNativeIntake(job,m){const p=assertNativeEvidence(m.nativeYouTube,{id:m.id}),f=job.sourceIntake?.files?.find(x=>x.id===m.id);if(f){if(f.nativeYouTube?.identity!==p.identity)throw Error('SOURCE_INPUT_CHANGED');f.nativeYouTube=p;}}
export const nativeInputIdentity=m=>m.nativeYouTube?{id:m.id,modified:m.modified,mime:m.mime,nativeIdentity:m.nativeYouTube.identity}:m;
