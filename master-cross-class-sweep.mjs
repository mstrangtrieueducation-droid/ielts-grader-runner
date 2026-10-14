import {sourceInMasterScope,MASTER_SUBMISSIONS_SINCE} from './master-submission-scope.mjs';
import {createHash} from 'node:crypto';
import {generationSpent} from './master-policy.mjs';
import {Sheet,gridMaster} from './google-adapter.mjs';
export const SWEEP_VERSION='master-cross-class-20261014';
export const ISSUE_TAB='[CẦN_CÔ_GÁN_CỘT_HOẶC_TÊN]';
export const masterSweepEnabled=()=>process.env.MASTER_CROSS_CLASS_SWEEP==='true';
const keyOf=(lane,s)=>createHash('sha256').update(JSON.stringify([lane,s.className,s.name||s.student,s.code])).digest('hex');
const typed=v=>typeof v==='number'?{numberValue:v}:{stringValue:String(v??'')};
const cells=rows=>rows.map(row=>({values:row.map(v=>({userEnteredValue:typed(v)}))}));
const issueError=e=>/STUDENT|DESTINATION|TARGET_(?:COLUMN|TAB)|CLASS_(?:NOT_CONFIGURED|UNCONFIGURED)|SOURCE_HEADER/.test(e.message||'');
export function cachedOrUnpaid(job){return !!job.rawId||!generationSpent(job)&&!job.approvedGenerateRequests&&!job.apiUsage&&!job.usage&&!job.technicalInputFailure&&!job.presentationResubmissionRequired&&!/SYSTEM_AUDIO_ERROR|WAITING_MODEL_ACCESS/.test(job.status);}
export function createMasterSweep({google,lane,controlId,classes,entries,resolve,hasFeedback,findJob,enqueue,save,readyStatus='READY',freshStatus='READY',emit=()=>{}}){
 const issues=new Map(),states=new Map(),summary=new Map(classes.map(x=>[x.className,{className:x.className,newReturned:0,existing:0,assignment:0,pending:0}]));
 const itemState=(s,cls)=>{const key=keyOf(lane,s);if(!states.has(key))states.set(key,{key,source:s,cls});return states.get(key);};
 const countable=(j,text)=>j?.masterSweep?.version===SWEEP_VERSION&&j.masterSweep.baseline==='EMPTY'&&(['RETURNED','DONE'].includes(j.status)&&(/Chất lượng:[^\n]*\d+\s*%/.test(text)||lane==='ielts'&&/\b(?:[0-9](?:\.5|\.0)?)\s*\/\s*9|Overall|Tổng điểm|Band/i.test(text))||/^COMPLETED_.*RESUBMISSION$/.test(j.status)&&j.autoNotice===text);
 function inspect(item,mutate){
  const s=item.source,cls=item.cls,row=summary.get(s.className)||{className:s.className,newReturned:0,existing:0,assignment:0,pending:0};summary.set(s.className,row);const existing=findJob(s),j=existing?.job;item.jobId=j?.id;
  try{const dst=resolve(s,j),text=dst.cell?dst.cell.getDisplayValue():dst.text,formula=dst.cell?.getFormula?.()||dst.formula||'';if(dst.cell?.sheet?.book?.id&&dst.cell.r&&dst.cell.c)item.targetKey=[dst.cell.sheet.book.id,dst.cell.sheet.getSheetId(),dst.cell.r,dst.cell.c].join('|');
   if(hasFeedback(text,formula)||formula||dst.cell?.getDataValidation?.())return countable(j,text)?'newReturned':'existing';
   if(mutate){
    if(j){if(cachedOrUnpaid(j)){let changed=!j.masterSweep;const nextStatus=j.rawId?readyStatus:freshStatus;j.masterSweep ||= {version:SWEEP_VERSION,baseline:'EMPTY',mode:j.rawId?'CACHE':'NEW',at:new Date().toISOString()};if((j.rawId||/^(SKIPPED_|NEEDS_ASSIGNMENT|NEEDS_REVIEW|BLOCKED|STALE|RETURNED|DONE)/.test(j.status))&&(j.status!==nextStatus||j.error||j.nextAt)){j.status=nextStatus;j.error='';j.nextAt=0;changed=true;}if(changed)save(j,existing.row);}}
    else{const created=enqueue(s,cls);item.jobId=created.job.id;created.job.masterSweep={version:SWEEP_VERSION,baseline:'EMPTY',mode:'NEW',at:new Date().toISOString()};save(created.job,created.row);}
   }
   return 'pending';
  }catch(e){if(issueError(e)){if(mutate){const bucket=issues.get(cls?.spreadsheetId)||{cls,items:new Map()};bucket.items.set(item.key,{...item,reason:e.message,jobId:j?.id||''});issues.set(cls?.spreadsheetId,bucket);}return 'assignment';}item.error=e.message;return 'pending';}
 }
 function scan(){for(const entry of entries){if(!sourceInMasterScope(entry.source))continue;const item=itemState(entry.source,entry.cls);item.outcome=inspect(item,true);}emit({event:'MASTER_SWEEP_SCANNED',lane,classes:summary.size,submissions:states.size,providerCalls:0});return states.size;}
 function refresh(){for(const r of summary.values())Object.assign(r,{newReturned:0,existing:0,assignment:0,pending:0});const unique=new Map(),rank={newReturned:0,existing:1,pending:2,assignment:3};for(const item of states.values()){item.outcome=inspect(item,false);const key=item.targetKey||item.key,prior=unique.get(key);if(!prior||rank[item.outcome]<rank[prior.outcome])unique.set(key,item);}for(const item of unique.values())summary.get(item.source.className)[item.outcome]++;return [...summary.values()];}
 function publish(){const rows=refresh(),issueResult=flushClassIssues(google,issues,lane),title='MASTER SWEEP '+lane.toUpperCase(),book=google.book(controlId),tab=book.getSheetByName(title),sheetId=tab?.getSheetId()||stableSheetId(controlId,title,book),requests=[];
  if(!tab)requests.push({addSheet:{properties:{sheetId,title,gridProperties:{rowCount:Math.max(100,rows.length+5),columnCount:7,frozenRowCount:1}}}});
  const data=[['Tên lớp','Số bài vừa trả mới','Số bài đã có điểm từ trước','Số bài cần cô gán cột/tên'],...rows.map(r=>[r.className,r.newReturned,r.existing,r.assignment])];
  requests.push({updateCells:{range:{sheetId,startRowIndex:0,endRowIndex:data.length,startColumnIndex:0,endColumnIndex:4},rows:cells(data),fields:'userEnteredValue'}});
  requests.push({updateCells:{range:{sheetId,startRowIndex:0,endRowIndex:4,startColumnIndex:5,endColumnIndex:7},rows:cells([['Cập nhật',new Date().toISOString()],['Đã đối soát',states.size],['Còn chờ xử lý',rows.reduce((n,r)=>n+r.pending,0)],['Bài nộp từ',MASTER_SUBMISSIONS_SINCE]]),fields:'userEnteredValue'}});
  google.api('https://sheets.googleapis.com/v4/spreadsheets/'+controlId+':batchUpdate','POST',{requests});if(!tab)registerCreatedSheet(book,title,sheetId,Math.max(100,rows.length+5),7);
  emit({event:'MASTER_SWEEP_REPORT',lane,classes:rows.length,scanned:states.size,newReturned:rows.reduce((n,r)=>n+r.newReturned,0),existing:rows.reduce((n,r)=>n+r.existing,0),assignment:rows.reduce((n,r)=>n+r.assignment,0),pending:rows.reduce((n,r)=>n+r.pending,0),issueWriteFailures:issueResult.failed.length,providerCalls:0});return {rows,issueResult,spreadsheetId:controlId,sheetId};
 }
 const allowsJob=job=>[...states.values()].some(item=>item.jobId===job.id&&item.outcome==='pending');
 return {scan,refresh,publish,states,allowsJob};
}
function stableSheetId(id,title,book){let n=createHash('sha256').update(id+'|'+title).digest().readUInt32BE(0)&0x7fffffff;const ids=new Set(book.sheets.map(s=>s.getSheetId()));while(ids.has(n))n=(n+1)&0x7fffffff;return n;}
function registerCreatedSheet(book,title,sheetId,rowCount,columnCount){if(book.getSheetByName(title))return;const meta={properties:{sheetId,title,gridProperties:{rowCount,columnCount,frozenRowCount:1}},merges:[]};book.sheets.push(new Sheet(book,meta));if(book.meta?.sheets)book.meta.sheets.push(meta);book.cache?.set(title+'|master',gridMaster([],columnCount));}
export function flushClassIssues(g,groups,lane){const written=[],failed=[];
 for(const [id,bucket]of groups){if(!id){failed.push({className:bucket.cls?.className,error:'CLASS_FILE_NOT_CONFIGURED'});continue;}try{
  const book=g.book(id),tab=book.getSheetByName(ISSUE_TAB),sheetId=tab?.getSheetId()||stableSheetId(id,ISSUE_TAB,book),requests=[],known=new Set();
  if(tab){const rows=g.api('https://sheets.googleapis.com/v4/spreadsheets/'+id+'/values/'+encodeURIComponent("'"+ISSUE_TAB+"'!A1:I"+tab.meta.properties.gridProperties.rowCount)).values||[];for(const r of rows.slice(1))if(r[8])known.add(r[8]);}
  else{requests.push({addSheet:{properties:{sheetId,title:ISSUE_TAB,gridProperties:{rowCount:1000,columnCount:10,frozenRowCount:1}}}});requests.push({updateCells:{range:{sheetId,startRowIndex:0,endRowIndex:1,startColumnIndex:0,endColumnIndex:10},rows:cells([['Cập nhật','Lớp','Học sinh','Mã bài','Lý do','Dòng Form','Tab nguồn','Job ID','Khóa đối soát','Trạng thái']]),fields:'userEnteredValue'}});}
  const added=[...bucket.items.values()].filter(x=>!known.has(x.key));if(added.length)requests.push({appendCells:{sheetId,rows:cells(added.map(x=>[new Date().toISOString(),x.source.className,x.source.student||x.source.name,x.source.code,x.reason,x.source.row,x.source.sourceTab||x.source.sheetName,x.jobId,x.key,'CẦN GÁN CỘT/TÊN'])),fields:'userEnteredValue'}});
  if(requests.length)g.api('https://sheets.googleapis.com/v4/spreadsheets/'+id+':batchUpdate','POST',{requests});if(!tab)registerCreatedSheet(book,ISSUE_TAB,sheetId,1000,10);written.push({className:bucket.cls.className,added:added.length});
 }catch(e){failed.push({className:bucket.cls?.className,error:e.message});}}
 return {written,failed};
}
