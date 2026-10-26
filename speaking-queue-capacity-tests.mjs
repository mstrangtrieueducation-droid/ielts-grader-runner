import assert from 'node:assert/strict';
import {ensureSpeakingQueueCapacity} from './speaking-queue-capacity.mjs';
import {bufferSpeakingQueue} from './master-native-sweep.mjs';
function fixture(actual=1000){const calls=[],table={meta:{properties:{gridProperties:{rowCount:1000}}},getSheetId:()=>7},g={api(url,method='GET',body){calls.push({url,method,body});if(method==='GET')return {sheets:[{properties:{sheetId:7,gridProperties:{rowCount:actual}}}]};return {};}};return {g,table,calls};}
let f=fixture();ensureSpeakingQueueCapacity(f.g,'control',f.table,1000);assert.equal(f.calls.length,0);
f=fixture();ensureSpeakingQueueCapacity(f.g,'control',f.table,1003);assert.equal(f.calls.length,2);const r=f.calls[1].body.requests[0].updateSheetProperties;assert.deepEqual(r,{properties:{sheetId:7,gridProperties:{rowCount:1100}},fields:'gridProperties.rowCount'});assert.equal(f.table.meta.properties.gridProperties.rowCount,1100);
f=fixture(1300);ensureSpeakingQueueCapacity(f.g,'control',f.table,1003);assert.equal(f.calls.length,1);assert.equal(f.table.meta.properties.gridProperties.rowCount,1300);
f=fixture();f.g.api=()=>{throw Error('GOOGLE_HTTP_503');};assert.throws(()=>ensureSpeakingQueueCapacity(f.g,'control',f.table,1003),/GOOGLE_HTTP_503/);assert.equal(f.table.meta.properties.gridProperties.rowCount,1000);
f=fixture();f.table.getLastRow=()=>1000;f.g.books=new Map();const native={isgJobs_:()=>[],isgSave_:()=>{throw Error('MUST_BUFFER');}},buffer=bufferSpeakingQueue(native,f.table,f.g,'control');
for(let i=0;i<3;i++)native.isgSave_(f.table,f.table.getLastRow()+1,{id:'job-'+i,status:'QUEUED',source:{signature:'receipt-'+i}});
buffer.flush();assert.deepEqual(f.calls.map(x=>x.method),['GET','POST','POST']);assert.equal(f.calls[2].body.data.at(-1).range,"'IELTS SPEAKING AI'!A1003:F1003");assert.equal(f.calls[2].body.data.length,3);
console.log('PASS full queue grows before batch values; existing jobs untouched; fresh larger grid is never shrunk; failed growth retains pending flush; 0 AI/0 live Sheet writes.');
