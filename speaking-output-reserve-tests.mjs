import assert from 'node:assert/strict';import vm from 'node:vm';import fs from 'node:fs';import {withSpeakingOutputReserve} from './speaking-output-reserve.mjs';
const c=vm.createContext({isgSchema_:()=>({type:'object',properties:{criterionScores:{type:'object'}}})});vm.runInContext(fs.readFileSync(new URL('./ielts-gas/SpeakingCostPolicy.gs',import.meta.url),'utf8'),c);
const old=c.isgCostGenerationConfig_('gemini-3.8-flash'),next=withSpeakingOutputReserve(old,'gemini-3.8-flash');
assert.equal(old.thinkingConfig.thinkingLevel,'medium');assert.equal(next.thinkingConfig.thinkingLevel,'low');assert.equal(next.thinkingConfig.includeThoughts,false);assert.equal(next.maxOutputTokens,old.maxOutputTokens);assert.equal(next.responseFormat,old.responseFormat);assert.equal(withSpeakingOutputReserve(old,'other-model'),old);
console.log('Speaking response reserve: lower reasoning setting; same output cap, schema and frozen cost policy; zero generation calls.');
