import fs from 'node:fs';import path from 'node:path';import {createHash} from 'node:crypto';import {execFileSync} from 'node:child_process';
const hash=x=>createHash('sha256').update(x).digest('hex');
export function establishCodeFreeze(root,files){
 const manifest={version:'teacher-code-freeze-20261014',createdAt:new Date().toISOString(),files:{}};
 for(const file of files){const bytes=fs.readFileSync(path.join(root,file));manifest.files[file]=hash(bytes);const backup=path.join(root,'private','.code-freeze',file);fs.mkdirSync(path.dirname(backup),{recursive:true});fs.writeFileSync(backup,bytes);}
 fs.writeFileSync(path.join(root,'CODE_FREEZE.json'),JSON.stringify(manifest,null,2));return manifest;
}
export function verifyCodeFreeze(root){
 const file=path.join(root,'CODE_FREEZE.json');if(!fs.existsSync(file))throw Error('CODE_FREEZE_BASELINE_MISSING');const manifest=JSON.parse(fs.readFileSync(file,'utf8')),restored=[];
 for(const [name,expected]of Object.entries(manifest.files)){const target=path.resolve(root,name);if(!target.startsWith(path.resolve(root)+path.sep))throw Error('CODE_FREEZE_PATH_INVALID');if(fs.existsSync(target)&&hash(fs.readFileSync(target))===expected)continue;
  let bytes;const backup=path.join(root,'private','.code-freeze',name);if(fs.existsSync(backup))bytes=fs.readFileSync(backup);else try{bytes=execFileSync('git',['show','HEAD:'+name],{cwd:root,windowsHide:true,stdio:['ignore','pipe','ignore']});}catch{}
  if(!bytes||hash(bytes)!==expected)throw Error('CODE_FREEZE_RECOVERY_REQUIRED');fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,bytes);restored.push(name);
 }return {checked:Object.keys(manifest.files).length,restored};
}
