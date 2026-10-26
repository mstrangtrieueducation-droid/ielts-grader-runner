// The native queue's exact rows remain authoritative. Grow storage before
// flushing newly enqueued rows; never delete, move or rewrite existing jobs.
export function ensureSpeakingQueueCapacity(g,controlId,table,lastRow){
 if(lastRow<=table.meta.properties.gridProperties.rowCount)return;
 const url='https://sheets.googleapis.com/v4/spreadsheets/'+controlId;
 const metadata=g.api(url+'?fields=sheets(properties(sheetId,gridProperties(rowCount)))');
 const props=metadata.sheets.find(s=>s.properties.sheetId===table.getSheetId())?.properties;
 if(!props)throw Error('SPEAKING_QUEUE_TAB_MISSING');
 const rows=props.gridProperties.rowCount;
 if(lastRow>rows){const target=Math.max(lastRow,rows+100);g.api(url+':batchUpdate','POST',{requests:[{updateSheetProperties:{properties:{sheetId:table.getSheetId(),gridProperties:{rowCount:target}},fields:'gridProperties.rowCount'}}]});table.meta.properties.gridProperties.rowCount=target;}
 else table.meta.properties.gridProperties.rowCount=rows;
}
