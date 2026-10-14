import assert from 'node:assert/strict';import {noSpeech} from './zero-cost-gates.mjs';
for(const g of [{assessable:false,speechStatus:'SPEECH_DETECTED',roseSections:[]},{assessable:false,studentTranscript:'Let us make a shadow',roseSections:[]},{assessable:false,submissionCheck:{status:'wrong_assignment'},roseSections:[]},{assessable:false,roseSections:[]}])assert.equal(noSpeech(g),false);
assert.equal(noSpeech({speechStatus:'NO_SPEECH_DETECTED',assessable:false,roseSections:[]}),true);assert.equal(noSpeech({reason:'NO_SPEECH_DETECTED'}),true);
assert.equal(noSpeech({speechStatus:'SPEECH_DETECTED',reason:'NO_SPEECH_DETECTED'}),false);
console.log('PASS wrong lesson, detected speech and unavailable assessment cannot become a silence verdict; provider calls: 0.');
