// Foreground-only palette repair. Preserve semantic tones and exact text.
const rgb=hex=>({red:parseInt(hex.slice(1,3),16)/255,green:parseInt(hex.slice(3,5),16)/255,blue:parseInt(hex.slice(5,7),16)/255});
export const FEEDBACK_BASE='#0D47A1';
export function readableForeground(format={}){
 const color=format.foregroundColorStyle?.rgbColor||format.foregroundColor;
 if(!color)return format.foregroundColorStyle?.themeColor?rgb(FEEDBACK_BASE):null;
 // Normalize even readable legacy shades to the teacher's three exact colors.
 const r=color.red||0,g=color.green||0,b=color.blue||0;
 return rgb(g>r*1.12&&g>b*1.08?'#1B5E20':r>b*1.12&&r>g*1.25?'#C2185B':b>g*1.15&&r>g*1.15?'#C2185B':FEEDBACK_BASE);
}
export function contrastCell(cell,{base=true}={}){
 const out=structuredClone(cell);
 for(const run of out.textFormatRuns||[]){const color=readableForeground(run.format);if(!color)continue;run.format={...run.format,foregroundColorStyle:{rgbColor:color}};delete run.format.foregroundColor;}
 if(base){out.userEnteredFormat={...out.userEnteredFormat,textFormat:{...out.userEnteredFormat?.textFormat,foregroundColorStyle:{rgbColor:rgb(FEEDBACK_BASE)}}};delete out.userEnteredFormat.textFormat.foregroundColor;}
 return out;
}
export function contrastingFeedbackBody(body){
 if(!Array.isArray(body?.requests))return body;let changed=false;
 const requests=[];for(const request of body.requests){const u=request.updateCells;if(!u?.range){requests.push(request);continue;}let eligible=false;const baseRequests=[];
  const rows=(u.rows||[]).map((row,i)=>({...row,values:(row.values||[]).map((cell,k)=>{const text=cell.userEnteredValue?.stringValue||'';
   if(text.trim().startsWith('{')||text.trim().startsWith('[')||cell.dataValidation||cell.userEnteredValue?.formulaValue)return cell;
   const full=/NHẬN XÉT GV|Estimated Band:|Chất lượng:/i.test(text),repair=!cell.userEnteredValue&&cell.textFormatRuns?.length;
   if(!full&&!repair)return cell;eligible=true;
   if(full){const r=(u.range.startRowIndex||0)+i,c=(u.range.startColumnIndex||0)+k;baseRequests.push({repeatCell:{range:{sheetId:u.range.sheetId,startRowIndex:r,endRowIndex:r+1,startColumnIndex:c,endColumnIndex:c+1},cell:{userEnteredFormat:{textFormat:{foregroundColorStyle:{rgbColor:rgb(FEEDBACK_BASE)}}}},fields:'userEnteredFormat.textFormat.foregroundColorStyle'}});}
   return contrastCell(cell,{base:false});
  })}));
  if(!eligible){requests.push(request);continue;}changed=true;
  requests.push({updateCells:{...u,rows}},...baseRequests.filter(x=>!body.requests.some(y=>JSON.stringify(x)===JSON.stringify(y))));
 }return changed?{...body,requests}:body;
}
