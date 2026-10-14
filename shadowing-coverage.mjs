// Coverage must be stated by the model for EACH target, never inferred from
// omissions in a sparse list of errors. This module never invents verdicts.
export function checkShadowCoverage(grade, template) {
 const reasons=[];
 const ledger=grade.scoreLedger;
 for(const name of ['units','prosody','fluency']) {
  const block=ledger?.[name],targets=template?.[name]||block?.targets;
  if(!Array.isArray(targets)||!targets.length||typeof block?.outcomes!=='string'||block.outcomes.length!==targets.length||!/^[CIMU]+$/.test(block.outcomes)) {reasons.push(name+': missing explicit verdicts');continue;}
  const links=new Map((block.errors||[]).map(e=>[e.unitIndex,e]));
  for(let i=0;i<targets.length;i++) {
   const verdict=block.outcomes[i];
   if(verdict==='U')reasons.push(name+': unheard target '+i);
   if(verdict==='C'&&links.has(i)||['I','M'].includes(verdict)&&!links.get(i)?.evidenceIndexes?.length)reasons.push(name+': verdict/evidence mismatch '+i);
  }
  if(block.unclearIndexes?.length)reasons.push(name+': unclear targets');
 }
 if(ledger?.complete!==true||grade.uncertainty?.length)reasons.push('incomplete assessment');
 const phrases=template?.prosody||ledger?.prosody?.targets;
 const checks=ledger?.phraseChecks;
 if(!Array.isArray(checks)||checks.length!==phrases?.length)reasons.push('missing phrase alignment');
 else for(let i=0;i<checks.length;i++) {
  const c=checks[i];
  if(c.phraseIndex!==i||!/^\d{1,2}:[0-5]\d(?:\.\d+)?$/.test(c.time||'')||!c.heardStudentText?.trim())reasons.push('invalid phrase alignment '+i);
 }
 // Corrections that name additional problems must not disappear merely
 // because the model forgot to put them in the ledger.
 for(const [i,name]of ['units','prosody','fluency'].entries()) {
  const correction=grade.sections?.[i]?.correction?.trim();
  if(correction&&!ledger?.[name]?.errors?.length)reasons.push(name+': correction without linked evidence');
 }
 if(reasons.length) {
  grade.scoreQuality={status:'unscored',reasons:[...new Set(reasons)]};
  delete grade.scoreCalculation;
  for(const s of grade.sections||[])s.score=null;
 } else grade.scoreQuality={status:'verified-coverage'};
 return grade;
}
