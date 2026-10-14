import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {checkShadowCoverage} from './shadowing-coverage.mjs';
import {restoreFixedTargets} from './shadowing-fixed-ledger.mjs';
const root=path.dirname(fileURLToPath(import.meta.url));
export function postprocessShadow(raw){
 const text=(raw.candidates?.[0]?.content?.parts||[]).filter(p=>!p.thought&&typeof p.text==='string').map(p=>p.text).join('');
 const python=process.env.PYTHON_PATH||(process.platform==='win32'?path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'):'python3');
 const p=spawnSync(python,['-X','utf8',path.join(root,'shadowing-postprocess.py')],{input:JSON.stringify({text,fixedLedger:raw._shadowRequestLedger}),encoding:'utf8',timeout:15000,windowsHide:true});
 let result;try{result=JSON.parse(p.stdout);}catch{throw Error('SHADOW_POSTPROCESS_FAILED');}
 if(p.status!==0||result.error)throw Error(result.error||'SHADOW_POSTPROCESS_FAILED');
 const dir=path.join(root,'private','shadow-postprocessed');fs.mkdirSync(dir,{recursive:true});
 const digest=createHash('sha256').update(JSON.stringify(raw)).digest('hex');
 fs.writeFileSync(path.join(dir,digest+'.json'),JSON.stringify(result));
 const grade=restoreFixedTargets(result.grade,raw._shadowRequestLedger);
 return grade.scoreLedger?checkShadowCoverage(grade,raw._shadowRequestLedger):grade;
}
