import assert from 'node:assert/strict';
import {repairMediaSourceNotice,sourceNoticeBody} from './media-source-notice-recovery.mjs';
const source={className:'KIDS 90',student:'SYNTHETIC PUPIL',code:'SCIENCE-G1-01',time:'2026-10-20T10:00:00Z',links:'https://drive.google.com/open?id=synthetic_folder_123456789',row:4,sourceTab:'synthetic'};
const before='Điểm nghe: 13/30 (43%)\n✅ ĐÃ NỘP 20/10/2026 17:00:00\n— NHẬN XÉT GV —\n❌ CẦN NỘP LẠI: Link bài nộp không hợp lệ. Con kiểm tra lại nhé!';
function rig({job,formula='',validation=null,text=before,src=source}={}){
 let saves=0,writes=0;const j=job||{id:'synthetic-job',receipt:src,status:'COMPLETED_NEEDS_RESUBMISSION',autoNotice:before,resultHash:'source-notice-render',generateRequests:0};
 const cell={getDisplayValue:()=>text,getFormula:()=>formula,getDataValidation:()=>validation,getNote:()=> 'Teacher note preserved',setRichTextValue:r=>{text=r.getText();writes++;}};
 const options={source:src,existing:{job:j,row:2},cell,service:{ids:()=>['synthetic-media'],resolutionInfo:()=>({hasFolder:true})},metadata:()=>({id:'synthetic-media',mimeType:'video/mp4',size:50000}),save:()=>saves++};
 return {j,cell,options,get saves(){return saves;},get writes(){return writes;}};
}
let r=rig();assert(repairMediaSourceNotice(r.options).recovered);assert.equal(r.j.status,'READY');assert.equal(r.j.generateRequests,0);assert(!r.j.autoNotice&&!r.j.resultHash);assert.equal(r.j.mediaResolverRecovery.previousNoticeText,before);assert(r.cell.getDisplayValue().startsWith('Điểm nghe: 13/30 (43%)'));assert(!r.cell.getDisplayValue().includes('không hợp lệ'));assert(!r.cell.getDisplayValue().includes('ĐANG CHỜ'));assert.equal(r.cell.getNote(),'Teacher note preserved');assert.equal(r.saves,1);assert(!repairMediaSourceNotice(r.options).recovered);assert.equal(r.saves,1);
for(const opts of [{formula:'=1'},{validation:{}},{text:'— NHẬN XÉT GV —\nChất lượng: 85%. Con làm tốt.'},{src:{...source,time:'2026-08-01T00:00:00Z'}},{job:{id:'paid-unknown',receipt:source,status:'GENERATING',generateRequests:1}}]){r=rig(opts);assert(!repairMediaSourceNotice(r.options).recovered);assert.equal(r.writes,0);}
r=rig({job:{id:'saved',receipt:source,status:'RETURNED',rawId:'synthetic-raw',generateRequests:1,apiUsage:{tokens:100},autoNotice:before,resultHash:'saved-hash'}});assert(repairMediaSourceNotice(r.options).recovered);assert.equal(r.j.rawId,'synthetic-raw');assert.equal(r.j.generateRequests,1);assert.equal(r.j.apiUsage.tokens,100);assert.equal(r.j.resultHash,'saved-hash');assert.equal(r.j.mediaResolverRecovery.mode,'SAVED_RESULT_ONLY');
r=rig({job:{id:'archived',receipt:source,status:'COMPLETED_NEEDS_RESUBMISSION',autoNotice:before,archives:[{receipt:source,rawId:'synthetic-archive',generateRequests:1}]}});assert(repairMediaSourceNotice(r.options).recovered);assert.equal(r.j.rawId,'synthetic-archive');assert.equal(r.j.archives[0].generateRequests,1);
r=rig();r.options.service.ids=()=>{throw Error('TRANSIENT_MEDIA_FOLDER_EMPTY');};assert(repairMediaSourceNotice(r.options).deferred);assert.equal(r.writes,0);assert.equal(r.saves,0);
assert(!sourceNoticeBody('— NHẬN XÉT GV —\n❌ CẦN NỘP LẠI: Video không có tiếng đọc bài.'));
assert(!sourceNoticeBody('— NHẬN XÉT GV —\n❌ CẦN NỘP LẠI: Link bài nộp không hợp lệ. Chất lượng 80%.'));
console.log('PASS authorized source-notice recovery only, listening/notes/formulas/valid scores protected, uncertain paid requests held, cached/archive results preserved, no generation.');

r=rig({src:{...source,time:'2026-10-19T10:00:00Z'}});assert.equal(repairMediaSourceNotice(r.options).held,'NEWER_RECEIPT_ON_SHEET');assert.equal(r.writes,0);
r=rig();const newJob={id:'new-native-job',receipt:source,status:'READY'};r.options.existing=undefined;r.options.create=()=>({job:newJob,row:5});assert(repairMediaSourceNotice(r.options).recovered);assert.equal(newJob.generateRequests,undefined);assert.equal(r.writes,1);

r=rig({job:{id:'uncalled-input',receipt:source,autoNotice:before,resultHash:'notice-only',inputId:'old-prepared-input',inputHash:'old-hash',snapshotId:'old-guide',media:[{id:'synthetic_folder',mime:'application/vnd.google-apps.folder',size:0}]}});
assert(repairMediaSourceNotice(r.options).recovered);assert(!r.j.inputHash&&!r.j.snapshotId&&!r.j.media);assert.equal(r.j.mediaResolverRecovery.previousPrepared.inputId,'old-prepared-input');

// Speaking retains original native signatures (which may contain expanded child
// IDs); original Form text is a transport argument, never a source mutation.
r=rig();r.options.inputText='https://drive.google.com/drive/folders/synthetic_folder_123456789';r.options.source={...source,links:undefined,fileIds:['synthetic_single_child_123']};
r.options.service.ids=text=>{assert.equal(text,r.options.inputText);return ['synthetic_single_child_123'];};r.options.service.resolutionInfo=()=>({hasFolder:true});assert(repairMediaSourceNotice(r.options).recovered);assert.equal(r.options.source.fileIds.length,1);
