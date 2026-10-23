import assert from 'node:assert/strict';
import {OUTPUT_TOKENS,COMPACT_VERSION,compactGeneration,compactResponse,expandKidsCompact,expandShadowCompact} from './master-compact-output.mjs';
const response=g=>({candidates:[{finishReason:'STOP',content:{parts:[{text:JSON.stringify(g)}]}}]}),g={v:COMPACT_VERSION,ok:true,score:83,why:'',sections:[{label:'Phát âm',praise:'Con đọc rõ.',correction:'Con giữ âm cuối /s/.'}]};
assert.equal(OUTPUT_TOKENS,2048);assert.equal(compactGeneration({},'gemini-3.8-flash').thinkingConfig.thinkingLevel,'low');assert.equal(compactGeneration({},'gemini-2.5-flash').thinkingConfig.thinkingBudget,0);
assert.equal(expandKidsCompact(response(g)).band,'85%');assert.equal(expandShadowCompact(response(g)).overallPercent,85);assert.equal(expandKidsCompact(response({legacy:true})),null);assert.equal(compactResponse({candidates:[{content:{parts:[{text:'{'}]}}]}),null);assert.throws(()=>compactResponse(response({...g,score:null})),/INCOMPLETE/);
assert.equal(expandKidsCompact(response({...g,ok:false,score:null,capture:'screen_only',visualBasis:'Chỉ thấy màn hình.'})).band,'');
console.log('PASS compact future output with 2048 token cap, real score only, rounded percentages, legacy raw passthrough and incomplete JSON protection; 0 API.');

const {acceptTeacherApprovals}=await import('./teacher-approval-guards.mjs');
const paid={id:'paid',status:'DONE',rawId:'saved',gradeId:'grade',generateRequests:1,approvedGenerateRequests:1,usage:{totalTokenCount:50},generationReservation:{id:'reservation'}},old=structuredClone(paid),session={approved:new Map([['paid',{sourceLink:'https://docs.google.com/spreadsheets/d/control/edit#range=A2:F2'}]]),finish:()=>{}};
acceptTeacherApprovals([{row:2,job:paid}],session,'control','Jobs',()=>{});for(const key of ['rawId','gradeId','generateRequests','approvedGenerateRequests','usage','generationReservation'])assert.deepEqual(paid[key],old[key]);assert.equal(paid.status,'DONE');
console.log('PASS teacher checkbox preserves paid raw, usage, reservation and counters; no duplicate generation.');
