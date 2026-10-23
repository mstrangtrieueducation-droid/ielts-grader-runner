// Fresh class-cell checks protect teacher edits before an absolute batch replay.
const canonical=x=>JSON.stringify(x===undefined?null:x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,JSON.parse(canonical(x[k]))])):Array.isArray(x)?x.map(v=>JSON.parse(canonical(v))):x);
export const cellEvidence=c=>({value:c?.userEnteredValue||null,validation:c?.dataValidation||null});
export function classWritePlan(requests,expected,current){
 const bad=new Set(expected.filter(e=>canonical(e.before)!==canonical(cellEvidence(current.get(e.key)))).map(e=>e.key));
 const touches=(r,e)=>{const a=r.updateCells?.range||r.repeatCell?.range;return a&&a.sheetId===e.sheetId&&e.row>=(a.startRowIndex||0)&&e.row<(a.endRowIndex??Infinity)&&e.col>=(a.startColumnIndex||0)&&e.col<(a.endColumnIndex??Infinity);};
 return {requests:requests.filter(r=>!expected.some(e=>bad.has(e.key)&&touches(r,e))),conflicts:expected.filter(e=>bad.has(e.key)).map(e=>({...e,current:current.get(e.key)||{}}))};
}
const letters=c=>{let s='';for(c++;c;c=Math.floor((c-1)/26))s=String.fromCharCode(65+(c-1)%26)+s;return s;};
export function guardClassRequests(g,id,requests,expected){
 if(!expected?.length)return {requests:[],conflicts:[]};const current=new Map();
 for(let start=0;start<expected.length;start+=100){const group=expected.slice(start,start+100),ranges=group.map(e=>"'"+e.title.replaceAll("'","''")+"'!"+letters(e.col)+(e.row+1)),data=g.api('https://sheets.googleapis.com/v4/spreadsheets/'+id+'?'+ranges.map(r=>'ranges='+encodeURIComponent(r)).join('&')+'&includeGridData=true&fields=sheets(properties(sheetId),data(startRow,startColumn,rowData(values(userEnteredValue,dataValidation))))');
  for(const s of data.sheets||[])for(const b of s.data||[])for(let y=0;y<(b.rowData||[]).length;y++)for(let x=0;x<(b.rowData[y].values||[]).length;x++)current.set([s.properties.sheetId,(b.startRow||0)+y,(b.startColumn||0)+x].join('|'),b.rowData[y].values[x]);
 }return classWritePlan(requests,expected,current);
}
