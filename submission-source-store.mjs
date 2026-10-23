import {normalizeInput} from './submission-source-policy.mjs';
const START='[MTT_SOURCE_V1]',END='[/MTT_SOURCE_V1]';
export function publishSourceStatus(g,sourceId,receipt,result){
 if(!sourceId||!receipt.sourceTab||!Number.isInteger(receipt.row)||receipt.row<2)return false;
 const sheet=g.book(sourceId).getSheetByName(receipt.sourceTab);if(!sheet)return false;
 const a1="'"+receipt.sourceTab.replace(/'/g,"''")+"'!A"+receipt.row;
 const url='https://sheets.googleapis.com/v4/spreadsheets/'+sourceId;
 const response=g.api(url+'?ranges='+encodeURIComponent(a1)+'&includeGridData=true&fields=sheets(data(rowData(values(note))))');
 const prior=response.sheets?.[0]?.data?.[0]?.rowData?.[0]?.values?.[0]?.note||'';
 const payload={schema:1,input:normalizeInput(receipt.links),code:receipt.code,student:receipt.student,className:receipt.className,submittedAt:receipt.time,state:result.state,label:result.label,reason:result.reason,aiEligible:result.aiEligible,checkedAt:new Date().toISOString()};
 const block=START+JSON.stringify(payload,null,2)+END;
 const old=prior.match(/\[MTT_SOURCE_V1\]([\s\S]*?)\[\/MTT_SOURCE_V1\]/);
 if(old)try{const p=JSON.parse(old[1]);if(p.input===payload.input&&p.code===payload.code&&p.student===payload.student&&p.className===payload.className&&p.state===payload.state&&p.reason===payload.reason)return false;}catch{}
 const note=(prior.replace(/\s*\[MTT_SOURCE_V1\][\s\S]*?\[\/MTT_SOURCE_V1\]/g,'').trim()+'\n'+block).trim();
 g.api(url+':batchUpdate','POST',{requests:[{updateCells:{range:{sheetId:sheet.getSheetId(),startRowIndex:receipt.row-1,endRowIndex:receipt.row,startColumnIndex:0,endColumnIndex:1},rows:[{values:[{note}]}],fields:'note'}}]});return true;
}
