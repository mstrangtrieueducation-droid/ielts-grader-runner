import fs from 'node:fs';
import path from 'node:path';
const sleep=ms=>Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,ms);
export function tryFileLock(file){
 fs.mkdirSync(path.dirname(file),{recursive:true});
 try{fs.writeFileSync(file,JSON.stringify({pid:process.pid,at:Date.now()}),{flag:'wx'});}
 catch(e){if(e.code!=='EEXIST')throw e;
  try{const old=JSON.parse(fs.readFileSync(file));try{process.kill(old.pid,0);}catch(p){if(p.code==='ESRCH'){fs.unlinkSync(file);return tryFileLock(file);}}}catch{try{if(Date.now()-fs.statSync(file).mtimeMs>30000){fs.unlinkSync(file);return tryFileLock(file);}}catch{}}
  return null;
 }
 return ()=>{try{const old=JSON.parse(fs.readFileSync(file));if(old.pid===process.pid)fs.unlinkSync(file);}catch{}};
}
export function reserveRateSlot(state,kind,now,interval=1100){
 const at=Math.max(now,Number(state[kind]||0));return {at,next:{...state,[kind]:at+interval}};
}
export function sheetsGate(file,kind){
 let release;while(!(release=tryFileLock(file+'.lock')))sleep(30);
 let at;try{const saved=fs.existsSync(file)?JSON.parse(fs.readFileSync(file)):{};const reserved=reserveRateSlot(saved,kind,Date.now(),Number(process.env.GOOGLE_SHEETS_INTERVAL_MS)||1100);at=reserved.at;fs.writeFileSync(file,JSON.stringify(reserved.next));}finally{release();}
 sleep(Math.max(0,at-Date.now()));
}
