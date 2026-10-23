import {inspectSubmissionSource,assertSourceReady,normalizeInput,SOURCE_VERSION} from './submission-source-policy.mjs';
import {publishSourceStatus} from './submission-source-store.mjs';
import {hasRequest,hasSavedResult} from './universal-media.mjs';
export function installSubmissionSourceGate(c,{g,service,sourceId,isLatest,publish=publishSourceStatus}){
 const step=c.step_,generate=c.generate_;
 c.step_=(j,row,...args)=>{
  if(hasSavedResult(j)||hasRequest(j))return step(j,row,...args);
  if(!isLatest(j))return;
  if(typeof c.destination_==='function'){const cell=c.destination_(j.cls,j.route,j.receipt.student).cell;if(cell.getFormula?.()||cell.getDataValidation?.()||c.hasFeedback_?.(cell.getDisplayValue()))return step(j,row,...args);}
  const result=inspectSubmissionSource({text:j.receipt.links,service,metadata:id=>g.fileMeta(id)});
  j.sourceIntake={...result,input:normalizeInput(j.receipt.links),receivedAt:j.receipt.time};
  c.persist_(j,row);
  // Publication failure must not discard acknowledgement or permit paid work.
  try{publish(g,sourceId,j.receipt,result);delete j.sourceStatusWriteError;}catch{j.sourceStatusWriteError=true;}
  if(result.state!=='valid'){j.status='WAITING_INPUT';j.error='SOURCE_INPUT_'+result.state.toUpperCase();j.nextAt=Date.now()+300000;c.persist_(j,row);return;}
  c.persist_(j,row);return step(j,row,...args);
 };
 c.generate_=(j,...args)=>{
  if(!j.rawId&&!j.gradeId){assertSourceReady(j.sourceIntake);if(j.sourceIntake.input!==normalizeInput(j.receipt.links))throw Error('SOURCE_INPUT_CHANGED');}
  return generate(j,...args);
 };
 c.submissionSourceVersion_=SOURCE_VERSION;
}
