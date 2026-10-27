import {NATIVE_YOUTUBE_VERSION,nativeInputIdentity,assertNativeEvidence} from './native-youtube.mjs';
import {speakingHeaderIndices} from './speaking-source-headers.mjs';
import {speakingRetryAllowed} from './speaking-provider-retry.mjs';
import fs from 'node:fs';
import {PREPROCESS_VERSION,firstUniversalPart,hasSavedResult,hasRequest,isTransient,retryPreparation,EMPTY_LINK_NOTICE,YOUTUBE_NOTICE} from './universal-media.mjs';
import {resumeUncalledPreprocessing} from './automatic-preprocessing.mjs';
import {sourceInMasterScope} from './master-submission-scope.mjs';

export function installSpeakingMedia(c,{g,service,nativeResubmission,approval:session=()=>null}){
 const cfg=JSON.parse(c.PropertiesService.getScriptProperties().getProperty('IELTS_SPEAKING_NATIVE_CONFIG'));
 const hash=c.isgHash_;c.isgHash_=value=>{
  if(value&&value.guide&&Array.isArray(value.media))return hash({...value,media:value.media.map(m=>m.nativeYouTube?nativeInputIdentity(m):m.preprocessVersion===PREPROCESS_VERSION?{id:m.originalSourceId||m.id,modified:m.modified,originalSize:m.universalAudio?.sourceSize,mime:'audio/mpeg',preprocessing:PREPROCESS_VERSION}:m)});
  return hash(value);
 };
 const oldIds=c.isgDriveIds_;c.isgDriveIds_=text=>{try{return service.legacySourceIds?service.legacySourceIds(text):service.ids(text);}catch{return oldIds(text);}};
 // Preserve existing Drive-only source objects/signatures exactly. The old
 // scanner omitted empty attachments completely, so append only those rows.
 const sourceInputs=new Map();c.isgSourceInput_=s=>sourceInputs.get(s.sheetName+'|'+s.row);
 const sourceRows=c.isgSourceRows_;c.isgSourceRows_=()=>{
  const rows=sourceRows();
  for(const name of cfg.sourceTabs){const sheet=g.book(cfg.source).getSheetByName(name),values=sheet.getDataRange().getValues();if(values.length<2)continue;let ix;try{ix=speakingHeaderIndices(values[0]);}catch{continue;}const audio=ix.audio;
   if(Object.values(ix).some(i=>i<0)||!audio.length)continue;
   for(let i=1;i<values.length;i++){const r=values[i];sourceInputs.set(name+'|'+(i+1),audio.map(col=>String(r[col]||'')).join(' ').trim());if(rows.some(s=>s.sheetName===name&&s.row===i+1))continue;const className=c.isgClass_(r[ix.className]),code=c.isgCode_(r[ix.code]),at=r[ix.time];if(!cfg.classes[className]||!code||!(at instanceof Date)||!Number.isFinite(at.getTime())||!String(r[ix.name]||'').trim())continue;const s={sheetId:sheet.getSheetId(),sheetName:name,row:i+1,className,code,name:String(r[ix.name]).trim(),at:at.toISOString(),fileIds:[]};const inputLinks=audio.map(col=>String(r[col]||'')).join(' ').trim();if(inputLinks)s.inputLinks=inputLinks;s.signature=c.isgHash_(s);rows.push(s);}
  }return rows.sort((a,b)=>b.at.localeCompare(a.at)||b.row-a.row);
 };
 const mediaCache=new Map();
 c.isgMedia_=source=>{
  const text=c.isgSourceInput_(source)??source.inputLinks??source.fileIds.map(id=>id.startsWith('yt_')?'https://www.youtube.com/watch?v='+id.slice(3):'https://drive.google.com/file/d/'+id+'/view').join(' '),resolvedIds=service.ids(text);if(!resolvedIds.length)throw Error('SPEAKING_AUDIO_EMPTY');
  const out=[];for(const id of resolvedIds){const meta=g.fileMeta(id);if(meta.nativeYouTube){assertNativeEvidence(meta.nativeYouTube,{id});out.push({id,mime:'video/mp4',size:0,modified:meta.modifiedTime,nativeYouTube:meta.nativeYouTube,preprocessVersion:NATIVE_YOUTUBE_VERSION});continue;}if(meta.trashed||!Number(meta.size))throw Error('SPEAKING_AUDIO_EMPTY');const key=[id,meta.modifiedTime,meta.size].join('|');if(!mediaCache.has(key)){
   const m={id,mime:meta.mimeType,size:Number(meta.size),modified:meta.modifiedTime},audio=service.prepare(m,{fileApi:resolvedIds.length>2});
   const prepared={id,size:audio.segments[0].bytes,modified:meta.modifiedTime,mime:'audio/mpeg',universalFile:audio.segments[0].file,originalSourceId:id,preprocessVersion:PREPROCESS_VERSION};firstUniversalPart(prepared,audio);mediaCache.set(key,[prepared]);
  }out.push(...mediaCache.get(key).map(m=>({...m})));}return out;
 };
 c.isgNativeYouTubePart_=m=>service.nativePart(m);
 c.isgAudioBytes_=m=>{if(!m.universalFile)throw Error('SPEAKING_PREPARED_AUDIO_MISSING');return [...fs.readFileSync(m.universalFile)];};
 const prompt=c.isgPrompt_;c.isgPrompt_=(guide,count)=>prompt(guide,count)+'\nCác FILE có thể là các đoạn chia đều từ cùng một video/audio dài. Nghe đủ các đoạn theo thứ tự; không coi ranh giới chia tệp kỹ thuật là học sinh ngập ngừng. Mốc thời gian tính riêng từng FILE như schema.';
 let approval;const process=c.isgProcess_;c.isgProcess_=(table,item)=>{
  const j=item.job,save=()=>c.isgSave_(table,item.row,j);approval=session();
  if(j.source.fileIds.some(id=>id.startsWith('yt_'))&&!hasSavedResult(j)&&!hasRequest(j)&&j.inputHash&&j.nativeInputVersion!==NATIVE_YOUTUBE_VERSION){j.preprocessHistory=(j.preprocessHistory||[]).concat([{inputHash:j.inputHash,inputId:j.inputId,at:new Date().toISOString(),reason:NATIVE_YOUTUBE_VERSION}]);delete j.inputHash;delete j.inputId;j.nativeInputVersion=NATIVE_YOUTUBE_VERSION;save();}
  if(sourceInMasterScope(j.source)&&!hasSavedResult(j)&&!hasRequest(j)&&!j.source.fileIds.length&&!String(c.isgSourceInput_(j.source)??j.source.inputLinks??'').trim()){
   c.isgFresh_(j.source);const dst=c.isgTarget_(j.source);if(c.isgHasFeedback_(dst.text)||dst.range.getFormula()||dst.range.getDataValidation())return process(table,item);
   nativeResubmission(j,dst.range,save,approval,EMPTY_LINK_NOTICE,'COMPLETED_NEEDS_RESUBMISSION');return j;
  }
  if(!hasSavedResult(j)&&j.inputHash&&j.preprocessInputVersion!==PREPROCESS_VERSION&&(!hasRequest(j)||speakingRetryAllowed(j))){j.preprocessHistory=(j.preprocessHistory||[]).concat([{inputHash:j.inputHash,inputId:j.inputId,at:new Date().toISOString(),reason:PREPROCESS_VERSION}]);delete j.inputHash;delete j.inputId;j.preprocessInputVersion=PREPROCESS_VERSION;save();}
  const result=process(table,item);
  if(!hasSavedResult(j)&&!hasRequest(j)&&/YOUTUBE_UNAVAILABLE/.test(j.internalDiagnostic||j.error||'')){
   j.error='TRANSIENT_MEDIA_YOUTUBE_OUTPUT_MISSING';retryPreparation(j,save);
  }else if(!hasSavedResult(j)&&!hasRequest(j)&&isTransient(j.internalDiagnostic||j.error||''))retryPreparation(j,save);
  return result;
 };
 return {recover(items,save,isLatest){return resumeUncalledPreprocessing(items,{isLatest,save,readyStatus:'QUEUED'});}};
}
