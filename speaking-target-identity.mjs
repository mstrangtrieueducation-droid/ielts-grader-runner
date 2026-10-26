import {normalizeName} from './master-policy.mjs';
// Reuse the native target resolver. Only a unique canonical roster name may
// replace a zero-match spelling for this lookup; source/signature stay intact.
export function installSpeakingTargetIdentity(c,{classes,tab},google){
 const native=c.isgTarget_;
 c.isgTarget_=source=>{
  try{return native(source);}catch(error){
   if(error.message!=='SPEAKING_STUDENT_AMBIGUOUS')throw error;
   const id=classes[source.className];if(!id)throw error;
   const sheet=google.book(id).getSheetByName(tab);if(!sheet)throw error;
   const rows=sheet.getRange(7,1,Math.max(1,sheet.getLastRow()-6),2).getDisplayValues(),names=rows.filter(r=>/^\d+$/.test(String(r[0]))&&Number(r[0])>0).map(r=>String(r[1]||'').split(/\r?\n/)[0]);
   // Never override a real exact-name ambiguity.
   if(names.some(name=>c.isgName_(name)===c.isgName_(source.name)))throw error;
   const key=normalizeName(source.name),hits=key?names.filter(name=>normalizeName(name)===key):[];
   if(hits.length!==1)throw error;
   return native({...source,name:hits[0]});
  }
 };
}
