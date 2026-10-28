import assert from 'node:assert/strict';import fs from 'node:fs';import path from 'node:path';import os from 'node:os';import {transcodeUniversal,decodedSampleClockArgs} from './universal-media.mjs';
const root=fs.mkdtempSync(path.join(os.tmpdir(),'synthetic-audio-completeness-')),input=path.join(root,'source.mp4');fs.writeFileSync(input,Buffer.alloc(40000));
try{
 function rig(convertedSeconds,{sampleClock=20.8,sourceClock=21.64,decodeStatus=0}={}){let checks=0;return {get checks(){return checks;},run:(bin,args)=>{
  if(args.includes('-c:a')){assert(args.includes('16000')&&args.includes('64k'));assert(!args.includes('-t')&&!args.includes('-ss'),'normal conversion never trims the pupil recording');fs.writeFileSync(args.at(-1),Buffer.alloc(170000));return {status:0};}
  if(args.includes('-progress')){checks++;const normalized=args.includes('asetpts=N/SR/TB');return {status:decodeStatus,stdout:'out_time_us='+Math.round((normalized?sampleClock:sourceClock)*1e6)+'\nprogress=end\n'};}
  const seconds=args.at(-1)===input?sourceClock:convertedSeconds;return {status:1,stderr:'Duration: 00:00:'+seconds.toFixed(2)+'\nStream #0:0: Audio: aac, 48000 Hz, mono (default)'};
 }};}
 const complete=rig(20.88),result=transcodeUniversal({input,output:path.join(root,'complete.mp3'),sourceId:'synthetic',sourceSize:40000,modified:'synthetic',run:complete.run});assert.equal(result.durationSeconds,20.88);assert.equal(complete.checks,1);assert(result.segments.every(s=>s.bytes>10240&&s.bytes<5*1024*1024));
 const trimmed=rig(18);assert.throws(()=>transcodeUniversal({input,output:path.join(root,'cut.mp3'),sourceId:'synthetic',sourceSize:40000,modified:'synthetic',run:trimmed.run}),/TRANSIENT_MEDIA_INCOMPLETE_AUDIO/);assert(!fs.existsSync(path.join(root,'cut.mp3.universal.json')));
 const broken=rig(20.88,{decodeStatus:1});assert.throws(()=>transcodeUniversal({input,output:path.join(root,'bad.mp3'),sourceId:'synthetic',sourceSize:40000,modified:'synthetic',run:broken.run}),/TRANSIENT_MEDIA_INCOMPLETE_AUDIO/);
 assert.equal(fs.statSync(input).size,40000);
 const selected=['-filter_complex','[0:1][0:2]amix=inputs=2:duration=longest:normalize=1[student_audio]','-map','[student_audio]'],mixed=decodedSampleClockArgs(selected);assert(!mixed.includes('-af'));assert(mixed[1].includes(';[student_audio]asetpts=N/SR/TB[decoded_sample_clock]'));assert.equal(mixed[3],'[decoded_sample_clock]');assert.equal(selected[3],'[student_audio]','native mix selection is never mutated');
 console.log('PASS complete audio with delayed timestamps is accepted; genuine truncation and failed decoding stay blocked; normalization, all samples, byte proofs and source file preserved; 0 AI/0 live writes.');
}finally{assert.equal(path.dirname(path.resolve(root)),path.resolve(os.tmpdir()));assert(path.basename(root).startsWith('synthetic-audio-completeness-'));fs.rmSync(root,{recursive:true,force:true});}
