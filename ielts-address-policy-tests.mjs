import assert from 'node:assert/strict';
import fs from 'node:fs';import vm from 'node:vm';
import {RichBuilder,Style} from './google-adapter.mjs';
import {isIeltsClass,ieltsAddressInstruction,ieltsAddressText,ieltsAddressSegments,installIeltsAddress,withIeltsNoticeAddress} from './ielts-address-policy.mjs';
assert.equal(ieltsAddressText('Con đọc rõ; tuy nhiên con cần giữ âm cuối trong bài của con.'),'Em đọc rõ; tuy nhiên em cần giữ âm cuối trong bài của em.');
assert.equal(ieltsAddressText('Con chú ý con số 6, con người và con đường. Confidence không đổi.'),'Em chú ý con số 6, con người và con đường. Confidence không đổi.');
const quotes='“Con nói” và "con artist", \'con\', /kɒn/; con → /kɒn/. Ở 00:18, con sửa âm /n/. Band 6.5.';
assert.equal(ieltsAddressText(quotes),'“Con nói” và "con artist", \'con\', /kɒn/; con → /kɒn/. Ở 00:18, em sửa âm /n/. Band 6.5.');
assert.equal(ieltsAddressText('Học sinh nói rõ.\n - con giữ /s/.'),'Em nói rõ.\n - em giữ /s/.');
const segments=[{text:'Con nói rõ; con giữ /s/ ở 00:18. 85%.',tone:'correction'}],before=structuredClone(segments);
for(const cls of ['IELTS 45','ielts51']){assert.equal(isIeltsClass(cls),true);assert.ok(ieltsAddressInstruction(cls).includes('em/Em'));assert.equal(ieltsAddressSegments(segments,cls)[0].text,'Em nói rõ; em giữ /s/ ở 00:18. 85%.');}
for(const cls of ['KIDS 7','FIGHTER 8']){assert.equal(ieltsAddressInstruction(cls),'');assert.equal(ieltsAddressSegments(segments,cls),segments);}
assert.deepEqual(segments,before);
const c=vm.createContext({});for(const file of ['SpeakingGemini','SpeakingCostPolicy'])vm.runInContext(fs.readFileSync(new URL('./ielts-gas/'+file+'.gs',import.meta.url),'utf8'),c);
c.ISG={neutral:'#333333',green:'#1B5E20',pink:'#C2185B',marker:'NHẬN XÉT GV',timezone:'Asia/Bangkok'};c.Utilities={formatDate:()=>''};c.SpreadsheetApp={newRichTextValue:()=>new RichBuilder(),newTextStyle:()=>new Style()};installIeltsAddress(c);
const grade={estimatedBand:6.5,limitation:'',pronunciation:{praise:['Con đọc rõ.'],errors:[{word:'rain',ipa:'/reɪn/',heard:'mail',error:'Ở 00:18, con thiếu /n/.',correction:'Con bật rõ /n/.',errorType:'Âm cuối',fileIndex:1,atSeconds:18}],endings:'Giọng con rõ.',stress:'',intonation:''},fluency:{praise:[],observation:'Tuy nhiên con còn ngập ngừng.',corrections:[]},lexical:{praise:[],observation:'',corrections:[]},grammar:{praise:[],observation:'',corrections:[]},advice:['Con luyện lại câu "Con nói".']};const original=JSON.stringify(grade),rich=c.isgRichText_(grade,{at:'2026-10-16T00:00:00Z',fileIds:['fixture-media']},true),text=rich.getText();
assert.ok(text.includes('Em đọc rõ.')&&text.includes('Giọng em rõ.')&&text.includes('Tuy nhiên em còn ngập ngừng.')&&text.includes('Em luyện lại câu "Con nói".'));
for(const unchanged of ['6.5','rain','/reɪn/','mail','[file 1, 18s]'])assert.ok(text.includes(unchanged));assert.equal(JSON.stringify(grade),original);
assert.ok(rich.getRuns().some(r=>r.getTextStyle().getForegroundColor()==='#1B5E20'));
const evidenceGrade=structuredClone(grade);Object.assign(evidenceGrade.pronunciation.errors[0],{word:'con',ipa:'/kɒn/',heard:'con'});const evidenceText=c.isgRichText_(evidenceGrade,{at:'2026-10-16T00:00:00Z',fileIds:[]},true).getText();assert.ok(evidenceText.includes('con → /kɒn/')&&evidenceText.includes('Nghe: con.'));assert.ok(evidenceText.includes('em thiếu /n/'));
const notices=[],write=withIeltsNoticeAddress((...args)=>notices.push(args),'Con kiểm tra bản thu.');write({source:{className:'IELTS 49'}},null,null,null);assert.equal(notices[0][4],'Em kiểm tra bản thu.');
console.log('PASS IELTS Em in prompt and rich feedback; quotes, words, IPA, time, bands, raw grade and non-IELTS classes preserved; zero provider calls.');
