import fs from 'node:fs';import path from 'node:path';import {createHash} from 'node:crypto';import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const manifest=JSON.parse(fs.readFileSync(path.join(root,'approved-code.txt'),'utf8'));
for(const [name,expected]of Object.entries(manifest.files)){const file=path.resolve(root,name);if(!file.startsWith(root+path.sep)||createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==expected)throw Error('APPROVED_CODE_MISMATCH');}
fs.writeFileSync(path.join(root,'CODE_FREEZE.json'),JSON.stringify(manifest));
