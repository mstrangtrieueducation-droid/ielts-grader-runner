import fs from 'node:fs';
import {spawnSync} from 'node:child_process';

export function audioStreams(stderr){
 const segments=String(stderr).split(/(?=Stream #\d+:\d+)/);
 return segments.map(s=>{const m=s.match(/^Stream #0:(\d+)(?:[^\n]*): Audio:/);return m?{index:Number(m[1]),microphone:/\b(?:microphone|mic(?:rophone)? input|micro thu|microphone audio)\b/i.test(s),description:s.slice(0,500)}:null;}).filter(Boolean);
}
export function streamSelection(streams){
 if(!streams.length)throw Error('AUDIO_NO_STREAM');
 const microphones=streams.filter(s=>s.microphone),selected=microphones.length?microphones:streams;
 if(selected.length===1)return {args:['-map','0:'+selected[0].index],mode:microphones.length?'labelled_microphone':'single_audio_stream',indices:selected.map(s=>s.index)};
 // Preserve every unlabeled audio track. amix does not separate voices that were
 // recorded together; the model must assess audibility rather than guess.
 return {args:['-filter_complex',selected.map(s=>'[0:'+s.index+']').join('')+'amix=inputs='+selected.length+':duration=longest:normalize=1[student_audio]','-map','[student_audio]'],mode:'all_unlabelled_tracks',indices:selected.map(s=>s.index)};
}
export function inspectAudio(ffmpeg,input,run=spawnSync){
 const result=run(ffmpeg,['-nostdin','-hide_banner','-i',input],{encoding:'utf8',windowsHide:true,timeout:30000});
 if(result.error)throw Error('AUDIO_PROBE_FAILED');
 const streams=audioStreams(result.stderr);if(!streams.length&&!/Duration:|Stream #0:/.test(result.stderr||''))throw Error('AUDIO_PROBE_FAILED');
 return streamSelection(streams);
}
export function extractStudentAudio({ffmpeg,input,audio,flac,canonicalFormat,run=spawnSync}){
 const selection=inspectAudio(ffmpeg,input,run),working=audio+'.working.m4a',workingFlac=flac+'.working.flac';
 const execute=args=>run(ffmpeg,['-nostdin','-v','error','-i',input,...selection.args,'-vn',...args],{encoding:'utf8',windowsHide:true,timeout:240000});
 const valid=p=>fs.existsSync(p)&&fs.statSync(p).size>0;
 if(canonicalFormat==='mp3'){
  const file=audio.replace(/\.m4a$/,'.mp3'),temp=file+'.working.mp3',r=execute(['-ac','1','-ar','44100','-c:a','libmp3lame','-b:a','192k','-y',temp]);
  if(r.status!==0||!valid(temp)){if(fs.existsSync(temp))fs.unlinkSync(temp);throw Error('AUDIO_EXTRACTION_FAILED');}
  fs.renameSync(temp,file);return {file,mime:'audio/mpeg',selection};
 }
 if(selection.indices.length===1){const r=execute(['-c:a','copy','-y',working]);if(r.status===0&&valid(working)){fs.renameSync(working,audio);return {file:audio,mime:'audio/mp4',selection};}}
 if(fs.existsSync(working))fs.unlinkSync(working);
 const r=execute(['-ar','44100','-c:a','flac','-y',workingFlac]);
 if(r.status!==0||!valid(workingFlac)){if(fs.existsSync(workingFlac))fs.unlinkSync(workingFlac);throw Error('AUDIO_EXTRACTION_FAILED');}
 fs.renameSync(workingFlac,flac);return {file:flac,mime:'audio/flac',selection};
}
