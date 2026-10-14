import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
export function normalizeShadowAudio(part,job){
 const mime=part.inlineData?.mimeType||part.fileData?.mimeType;
 if(mime!=='audio/mp4')return part;
 const tag=job.media[0].id+'-'+createHash('sha256').update(String(job.media[0].modified)).digest('hex').slice(0,10);
 const dir=path.join(path.dirname(fileURLToPath(import.meta.url)),'private','cache');fs.mkdirSync(dir,{recursive:true});
 const source=path.join(dir,tag+'.shadow-input.m4a'),out=path.join(dir,tag+'.shadow.mp3');
 if(!fs.existsSync(out)){
  let input=path.join(dir,tag+'.m4a');
  if(part.inlineData){fs.writeFileSync(source,Buffer.from(part.inlineData.data,'base64'));input=source;}
  if(!fs.existsSync(input))throw Error('SHADOW_CANONICAL_AUDIO_SOURCE_MISSING');
  try{
   const ffmpeg=process.env.FFMPEG_PATH||'ffmpeg';const result=spawnSync(ffmpeg,['-nostdin','-v','error','-i',input,'-map','0:a:0','-vn','-ac','1','-ar','44100','-c:a','libmp3lame','-b:a','128k','-y',out],{encoding:'utf8',timeout:120000,windowsHide:true});
   if(result.status!==0||!fs.existsSync(out)||!fs.statSync(out).size){if(fs.existsSync(out))fs.unlinkSync(out);throw Error('SHADOW_CANONICAL_AUDIO_FAILED');}
  }finally{if(fs.existsSync(source))fs.unlinkSync(source);}
 }
 const data=fs.readFileSync(out);if(data.length>8*1024*1024)throw Error('SHADOW_CANONICAL_AUDIO_TOO_LARGE');
 job.canonicalAudio={mime:'audio/mpeg',bytes:data.length,sourceMime:mime};
 return {inlineData:{mimeType:'audio/mpeg',data:data.toString('base64')}};
}
