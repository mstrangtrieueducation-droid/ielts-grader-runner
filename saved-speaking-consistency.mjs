// Offline repair of duplicate references inside an already-paid response.
// The detailed error is canonical; never invent times or relax the validator.
export function normalizeSavedSpeaking(raw){
 const candidate=raw?.candidates?.[0],parts=candidate?.content?.parts;
 if(!Array.isArray(parts))return {raw,changes:[]};
 const texts=parts.filter(p=>typeof p.text==='string'&&!p.thought);
 let grade;try{grade=JSON.parse(texts.map(p=>p.text).join(''));}catch{return {raw,changes:[]};}
 const errors=grade.pronunciation?.errors,evidence=grade.criterionScores?.pronunciation?.evidence;
 if(!Array.isArray(errors)||!Array.isArray(evidence))return {raw,changes:[]};
 const normal=s=>String(s||'').trim().toLowerCase().replaceAll('’',"'");
 const changes=[];
 for(const e of evidence){
  const matches=errors.filter(x=>x.fileIndex===e.fileIndex&&normal(x.word)===normal(e.quote));
  if(matches.length!==1)continue;
  const canonical=matches[0],coverage=grade.coverage?.find(x=>x.fileIndex===e.fileIndex);
  if(!coverage||!Number.isFinite(canonical.atSeconds)||canonical.atSeconds<0||canonical.atSeconds>coverage.durationSeconds)continue;
  if(Number.isFinite(e.atSeconds)&&Math.abs(e.atSeconds-canonical.atSeconds)<=2)continue;
  changes.push({kind:'DUPLICATE_WORD_REFERENCE',word:e.quote,fileIndex:e.fileIndex,from:e.atSeconds,to:canonical.atSeconds});
  e.atSeconds=canonical.atSeconds;
 }
 if(!changes.length)return {raw,changes};
 const copy=JSON.parse(JSON.stringify(raw)),out=copy.candidates[0].content.parts;
 let written=false;for(const p of out)if(typeof p.text==='string'&&!p.thought){p.text=written?'':JSON.stringify(grade);written=true;}
 return {raw:copy,changes};
}
