import {createHash} from 'node:crypto';
import {returnedSpeakingGrade} from './speaking-returned-result-policy.mjs';
import {COMPACT_VERSION,compactResponse} from './master-compact-output.mjs';
import {isFoundation} from './speaking-master-policy.mjs';
export const REPAIR_AUTH='teacher-master-policy-correction-20261023';
// Explicit teacher-authorized, single linked correction for legacy failed output.
// Never mutate/reuse a parent's reservation, usage, counters, raw, or artifacts.
export function legacySpeakingRepairReason(job,raw){
 if(job.masterRepairOrigin||!job.rawId||compactResponse(raw))return null;
 if(raw?.candidates?.[0]?.finishReason==='MAX_TOKENS'){
  try{returnedSpeakingGrade(raw);return null;}catch{return 'LEGACY_TRUNCATED_RESPONSE';}
 }
 if(isFoundation(job.source?.code))try{const g=returnedSpeakingGrade(raw);if(!g.usable&&g.estimatedBand===null)return 'S01_FOUNDATION_PERCENT_POLICY';}catch{}
 return null;
}
export function enqueueSpeakingMasterRepairs(c,table,{inScope,isLatest,emit=()=>{}}){
 const all=c.isgJobs_(table),ids=new Set(all.map(x=>x.job.id));let count=0;
 for(const {job:parent}of all.slice()){
  if(!parent.rawId||parent.masterRepairOrigin||!inScope(parent)||!isLatest(parent.source))continue;
  const id=createHash('sha256').update(REPAIR_AUTH+'|'+parent.id).digest('hex');if(ids.has(id))continue;
  try{
   const target=c.isgTarget_(parent.source);if(c.isgHasFeedback_(target.text)||target.range.getFormula()||target.range.getDataValidation?.())continue;
   const reason=legacySpeakingRepairReason(parent,c.isgReadArtifact_(parent.rawId));if(!reason)continue;
   const child={id,source:structuredClone(parent.source),mode:'live',selectionPolicy:'NEW_SUBMISSION',status:'QUEUED',error:'',nextAt:0,masterRepairOrigin:{authorization:REPAIR_AUTH,parentId:parent.id,parentRawId:parent.rawId,reason,policy:COMPACT_VERSION},createdAt:new Date().toISOString()};
   c.isgSave_(table,table.getLastRow()+1,child);ids.add(id);count++;emit({event:'SPEAKING_MASTER_REPAIR_QUEUED',reason,providerCalls:0});
  }catch{/* Source/target uncertainty defers this record, never blocks another. */}
 }
 return {queued:count,providerCalls:0};
}
