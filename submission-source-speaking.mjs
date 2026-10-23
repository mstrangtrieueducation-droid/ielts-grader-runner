import {inspectSubmissionSource,sourceInput,assertSourceReady} from './submission-source-policy.mjs';
import {publishSourceStatus} from './submission-source-store.mjs';
import {hasRequest,hasSavedResult} from './universal-media.mjs';
export function installSpeakingSourceGate(c,{g,service,sourceId,publish=publishSourceStatus}){
 const process=c.isgProcess_,generate=c.isgCallGemini_;
 c.isgProcess_=(table,item)=>{
  const j=item.job,s=j.source;
  if(!hasSavedResult(j)&&!hasRequest(j)){
   try{c.isgFresh_(s);}catch(e){j.status='RETRY';j.error='SOURCE_CHECK_RETRY';j.nextAt=Date.now()+300000;j.retryAt=new Date(j.nextAt).toISOString();c.isgSave_(table,item.row,j);return j;}
   if(typeof c.isgTarget_==='function'){const dst=c.isgTarget_(s);if(c.isgHasFeedback_?.(dst.text)||dst.range.getFormula()||dst.range.getDataValidation())return process(table,item);}
   const result=s.inputLinks?inspectSubmissionSource({text:s.inputLinks,service,metadata:id=>g.fileMeta(id)}):s.fileIds.length?inspectSubmissionSource({ids:s.fileIds,service,metadata:id=>g.fileMeta(id)}):sourceInput('');
   j.sourceIntake={...result,receivedAt:s.at};c.isgSave_(table,item.row,j);
   try{publish(g,sourceId,{sourceTab:s.sheetName,row:s.row,links:s.inputLinks||s.fileIds.map(id=>'https://drive.google.com/file/d/'+id+'/view').join(' '),code:s.code,student:s.name,className:s.className,time:s.at},result);delete j.sourceStatusWriteError;}catch{j.sourceStatusWriteError=true;}
   if(result.state!=='valid'){j.status='RETRY';j.error='SOURCE_INPUT_'+result.state.toUpperCase();j.nextAt=Date.now()+300000;j.retryAt=new Date(j.nextAt).toISOString();c.isgSave_(table,item.row,j);return j;}
  }
  return process(table,item);
 };
 c.isgCallGemini_=(j,...args)=>{if(!j.rawId)assertSourceReady(j.sourceIntake);return generate(j,...args);};
}
