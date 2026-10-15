import fs from 'node:fs';import {spawnSync} from 'node:child_process';
import {SCREEN_GROUNDING_VERSION} from './screen-grounding.mjs';
export function extractPhonicsFrame({ffmpeg,input,output,durationSeconds,timeSeconds,run=spawnSync}){
 const at=Number.isFinite(timeSeconds)?timeSeconds:Number.isFinite(durationSeconds)&&durationSeconds>0?Math.min(30,durationSeconds*0.1):2;
 const args=time=>['-nostdin','-v','error','-ss',String(time),'-i',input,'-map','0:v:0','-frames:v','1','-vf','scale=min(1600\\,iw):-2','-q:v','3','-y',output];
 let time=at,result=run(ffmpeg,args(time),{encoding:'utf8',timeout:60000,windowsHide:true});
 if(result.status!==0||!fs.existsSync(output)||!fs.statSync(output).size){time=0;result=run(ffmpeg,args(time),{encoding:'utf8',timeout:60000,windowsHide:true});}
 if(result.status!==0||!fs.existsSync(output)||!fs.statSync(output).size||fs.statSync(output).size>1024*1024)throw Error('KIDS_PHONICS_FRAME_UNAVAILABLE');
 return {path:output,timeSeconds:time,bytes:fs.statSync(output).size,mime:'image/jpeg'};
}
export function extractPresentationFrames(options){
 const times=[10,40].filter(t=>!Number.isFinite(options.durationSeconds)||t<options.durationSeconds),frames=[];
 if(!times.length)times.push(Math.max(0,(options.durationSeconds||1)/2));
 for(const [i,timeSeconds] of times.entries())try{const f=extractPhonicsFrame({...options,timeSeconds,output:options.output.replace(/\.jpg$/,`-${i+1}.jpg`)});if(!frames.some(x=>x.timeSeconds===f.timeSeconds))frames.push(f);}catch{}
 return frames;
}
export function phonicsFrameParts(job,{read=fs.readFileSync,exists=fs.existsSync}={}){
 if(job.rawId||job.gradeId)return [];
 const parts=[];
 for(const [i,m] of (job.media||[]).filter(m=>!m.isReference).entries()){
  if(!m.mime.startsWith('video/'))continue;
  const frames=['phonics','science','scienceK','critical','de','project'].includes(job.route?.kind)?(m.runnerContextFrames?.length?m.runnerContextFrames:m.runnerPdfFrame?[m.runnerPdfFrame]:[]):[];
  for(const frame of frames){if(!frame.path||!exists(frame.path))continue;
   parts.push({text:`Ảnh từ FILE HỌC SINH ${i+1}, tại ${frame.timeSeconds}s. Đây là khung hình của cùng tệp âm thanh, không phải tệp/bài mới. Đối chiếu chữ/hình và cách trình bày với barem text local của đúng bài. Không suy hành vi liên tục từ một ảnh, không coi nhìn từ khóa mindmap là đọc bài viết sẵn.`},{inlineData:{mimeType:'image/jpeg',data:read(frame.path).toString('base64')}});
  }
 }
 return parts.concat(screenFrameParts(job,{read,exists}));
}

export function screenFrameTimes(duration){
 if(!Number.isFinite(duration)||duration<=0)return [0];
 return [...new Set([Math.min(1,duration*0.05),duration*0.5,Math.max(0,duration-5),Math.max(0,duration-0.5)].map(n=>Math.round(n*100)/100))].sort((a,b)=>a-b);
}
export function extractScreenFrames(options){
 const frames=[];for(const [i,timeSeconds]of screenFrameTimes(options.durationSeconds).entries())try{const f=extractPhonicsFrame({...options,timeSeconds,output:options.output.replace(/\.jpg$/,`-screen-${i+1}.jpg`)});if(!frames.some(x=>x.timeSeconds===f.timeSeconds))frames.push({...f,role:'screen_scope',version:SCREEN_GROUNDING_VERSION});}catch{}
 return frames;
}
export function screenFramesReady(m,{exists=fs.existsSync}={}){
 const capture=m.screenGroundingCapture;if(capture?.version!==SCREEN_GROUNDING_VERSION||capture.sourceId!==m.id||capture.modified!==m.modified)return false;
 return capture.status==='unavailable'||!!m.runnerScreenFrames?.length&&m.runnerScreenFrames.every(f=>f.path&&exists(f.path));
}
export function screenFrameParts(job,{read=fs.readFileSync,exists=fs.existsSync}={}){
 if(job.rawId||job.gradeId)return [];
 job.screenGroundingPolicyVersion=SCREEN_GROUNDING_VERSION;job.screenGroundingFrames=[];const parts=[];
 for(const [i,m]of (job.media||[]).filter(m=>!m.isReference).entries())for(const frame of m.runnerScreenFrames||[]){
  if(!frame.path||!exists(frame.path)||frame.version!==SCREEN_GROUNDING_VERSION)continue;
  job.screenGroundingFrames.push({fileIndex:i,timeSeconds:frame.timeSeconds,sourceId:m.id});
  parts.push({text:`Khung hình THỰC TẾ của FILE HỌC SINH ${i+1} (fileIndex ${i}), tại ${frame.timeSeconds}s. Đọc đúng câu/chỉ số tiến độ nếu nhìn thấy. Đây là cùng bài/audio; không cộng ảnh thành bài/câu mới. Phân biệt Lý thuyết/ví dụ với câu Thực hành. Nếu không đọc rõ hoặc chỉ thấy một phần, không tự suy tổng câu và không buộc học sinh làm câu chỉ có trong sách.`},{inlineData:{mimeType:frame.mime||'image/jpeg',data:read(frame.path).toString('base64')}});
 }
 return parts;
}
