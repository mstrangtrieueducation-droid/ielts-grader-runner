export function readSpeakingArtifact(google,controlId,id){
 if(!String(id).startsWith('runner:'))return JSON.parse(google.file(id).getBlob().getDataAsString());
 const sheet=google.book(controlId).getSheetByName('RunnerArtifacts');
 const index=sheet.getRange(1,1,sheet.getLastRow(),2).getValues();
 const parts=index.flatMap((r,i)=>r[0]===id?[{row:i+1,part:Number(r[1])}]:[]).sort((a,b)=>a.part-b.part);
 if(!parts.length)throw Error('SPEAKING_ARTIFACT_MISSING');
 let text='';for(let start=0;start<parts.length;start+=100){const selected=parts.slice(start,start+100),ranges=selected.map(p=>"'RunnerArtifacts'!C"+p.row);
  const values=google.api('https://sheets.googleapis.com/v4/spreadsheets/'+controlId+'/values:batchGet?'+ranges.map(r=>'ranges='+encodeURIComponent(r)).join('&')).valueRanges;
  if(values.length!==selected.length)throw Error('SPEAKING_ARTIFACT_MISSING');text+=values.map(r=>r.values?.[0]?.[0]??'').join('');
 }return JSON.parse(text);
}
