import {contrastingFeedbackBody} from './feedback-contrast.mjs';
// Alignment preserves every value and run; the separate contrast policy repairs pale ink.
export function leftAlignedFeedbackBody(body){
 if(!Array.isArray(body?.requests))return body;
 const requests=[];let added=false;
 for(const request of body.requests){requests.push(request);const u=request.updateCells;if(!u?.range)continue;
  for(const [i,row]of (u.rows||[]).entries())for(const [k,cell]of (row.values||[]).entries()){
   const text=cell.userEnteredValue?.stringValue||'';
   if(text.trim().startsWith('{')||text.trim().startsWith('['))continue;
   if(!(/NHẬN XÉT GV|Estimated Band:|Chất lượng:/i.test(text)||cell.textFormatRuns?.length)||cell.userEnteredFormat?.horizontalAlignment==='LEFT'&&cell.userEnteredFormat?.verticalAlignment==='TOP')continue;
   const r=(u.range.startRowIndex||0)+i,c=(u.range.startColumnIndex||0)+k;
   requests.push({repeatCell:{range:{sheetId:u.range.sheetId,startRowIndex:r,endRowIndex:r+1,startColumnIndex:c,endColumnIndex:c+1},cell:{userEnteredFormat:{horizontalAlignment:'LEFT',verticalAlignment:'TOP'}},fields:'userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment'}});added=true;
  }
 }
 return added?{...body,requests}:body;
}
const installed=Symbol.for('teacher.feedbackAlignment.left');
export function installFeedbackAlignment(google){
 if(google[installed])return;const api=google.api;
 google.api=function(url,method,...args){if(method==='POST'&&/sheets\.googleapis\.com\/v4\/spreadsheets\/[^/]+:batchUpdate$/.test(url))args[0]=contrastingFeedbackBody(leftAlignedFeedbackBody(args[0]));return api.call(this,url,method,...args);};google[installed]=true;
}
