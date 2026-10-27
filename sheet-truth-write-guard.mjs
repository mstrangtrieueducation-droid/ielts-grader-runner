// Fresh class-cell checks protect teacher edits before an absolute batch replay.
const canonical=x=>JSON.stringify(x===undefined?null:x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,JSON.parse(canonical(x[k]))])):Array.isArray(x)?x.map(v=>JSON.parse(canonical(v))):x);
const displayEvidence=c=>c?.formattedValue??c?.effectiveValue?.stringValue??c?.effectiveValue?.numberValue??c?.userEnteredValue?.stringValue??c?.userEnteredValue?.numberValue??'';
const headerMerges=(merges,col,limit)=>(merges||[]).filter(m=>(m.startRowIndex||0)<limit&&(m.startColumnIndex||0)<=col&&m.endColumnIndex>col).map(m=>[m.startRowIndex||0,m.endRowIndex,m.startColumnIndex||0,m.endColumnIndex]).sort((a,b)=>canonical(a).localeCompare(canonical(b)));
export function expectedBindings(sheet,master,row,col){const coords=new Map(),add=(r,c)=>{if(r===row&&c===col)return;const key=[sheet.getSheetId(),r,c].join('|');coords.set(key,{key,sheetId:sheet.getSheetId(),title:sheet.getName(),row:r,col:c,before:displayEvidence(master.cells[r]?.values?.[c])});};for(let c=0;c<3;c++){const v=String(displayEvidence(master.cells[row]?.values?.[c])||'');if(v.length<150&&!/NHẬN XÉT GV|ĐÃ NỘP|%|https?:|CẦN NỘP LẠI/.test(v))add(row,c);}const limit=Math.min(row,Math.max(1,Math.min(5,sheet.meta.properties.gridProperties.frozenRowCount||4)));for(let r=0;r<limit;r++)add(r,col);for(const m of sheet.meta.merges||[])if((m.startRowIndex||0)<limit&&(m.startColumnIndex||0)<=col&&m.endColumnIndex>col)add(m.startRowIndex||0,m.startColumnIndex||0);return {bindings:[...coords.values()],headerLimit:limit,headerMerges:headerMerges(sheet.meta.merges,col,limit)};}
export const cellEvidence=c=>({value:c?.userEnteredValue||null,validation:c?.dataValidation||null,note:c?.note||null});
export function classWritePlan(requests,expected,current){
 const bad=new Set(expected.filter(e=>canonical({...e.before,note:e.before?.note||null})!==canonical(cellEvidence(current.get(e.key)))||(e.bindings||[]).some(b=>canonical(b.before)!==canonical(displayEvidence(current.get(b.key))))||e.headerMerges&&current.merges&&canonical(e.headerMerges)!==canonical(headerMerges(current.merges.get(e.sheetId),e.col,e.headerLimit))).map(e=>e.key));
 const touches=(r,e)=>{const a=r.updateCells?.range||r.repeatCell?.range;return a&&a.sheetId===e.sheetId&&e.row>=(a.startRowIndex||0)&&e.row<(a.endRowIndex??Infinity)&&e.col>=(a.startColumnIndex||0)&&e.col<(a.endColumnIndex??Infinity);};
 return {requests:requests.filter(r=>!expected.some(e=>bad.has(e.key)&&touches(r,e))),conflicts:expected.filter(e=>bad.has(e.key)).map(e=>({...e,current:current.get(e.key)||{}}))};
}
const letters=c=>{let s='';for(c++;c;c=Math.floor((c-1)/26))s=String.fromCharCode(65+(c-1)%26)+s;return s;};
export function guardClassRequests(g,id,requests,expected){
 if(!expected?.length)return {requests:[],conflicts:[]};const current=new Map();current.merges=new Map();const unique=new Map();for(const e of expected)for(const v of [e,...(e.bindings||[])])unique.set(v.key,v);const coordinates=[...unique.values()];
 const groups=[];let pending=[],encodedLength=0;for(const e of coordinates){const length=encodeURIComponent("'"+e.title.replaceAll("'","''")+"'!"+letters(e.col)+(e.row+1)).length+8;if(pending.length&&(encodedLength+length>5500||pending.length>=50)){groups.push(pending);pending=[];encodedLength=0;}pending.push(e);encodedLength+=length;}if(pending.length)groups.push(pending);
 for(const group of groups){const ranges=group.map(e=>"'"+e.title.replaceAll("'","''")+"'!"+letters(e.col)+(e.row+1)),data=g.api('https://sheets.googleapis.com/v4/spreadsheets/'+id+'?'+ranges.map(r=>'ranges='+encodeURIComponent(r)).join('&')+'&includeGridData=true&fields=sheets(properties(sheetId),merges,data(startRow,startColumn,rowData(values(userEnteredValue,effectiveValue,formattedValue,dataValidation,note))))');
  for(const s of data.sheets||[])current.merges.set(s.properties.sheetId,s.merges||[]);for(const s of data.sheets||[])for(const b of s.data||[])for(let y=0;y<(b.rowData||[]).length;y++)for(let x=0;x<(b.rowData[y].values||[]).length;x++)current.set([s.properties.sheetId,(b.startRow||0)+y,(b.startColumn||0)+x].join('|'),b.rowData[y].values[x]);
 }
 // Sheets returns only merges intersecting each requested range set. The last
 // coordinate chunk is not the complete header structure of the class. Read
 // current merge metadata once after all chunks; never treat an omitted merge
 // in the last chunk as a teacher edit, or retain a merge that was removed.
 if(expected.some(e=>Array.isArray(e.headerMerges))){const metadata=g.api('https://sheets.googleapis.com/v4/spreadsheets/'+id+'?fields=sheets(properties(sheetId),merges)');current.merges.clear();for(const s of metadata.sheets||[])current.merges.set(s.properties.sheetId,s.merges||[]);}
 return classWritePlan(requests,expected,current);
}
