import assert from 'node:assert/strict';import {reuseDestinationPreloads} from './destination-preload-reuse.mjs';
const staged={width:60,cells:[{values:[{formattedValue:'saved pending feedback'}]}]},books=new Map([['class',{cache:new Map([['Tracker|master',staged]])}]]),calls=[],original=function(...args){calls.push(args);};const g={book:id=>books.get(id),preloadSource:original},restore=reuseDestinationPreloads(g,[{spreadsheetId:'class',sheetName:'Tracker'}]);
for(let i=0;i<1000;i++)g.preloadSource('class',60,['Tracker']);assert.equal(calls.length,0);assert.equal(books.get('class').cache.get('Tracker|master'),staged);
g.preloadSource('source',5,['Form']);g.preloadSource('class',61,['Tracker']);g.preloadSource('class',5,['Other']);assert.equal(calls.length,3);restore();assert.equal(g.preloadSource,original);
console.log('PASS 1000 destination rechecks use the same RAM grid; pending feedback preserved; source, unknown tab and wider reads unchanged.');
