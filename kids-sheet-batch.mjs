import {sheetTruthEnabled} from './sheet-truth-state.mjs';
import {cellEvidence,guardClassRequests} from './sheet-truth-write-guard.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {Book,Range,Sheet,gridMaster} from './google-adapter.mjs';
const clone=x=>JSON.parse(JSON.stringify(x));
const typed=v=>v instanceof Date?{stringValue:v.toISOString()}:typeof v==='number'?{numberValue:v}:typeof v==='boolean'?{boolValue:v}:{stringValue:String(v??'')};
let installed=false;
export function installBatchAdapter(){
 if(installed)return;installed=true;
 const set=Range.prototype.setValues,append=Sheet.prototype.appendRows,batch=Book.prototype.batch;
 Range.prototype.setValues=function(values){if(!this.sheet.book.ramBatch)return set.call(this,values);this.sheet.book.ramBatch.stage(this.sheet.book,{updateCells:{range:{sheetId:this.sheet.getSheetId(),startRowIndex:this.r-1,endRowIndex:this.r+this.nr-1,startColumnIndex:this.c-1,endColumnIndex:this.c+this.nc-1},rows:values.map(row=>({values:row.map(v=>({userEnteredValue:typed(v)}))})),fields:'userEnteredValue'}});return this;};
 Sheet.prototype.appendRows=function(values){if(!this.book.ramBatch)return append.call(this,values);const row=this.getLastRow()+1;this.lastAppendRow=row;this.getRange(row,1,values.length,Math.max(...values.map(r=>r.length))).setValues(values);return this;};
 Book.prototype.batch=function(requests){if(!this.ramBatch)return batch.call(this,requests);for(const r of requests)this.ramBatch.stage(this,r);return {};};
}
export function replaySheetBatches(g,cluster,journalDir,{emit=()=>{}}={}){
 fs.mkdirSync(journalDir,{recursive:true});
 // Replay durable, absolute-cell updates before reading Jobs or spending on API.
 for(const file of fs.readdirSync(journalDir).filter(f=>f.startsWith(cluster.controlId+'-')&&f.endsWith('.json'))){
  const p=path.join(journalDir,file),saved=JSON.parse(fs.readFileSync(p,'utf8'));
  for(const item of saved.books){if(sheetTruthEnabled()&&cluster.classes.some(c=>c.spreadsheetId===item.id)){const plan=guardClassRequests(g,item.id,item.requests,item.expected||[]);item.requests=plan.requests;if(!item.requests.length)continue;}g.api('https://sheets.googleapis.com/v4/spreadsheets/'+item.id+':batchUpdate','POST',{requests:item.requests});g.books.get(item.id)?.cache.clear();}
  fs.unlinkSync(p);emit({event:'SHEET_BATCH_REPLAYED',file});
 }
}
export function beginSheetBatch(g,cluster,journalDir,{emit=()=>{}}={}){
 installBatchAdapter();replaySheetBatches(g,cluster,journalDir,{emit});
 const active=new Map(),originalBook=g.book,originalPreload=g.preloadSource,sourceReads=new Set(),journal=path.join(journalDir,cluster.controlId+'-'+Date.now()+'.json');
 const ids=new Set([cluster.controlId,...cluster.classes.map(c=>c.spreadsheetId)]);
 const writeJournal=()=>{const books=[...active.values()].filter(b=>b.requests.length).sort((a,b)=>(a.book.id===cluster.controlId?1:0)-(b.book.id===cluster.controlId?1:0)).map(b=>({id:b.book.id,requests:b.requests,...(sheetTruthEnabled()?{expected:[...b.expected.values()]}:{})}));if(books.length){const temp=journal+'.tmp';fs.writeFileSync(temp,JSON.stringify({at:new Date().toISOString(),books}));fs.renameSync(temp,journal);}};
 function load(id){
  if(active.has(id))return active.get(id).book;
  const names=id===cluster.controlId?(g.books.get(id)?.sheets||[]).map(s=>s.getName()).filter(n=>['Jobs','RunnerArtifacts','Audit','Automation','RunnerReferences','[CẦN_CÔ_GÁN_CỘT_HOẶC_TÊN]'].includes(n)):cluster.classes.filter(c=>c.spreadsheetId===id).map(c=>c.sheetName).filter(Boolean);
  const scopedRanges=names.map(n=>'&ranges='+encodeURIComponent("'"+n.replaceAll("'","''")+"'")).join('');
  const data=g.api('https://sheets.googleapis.com/v4/spreadsheets/'+id+'?includeGridData=true'+scopedRanges+'&fields=spreadsheetId,properties(title),sheets(properties,merges,data(rowData(values(effectiveValue,userEnteredValue,formattedValue,hyperlink,textFormatRuns,userEnteredFormat,dataValidation,note))))');
  const book=g.books.get(id)||Object.assign(Object.create(Book.prototype),{g,id,cache:new Map()});
  if(!book.sheets){book.meta=data;book.sheets=data.sheets.map(s=>new Sheet(book,s));g.books.set(id,book);}
  book.cache.clear();for(const s of data.sheets){if(!s.data?.length)continue;const sheet=book.getSheetByName(s.properties.title);if(!sheet)throw Error('BATCH_SHEET_METADATA_CHANGED');book.cache.set(sheet.getName()+'|master',gridMaster(s.data?.[0]?.rowData||[],s.properties.gridProperties.columnCount));}
  const item={book,requests:[],expected:new Map(),clear:book.cache.clear,invalidate:book.invalidateSheet};active.set(id,item);
  // The batch owns a single snapshot. All legacy cache invalidations stay in RAM.
  book.cache.clear=()=>{};book.invalidateSheet=()=>{};book.ramBatch=session;
  emit({event:'SHEET_BULK_READ',spreadsheetId:id,requests:1});return book;
 }
 function stage(book,request){
  const item=active.get(book.id),u=request.updateCells;
  if(!u)throw Error('BATCH_UNSUPPORTED_MUTATION');
  const sheet=book.sheets.find(s=>s.getSheetId()===u.range.sheetId);if(!sheet)throw Error('BATCH_UNKNOWN_SHEET');
  const gp=sheet.meta.properties.gridProperties;
  for(const [dimension,key,end]of [['ROWS','rowCount',u.range.endRowIndex],['COLUMNS','columnCount',u.range.endColumnIndex]])if(end>gp[key]){item.requests.push({appendDimension:{sheetId:sheet.getSheetId(),dimension,length:end-gp[key]}});gp[key]=end;}
  const master=book.cache.get(sheet.getName()+'|master'),cells=master.cells;
  for(let ri=0;ri<(u.rows||[]).length;ri++){const row=u.range.startRowIndex+ri;cells[row] ||= {values:[]};for(let ci=0;ci<(u.rows[ri].values||[]).length;ci++){const column=u.range.startColumnIndex+ci,v=u.rows[ri].values[ci],old=cells[row].values[column]||{};if(sheetTruthEnabled()&&cluster.classes.some(c=>c.spreadsheetId===book.id)&&u.fields.includes('userEnteredValue')){const key=[sheet.getSheetId(),row,column].join('|');if(!item.expected.has(key))item.expected.set(key,{key,sheetId:sheet.getSheetId(),title:sheet.getName(),row,col:column,before:clone(cellEvidence(old))});}if(u.fields.includes('userEnteredValue')){old.userEnteredValue=clone(v.userEnteredValue);old.effectiveValue=clone(v.userEnteredValue);old.formattedValue=String(v.userEnteredValue?.stringValue??v.userEnteredValue?.numberValue??v.userEnteredValue?.boolValue??'');delete old.textFormatRuns;}if(u.fields.includes('textFormatRuns'))old.textFormatRuns=clone(v.textFormatRuns||[]);if(v.userEnteredFormat)old.userEnteredFormat={...old.userEnteredFormat,...v.userEnteredFormat};cells[row].values[column]=old;}}
  book.cache.set(sheet.getName()+'|master',gridMaster(cells,gp.columnCount));item.requests.push(clone(request));writeJournal();
 }
 function flush(){
  writeJournal();for(const item of [...active.values()].sort((a,b)=>(a.book.id===cluster.controlId?1:0)-(b.book.id===cluster.controlId?1:0))){if(!item.requests.length)continue;if(sheetTruthEnabled()&&cluster.classes.some(c=>c.spreadsheetId===item.book.id)){const plan=guardClassRequests(g,item.book.id,item.requests,[...item.expected.values()]);item.requests=plan.requests;for(const e of plan.conflicts){const sheet=item.book.sheets.find(s=>s.getSheetId()===e.sheetId),master=item.book.cache.get(sheet.getName()+'|master');master.cells[e.row] ||= {values:[]};master.cells[e.row].values[e.col]=clone(e.current);item.book.cache.set(sheet.getName()+'|master',gridMaster(master.cells,sheet.meta.properties.gridProperties.columnCount));}if(plan.conflicts.length)emit({event:'SHEET_TRUTH_TEACHER_EDITS_PROTECTED',cells:plan.conflicts.length,providerCalls:0});}if(item.requests.length)g.api('https://sheets.googleapis.com/v4/spreadsheets/'+item.book.id+':batchUpdate','POST',{requests:item.requests});emit({event:'SHEET_BATCH_WRITTEN',spreadsheetId:item.book.id,mutations:item.requests.length,requests:1});item.requests=[];item.expected.clear();writeJournal();}
  if(fs.existsSync(journal))fs.unlinkSync(journal);
 }
 function close(){try{flush();}finally{g.book=originalBook;if(originalPreload)g.preloadSource=originalPreload;for(const {book,clear,invalidate}of active.values()){delete book.ramBatch;book.cache.clear=clear;book.invalidateSheet=invalidate;book.cache.clear();}}}
 function checkpointControl(id,row){
  const item=active.get(id);if(!item)return;const artifacts=item.book.getSheetByName('RunnerArtifacts')?.getSheetId(),jobs=item.book.getSheetByName('Jobs')?.getSheetId();
  const selected=item.requests.filter(r=>r.appendDimension||r.updateCells?.range.sheetId===artifacts||r.updateCells?.range.sheetId===jobs&&r.updateCells.range.startRowIndex===row-1);
  if(!selected.length)return;g.api('https://sheets.googleapis.com/v4/spreadsheets/'+id+':batchUpdate','POST',{requests:selected});item.requests=item.requests.filter(r=>!selected.includes(r));writeJournal();
 }
 const session={stage,flush,close,checkpointControl};g.book=function(id){return ids.has(id)?load(id):originalBook.call(g,id);};
 if(originalPreload)g.preloadSource=function(id,width,names){if(ids.has(id)){load(id);return;}const key=JSON.stringify([id,width,names]);if(sourceReads.has(key))return;originalPreload.call(g,id,width,names);sourceReads.add(key);};
 try{load(cluster.controlId);}catch(e){g.book=originalBook;if(originalPreload)g.preloadSource=originalPreload;throw e;}return session;
}
