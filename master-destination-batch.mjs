import path from 'node:path';
import {beginSheetBatch} from './kids-sheet-batch.mjs';
import {reuseDestinationPreloads} from './destination-preload-reuse.mjs';
export function scopeFirstClassSnapshot(url,firstId,classes){
 const u=new URL(url);
 if(u.origin!=='https://sheets.googleapis.com'||u.pathname!=='/v4/spreadsheets/'+firstId||u.searchParams.get('includeGridData')!=='true')return url;
 u.searchParams.delete('ranges');
 for(const name of new Set(classes.filter(c=>c.spreadsheetId===firstId).map(c=>c.sheetName).filter(Boolean)))u.searchParams.append('ranges',"'"+name.replaceAll("'","''")+"'");
 return u.toString();
}
export function beginMasterDestinationBatch(g,classes,root,{emit=()=>{}}={}){
 if(!classes.length)return {flush(){},close(){}};
 const firstId=classes[0].spreadsheetId,ids=new Set(classes.map(c=>c.spreadsheetId));
 // Preserve complete tab metadata, but load grid data only for the class tracker.
 // The shared batch adapter's control-workbook defaults must not load every tab.
 g.book(firstId);
 const originalApi=g.api;let batch,scoped=false;
 g.api=function(url,method='GET',data){const selected=!scoped&&method==='GET'?scopeFirstClassSnapshot(url,firstId,classes):url;if(selected!==url)scoped=true;return originalApi.call(g,selected,method,data);};
 try{batch=beginSheetBatch(g,{controlId:firstId,classes},path.join(root,'private/master-destination-journal'),{emit});}finally{g.api=originalApi;}
 const book=g.book,refreshes=new Map();
 g.book=function(id){const b=book.call(g,id);if(ids.has(id)&&!refreshes.has(id)){refreshes.set(id,{b,refresh:b.refresh});b.refresh=()=>{};}return b;};
 const restorePreloads=reuseDestinationPreloads(g,classes);
 return {flush:()=>batch.flush(),close(){restorePreloads();g.book=book;for(const {b,refresh}of refreshes.values())b.refresh=refresh;batch.close();}};
}
