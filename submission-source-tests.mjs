import assert from 'node:assert/strict';
import {sourceInput,sourceFailure,inspectSubmissionSource,assertSourceReady,sourceNotice} from './submission-source-policy.mjs';
import {installSubmissionSourceGate} from './submission-source-kids.mjs';
import {publishSourceStatus} from './submission-source-store.mjs';
import {installSpeakingSourceGate} from './submission-source-speaking.mjs';
const ok={id:'file',size:'3',mimeType:'video/mp4',modifiedTime:'2026-10-22'};
let paid=0,uploaded=0,passed=0;
const service={ids:()=>['file'],verifyDownload:()=>({complete:true,bytes:3})};
function rig(input,metadata=()=>ok,transport=service){let writes=0,published=[],saved=[];const c={step_:()=>{uploaded++;return c.generate_(job);},generate_:()=>{paid++;},persist_:j=>saved.push(structuredClone(j))};let job={id:'job',receipt:{links:input,time:'2026-10-22T14:57:42Z',sourceTab:'PEPPA PIG',row:813},status:'WAITING_INPUT'};installSubmissionSourceGate(c,{g:{fileMeta:metadata},service:transport,sourceId:'test',isLatest:()=>true,publish:(_g,_s,r,result)=>{writes++;published.push(result);}});return {c,job,published,saved,run:()=>c.step_(job,2)};}
for(const [input,state,metadata]of [['','missing',()=>ok],['Snow.mov','invalid',()=>ok],['https://drive.google.com/file/d/file/view','access',()=>{const e=Error('GOOGLE_HTTP_403');e.httpCode=403;throw e;}],['https://drive.google.com/file/d/file/view','invalid',()=>{throw Error('GOOGLE_HTTP_404');}],['https://drive.google.com/file/d/file/view','pending',()=>{throw Error('GOOGLE_HTTP_503');}]]){const r=rig(input,metadata);r.run();assert.equal(r.job.sourceIntake.state,state);assert.equal(r.job.status,'WAITING_INPUT');assert.equal(r.job.receipt.time,'2026-10-22T14:57:42Z');assert(r.published[0].label.startsWith('ĐÃ NỘP'));assert.equal(paid,0);assert.equal(uploaded,0);passed++;}
const valid=rig('https://drive.google.com/file/d/file/view');valid.run();assert.equal(valid.job.sourceIntake.state,'valid');assert.equal(paid,1);assert.equal(uploaded,1);passed++;
// A corrected URL is checked afresh, not held behind the previous input failure.
const corrected=rig('');corrected.run();corrected.job.receipt.links='https://drive.google.com/file/d/file/view';corrected.run();assert.equal(corrected.job.sourceIntake.state,'valid');assert.equal(paid,2);passed++;
// Same URL, repaired permission, also resumes on the next scan.
let locked=true;const permission=rig('https://drive.google.com/file/d/file/view',()=>{if(locked)throw Error('GOOGLE_HTTP_403');return ok;});permission.run();locked=false;permission.run();assert.equal(permission.job.sourceIntake.state,'valid');assert.equal(paid,3);passed++;
let meta=0;const mixed=rig('https://drive.google.com/file/d/file/view',()=>{if(++meta===2)throw Error('GOOGLE_HTTP_403');return ok;},{...service,ids:()=>['first','second']});mixed.run();assert.equal(mixed.job.sourceIntake.state,'access');assert.equal(paid,3);assert.equal(uploaded,3);passed++;
const partial=inspectSubmissionSource({text:'https://example.test/x',service:{...service,verifyDownload:()=>({complete:false,bytes:2})},metadata:()=>ok});assert.equal(partial.state,'pending');assert.throws(()=>assertSourceReady(partial));passed++;
for(const [input,state]of [['javascript:alert(1)','invalid'],['http://example.test/x','invalid'],['https://user:pass@example.test/x','invalid'],['   ','missing']])assert.equal(sourceInput(input).state,state);passed+=4;
assert.equal(sourceFailure(Error('SOURCE_ACCESS_REQUIRED')).state,'access');assert.equal(sourceFailure(Error('SOURCE_NOT_FOUND')).state,'invalid');assert.equal(sourceFailure(Error('UNSUPPORTED_LINK')).state,'pending');passed+=3;
assert(sourceNotice(valid.job.sourceIntake,'22/10/2026 21:57:42').includes('21:57:42'));passed++;
// Source Sheet writer changes only its own note block, never Form values/grades.
let request;const g={book:()=>({getSheetByName:()=>({getSheetId:()=>1853171536})}),api:(url,method,data)=>{if(method==='POST'){request=data;return {};}return {sheets:[{data:[{rowData:[{values:[{note:'Ghi chú của cô'}]}]}]}]};}};
publishSourceStatus(g,'source',{links:'',sourceTab:'PEPPA PIG',row:813,code:'Peppa-22',student:'ELSA',className:'KIDS 28',time:'2026-10-22T14:57:42Z'},sourceInput(''));
assert.equal(request.requests[0].updateCells.fields,'note');assert(request.requests[0].updateCells.rows[0].values[0].note.startsWith('Ghi chú của cô'));passed++;
let speakingCalls=0,access=true;
const speaking={isgProcess_:(table,item)=>speaking.isgCallGemini_(item.job),isgCallGemini_:()=>speakingCalls++,isgFresh_:()=>{},isgSave_:()=>{}};
installSpeakingSourceGate(speaking,{g:{fileMeta:()=>{if(!access)throw Error('GOOGLE_HTTP_403');return ok;}},service,sourceId:'fixture',publish:()=>{}});
const sj={source:{fileIds:[],at:'2026-10-22T14:57:42Z',sheetName:'A',row:2},status:'QUEUED'};
speaking.isgProcess_({}, {job:sj,row:2});assert.equal(sj.sourceIntake.state,'missing');assert.equal(speakingCalls,0);passed++;
sj.source.fileIds=['file'];access=false;speaking.isgProcess_({}, {job:sj,row:2});assert.equal(sj.sourceIntake.state,'access');assert.equal(speakingCalls,0);passed++;
access=true;speaking.isgProcess_({}, {job:sj,row:2});assert.equal(sj.sourceIntake.state,'valid');assert.equal(speakingCalls,1);passed++;
assert.throws(()=>speaking.isgCallGemini_({sourceIntake:{schema:1,state:'access',aiEligible:false}}),/SOURCE_NOT_READY/);assert.equal(speakingCalls,1);passed++;
let inspected='';const mixedSpeaking={isgProcess_:()=>{throw Error('MUST_NOT_GENERATE');},isgCallGemini_:()=>{throw Error('MUST_NOT_GENERATE');},isgFresh_:()=>{},isgSave_:()=>{},isgSourceInput_:()=>'https://drive.google.com/file/d/file/view https://unsupported.test/video'};
installSpeakingSourceGate(mixedSpeaking,{g:{fileMeta:()=>ok},service:{...service,ids:text=>{inspected=text;throw Error('UNSUPPORTED_LINK');}},sourceId:'fixture',publish:()=>{}});
const mixedJob={source:{fileIds:['file'],at:'2026-10-22T14:57:42Z'},status:'QUEUED'};mixedSpeaking.isgProcess_({}, {job:mixedJob,row:2});assert(inspected.includes('unsupported.test'));assert.equal(mixedJob.sourceIntake.state,'pending');passed++;
console.log(JSON.stringify({passed,cases:'four states, all attachments, corrected link, repaired permissions, partial download, timeout, note isolation',realProviderCalls:0,fixturePaidCalls:paid,invalidSourceFixtureCalls:0}));
