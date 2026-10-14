import {createHash} from 'node:crypto';
// Additive teacher policy: retain returned marks/prose despite ancillary metadata errors.
export function returnedSpeakingGrade(data){
 let text=(data?.candidates?.[0]?.content?.parts||[]).filter(p=>!p.thought&&typeof p.text==='string').map(p=>p.text).join('').trim();
 text=text.replace(/^```(?:json)?\s*/i,'').replace(/\s*```$/,'');const g=JSON.parse(text);
 if(typeof g.usable!=='boolean'||!g.pronunciation||!['fluency','lexical','grammar'].every(k=>g[k]&&typeof g[k]==='object'))throw Error('SPEAKING_RESULT_CONTENT_MISSING');
 if(g.usable&&(typeof g.estimatedBand!=='number'||!Number.isFinite(g.estimatedBand)||g.estimatedBand<0||g.estimatedBand>9))throw Error('SPEAKING_RESULT_SCORE_MISSING');
 const meaningful=[...(g.pronunciation.praise||[]),...(g.pronunciation.errors||[]).map(e=>e.error),...['fluency','lexical','grammar'].flatMap(k=>[g[k].observation,...(g[k].praise||[]),...(g[k].corrections||[])])].some(x=>typeof x==='string'&&x.trim());
 if(!meaningful)throw Error('SPEAKING_RESULT_CONTENT_MISSING');
 g.limitation??='';g.advice??=[];g.pronunciation.praise??=[];g.pronunciation.errors??=[];
 for(const key of ['endings','stress','intonation','fewerThanThreeReason'])g.pronunciation[key]??='';
 for(const e of g.pronunciation.errors)for(const k of ['word','ipa','heard','error','correction','errorType'])e[k]??='';
 for(const k of ['fluency','lexical','grammar']){g[k].praise??=[];g[k].corrections??=[];g[k].observation??='';}
 return g;
}
export function installReturnedSpeakingPolicy(c){
 const parse=c.isgParseResponse_;c.isgParseResponse_=(...args)=>{try{return parse(...args);}catch(original){try{return returnedSpeakingGrade(args[0]);}catch{throw original;}}};
 c.isgWrite_=(job,rich)=>{
  c.isgAssert_(c.isgScopeAllows_(job.source),'SPEAKING_OUTSIDE_HOMEWORK_SCOPE');
  if(job.selectionPolicy==='LATEST_STUDENT_CATCHUP')c.isgAssert_(c.isgIsLatestStudent_(job.source),'SPEAKING_SUPERSEDED_SUBMISSION');
  const target=c.isgTarget_(job.source);
  if(c.isgHasFeedback_(target.text))return 'SKIPPED_EXISTING_FEEDBACK';
  c.isgAssert_(target.spreadsheetId===job.target.spreadsheetId&&target.address===job.target.address&&target.text===job.target.text&&target.note===job.target.note,'SPEAKING_TARGET_CHANGED');
  c.isgAssert_(!target.range.getFormula(),'SPEAKING_TARGET_CHANGED');
  target.range.setRichTextValue(rich);job.resultHash=createHash('sha256').update(JSON.stringify(rich.getText())).digest('hex');job.deliveryPolicy='teacher-ram-batch-no-note-mutation-20261015';
  return 'DONE';
 };
}
