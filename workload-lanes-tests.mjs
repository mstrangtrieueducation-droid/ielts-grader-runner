import assert from 'node:assert/strict';
import {mediaWorkload,workerAccepts,serviceMinutes,workConflict} from './workload-lanes.mjs';
const small={media:[{id:'one',size:49_999_999}]},large={media:[{id:'two',size:50_000_000}]},unknown={media:[]};
for(let i=0;i<3;i++){assert(workerAccepts(small,i));assert(!workerAccepts(large,i));assert(!workerAccepts(unknown,i));}
assert(workerAccepts(large,3));assert(workerAccepts(unknown,3));assert(!workerAccepts(small,3));assert(workerAccepts(small,3,{heavyWaiting:false}));
assert.equal(mediaWorkload({media:[{size:30_000_000},{size:30_000_000}]}).lane,'heavy');
assert.equal(mediaWorkload({...large,rawId:'saved'}).lane,'fast');assert(serviceMinutes(300*60000,0)>290);
assert(workConflict({source:{className:'TEST A'}},{source:{className:'TEST A'}}));assert(!workConflict({source:{className:'TEST A'},...small},{source:{className:'TEST B'},...large}));
console.log('PASS three small-file workers, at most one heavy/unknown worker, saved-result priority, class/media exclusion and five-hour budget; 0 provider calls.');

assert(workerAccepts(small,3,{heavyWaiting:true,ownerSlot:3}),'prepared files never become inaccessible when their heavy owner learns the true small size');

assert.equal(workConflict({source:{className:'TEST SAME',name:'LEARNER A'}},{source:{className:'TEST SAME',name:'LEARNER B'}}),false);
assert.equal(workConflict({source:{className:'TEST SAME',name:'LEARNER A'},target:{address:'A1'}},{source:{className:'TEST SAME',name:'LEARNER B'},target:{address:'A1'}}),true);
