import fs from 'node:fs';import path from 'node:path';import {createHash} from 'node:crypto';import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const manifest=JSON.parse(fs.readFileSync(path.join(root,'approved-code.txt'),'utf8')),runtime={...manifest,files:{}};
for(const [name,expected]of Object.entries(manifest.files)){const file=path.resolve(root,name);if(!file.startsWith(root+path.sep))throw Error('APPROVED_CODE_PATH_INVALID');const bytes=fs.readFileSync(file);const normalized=bytes.toString('utf8').replace(/\r\n/g,'\n');if(createHash('sha256').update(normalized).digest('hex')!==expected)throw Error('APPROVED_CODE_MISMATCH');runtime.files[name]=createHash('sha256').update(bytes).digest('hex');}
fs.writeFileSync(path.join(root,'CODE_FREEZE.json'),JSON.stringify(runtime));
