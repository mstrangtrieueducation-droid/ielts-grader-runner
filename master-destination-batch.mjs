import path from 'node:path';
import {beginSheetBatch} from './kids-sheet-batch.mjs';
export function beginMasterDestinationBatch(g,classes,root,{emit=()=>{}}={}){
 if(!classes.length)return {flush(){},close(){}};
 const ids=new Set(classes.map(c=>c.spreadsheetId)),batch=beginSheetBatch(g,{controlId:classes[0].spreadsheetId,classes},path.join(root,'private/master-destination-journal'),{emit}),book=g.book,refreshes=new Map();
 g.book=function(id){const b=book.call(g,id);if(ids.has(id)&&!refreshes.has(id)){refreshes.set(id,{b,refresh:b.refresh});b.refresh=()=>{};}return b;};
 return {flush:()=>batch.flush(),close(){g.book=book;for(const {b,refresh}of refreshes.values())b.refresh=refresh;batch.close();}};
}
