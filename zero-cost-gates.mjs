import {studentSpeechDetected} from './student-speech-evidence.mjs';
import {spawnSync} from 'node:child_process';
import {normalizeName} from './master-policy.mjs';
export const SILENT_NOTICE='❌ CẦN NỘP LẠI — Video/Audio của con không có tiếng đọc bài. Con kiểm tra lại micro và nộp lại để cô nhận xét nhé!';
export const OLD_FILE_NOTICE='❌ CẦN NỘP LẠI — Con nộp nhầm file của bài cũ đã có điểm rồi. Con kiểm tra và nộp lại đúng bài này nhé!';
export const SILENCE_POLICY=Object.freeze({noiseDb:-55,minSilenceSeconds:0.1,rmsDb:-65,minAudibleSeconds:0.35});
export function parseSilence(stderr){
 const s=String(stderr),duration=s.match(/Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)/),number=key=>{const m=s.match(new RegExp(key+':\\s*(-?inf|-?[\\d.]+)'));return m?Number(m[1].replace('-inf','-Infinity')):NaN;};
 const durationSeconds=duration?Number(duration[1])*3600+Number(duration[2])*60+Number(duration[3]):NaN,meanDb=number('mean_volume'),maxDb=number('max_volume');
 if(!Number.isFinite(durationSeconds)||Number.isNaN(meanDb)||Number.isNaN(maxDb))throw Error('AUDIO_SILENCE_PROBE_FAILED');
 const silentSeconds=[...s.matchAll(/silence_duration:\s*([\d.]+)/g)].reduce((n,m)=>n+Number(m[1]),0),audibleSeconds=Math.max(0,durationSeconds-silentSeconds);
 // Full-file measurement only. Brief greetings/initial silence never reject a file.
 const silent=maxDb<=SILENCE_POLICY.noiseDb||meanDb<SILENCE_POLICY.rmsDb&&audibleSeconds<SILENCE_POLICY.minAudibleSeconds;
 return {durationSeconds,meanDb:Number.isFinite(meanDb)?meanDb:null,maxDb:Number.isFinite(maxDb)?maxDb:null,silentSeconds,audibleSeconds,silent,policy:SILENCE_POLICY};
}
export function inspectSilence(ffmpeg,file,run=spawnSync){
 const r=run(ffmpeg,['-nostdin','-hide_banner','-i',file,'-vn','-af',`silencedetect=noise=${SILENCE_POLICY.noiseDb}dB:d=${SILENCE_POLICY.minSilenceSeconds},volumedetect`,'-f','null','-'],{encoding:'utf8',windowsHide:true,timeout:240000});
 if(r.error||r.status!==0)throw Error('AUDIO_SILENCE_PROBE_FAILED');return parseSilence(r.stderr);
}
const source=j=>j.receipt||j.source||{};
const ids=j=>new Set((j.media||[]).filter(m=>!m.isReference).flatMap(m=>[m.id,m.md5Checksum,m.runnerAudio?.sha256].filter(Boolean)).concat(source(j).fileIds||[],[...String(source(j).links||source(j).link||'').matchAll(/(?:[?&]id=|\/d\/)([-\w]{20,})/g)].map(m=>m[1])));
export function oldGradedSubmission(job,jobs,isGraded){
 const s=source(job),name=normalizeName(s.student||s.name),cls=job.cls?.className||s.className,code=job.route?.code||s.code,current=ids(job);
 if(!current.size)return null;
 for(const item of jobs){const prior=item.job||item,p=source(prior);if(prior.id===job.id||(prior.cls?.className||p.className)!==cls||normalizeName(p.student||p.name)!==name||(prior.route?.code||p.code)===code)continue;
  if(!['RETURNED','DONE','SKIPPED_ALREADY_GRADED','SKIPPED_EXISTING_FEEDBACK'].includes(prior.status))continue;
  if([...ids(prior)].some(id=>current.has(id))&&isGraded(prior))return prior;
 }return null;
}
export const noSpeech=g=>!studentSpeechDetected(g)&&(g.speechStatus==='NO_SPEECH_DETECTED'||g.reason==='NO_SPEECH_DETECTED');
export function hasExistingFeedback(value){const text=String(value||'').trim(),marker='— NHẬN XÉT GV —';if(!text)return false;if(text.includes(marker))return !!text.slice(text.indexOf(marker)+marker.length).trim();return text.split('\n').some(line=>{const s=line.trim();return s&&!/^(?:✅\s*(?:ĐÃ NỘP|ĐÃ GHI NHẬN)(?:\s*·.*)?|⚠️?\s*(?:ĐÃ NỘP MUỘN|NỘP MUỘN)(?:\s*·.*)?|❌\s*CHƯA NỘP|\[?\d{1,2}\/\d{1,2}\/\d{4}[^\n]*\]?|Lượt \d+:.*|— CHƯA GHI NHẬN.*)$/i.test(s);});}
