// Resolve semantic headers without guessing ambiguous columns or changing rows.
export const sourceHeaderNorm=v=>String(v??'').normalize('NFD').replace(/\p{M}/gu,'').replace(/[đĐ]/g,'d').replace(/\s+/g,' ').trim().toUpperCase();
export function speakingHeaderIndices(headers){
 const h=headers.map(sourceHeaderNorm),pick=(exact,pattern)=>{let hits=h.flatMap((v,i)=>exact.includes(v)?[i]:[]);if(!hits.length)hits=h.flatMap((v,i)=>pattern.test(v)?[i]:[]);if(hits.length!==1)throw Error('SPEAKING_SOURCE_HEADER_'+(hits.length?'AMBIGUOUS':'MISSING'));return hits[0];};
 return {time:pick(['DAU THOI GIAN'],/THOI GIAN|NGAY.*NOP|TIMESTAMP/),name:pick(['HO VA TEN DAY DU'],/HO.*TEN|TEN HOC (?:SINH|VIEN)|FULL NAME/),className:pick(['LOP'],/^(?:TEN )?LOP(?: HOC)?$|^CLASS$/),code:pick(['MA BAI'],/MA.*BAI|MA.*BUOI|^BUOI(?: HOC)?$|ASSIGNMENT.*CODE/),audio:h.flatMap((v,i)=>/FILE GHI AM|GHI AM PHAN [12]|^(?:LINK|TEP|FILE)(?: (?:AUDIO|VIDEO|BAI NOP|GHI AM))?$/.test(v)?[i]:[])};
}
export function installSpeakingSourceHeaders(c,{emit=()=>{}}={}){
 const cfg=JSON.parse(c.PropertiesService.getScriptProperties().getProperty('IELTS_SPEAKING_NATIVE_CONFIG'));
 c.isgSourceRows_=()=>{
  c.speakingSourceScanIncomplete_=false;const out=[];for(const [ordinal,name]of cfg.sourceTabs.entries()){
   const sheet=c.SpreadsheetApp.openById(cfg.source).getSheetByName(name);if(!sheet){c.speakingSourceScanIncomplete_=true;emit({event:'SPEAKING_SOURCE_DEFERRED',tab:ordinal,reason:'TAB_MISSING'});continue;}
   const rows=sheet.getDataRange().getValues();if(rows.length<2)continue;let ix;
   try{ix=speakingHeaderIndices(rows[0]);if(!ix.audio.length)throw Error('SPEAKING_AUDIO_HEADER_MISSING');}catch(e){c.speakingSourceScanIncomplete_=true;emit({event:'SPEAKING_SOURCE_DEFERRED',tab:ordinal,reason:e.message});continue;}
   for(let i=1;i<rows.length;i++){const r=rows[i],className=c.isgClass_(r[ix.className]),code=c.isgCode_(r[ix.code]),at=typeof r[ix.time]==='number'?new Date(Math.round((r[ix.time]-25569)*86400000)-25200000):r[ix.time];if(!cfg.classes[className]||!code)continue;
    if(!(at instanceof Date)||!Number.isFinite(at.getTime())){emit({event:'SPEAKING_SOURCE_DEFERRED',tab:ordinal,reason:'TIMESTAMP_INVALID'});continue;}
    const ids=Array.from(new Set(ix.audio.flatMap(k=>c.isgDriveIds_(r[k]))));if(!ids.length)continue;
    const s={sheetId:sheet.getSheetId(),sheetName:name,row:i+1,className,code,name:String(r[ix.name]??'').trim(),at:at.toISOString(),fileIds:ids};s.signature=c.isgHash_(s);out.push(s);
   }
  }return out.sort((a,b)=>b.at.localeCompare(a.at)||b.row-a.row);
 };
}
