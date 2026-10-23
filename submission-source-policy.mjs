// Receipt acknowledgement is independent of source availability and assessment.
export const SOURCE_VERSION='submission-source-v1';
export const SOURCE_LABELS=Object.freeze({missing:'ĐÃ NỘP — Chưa có link',access:'ĐÃ NỘP — Link cần mở quyền xem',invalid:'ĐÃ NỘP — Link không hợp lệ',valid:'ĐÃ NỘP — Link hợp lệ',pending:'ĐÃ NỘP — Chờ kiểm tra link'});
export const normalizeInput=value=>String(value||'').replace(/\s+/g,' ').trim();
export function sourceResult(state,reason,extra={}){return {schema:1,version:SOURCE_VERSION,state,label:SOURCE_LABELS[state],aiEligible:state==='valid',reason,...extra};}
export function sourceFailure(error){
 const message=String(error?.message||error||''),code=Number(error?.httpCode||message.match(/(?:HTTP[_ ]|SOURCE_HTTP_)(\d{3})/)?.[1]||0);
 if(/rateLimitExceeded|quota|dailyLimit|too many requests/i.test(message)||code===429||code>=500)return sourceResult('pending','SOURCE_CHECK_RETRY');
 if(code===401||code===403||/SOURCE_ACCESS_REQUIRED|YOUTUBE_PRIVATE/.test(message))return sourceResult('access','ACCESS_DENIED');
 if(code===404||code===410||/SOURCE_INVALID|INVALID_DRIVE_LINK|INVALID_YOUTUBE|SOURCE_NOT_FOUND|PREFLIGHT_FILE_MISSING_OR_INVALID|UNSUPPORTED_MEDIA|SPEAKING_AUDIO_EMPTY/.test(message))return sourceResult('invalid','MISSING_OR_INVALID_FILE');
 // Quota/rate limits, transport errors and unsupported providers are not proof
 // of an invalid pupil link. Hold without a paid call; retry next scan.
 return sourceResult('pending',/UNSUPPORTED_LINK/.test(message)?'PROVIDER_NOT_SUPPORTED':'SOURCE_CHECK_RETRY');
}
export function sourceInput(text){
 const input=normalizeInput(text);if(!input)return sourceResult('missing','NO_LINK');
 const raw=input.match(/https?:\/\/[^\s<>"']+/gi)||[];
 if(!raw.length)return sourceResult('invalid','MALFORMED_URL');
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
  for(const id of files){const m=metadata(id);if(m.trashed||!Number(m.size))return sourceResult('invalid','EMPTY_OR_REMOVED_FILE');
   const mime=m.mimeType||m.mime;if(!/^(audio|video|image)\//.test(mime||'')&&mime!=='application/pdf'&&!/\.(?:mp4|mov|m4a|mp3|wav|aac|ogg|flac|webm)$/i.test(m.name||''))return sourceResult('invalid','UNSUPPORTED_FILE_FORMAT');
   const proof=service.verifyDownload({id,mime,size:Number(m.size),modified:m.modifiedTime||m.modified});
   if(!proof||proof.complete!==true||proof.bytes!==Number(m.size))return sourceResult('pending','DOWNLOAD_NOT_CONFIRMED');
   proofs.push({id,bytes:proof.bytes,modified:m.modifiedTime||m.modified});
  }
  return sourceResult('valid','DOWNLOAD_CONFIRMED',{files:proofs});
 }catch(error){return sourceFailure(error);}
}
export function assertSourceReady(result){if(result?.schema!==1||result.state!=='valid'||result.aiEligible!==true||!result.files?.length||result.files.some(f=>!(f.bytes>0)))throw Error('SOURCE_NOT_READY_FOR_AI');}
export function sourceNotice(result,time){return (result?.label||SOURCE_LABELS.pending)+(time?' · '+time:'');}
