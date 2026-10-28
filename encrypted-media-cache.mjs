import fs from 'node:fs';import path from 'node:path';import {spawnSync,spawn} from 'node:child_process';import {createHash,randomBytes,createCipheriv,createDecipheriv} from 'node:crypto';import {pipeline} from 'node:stream/promises';import {fileURLToPath} from 'node:url';
export const CACHE_LIMIT=4*1024**3;
const allowed=p=>/^private\/(?:campaign-workers\/[0-3]\/private\/)?(?:cache|universal-media|silence-audit|shadow-reference)\//.test(p)&&!p.includes('\\')&&path.posix.normalize(p)===p;
const mediaRoots=['cache','universal-media','silence-audit','shadow-reference'].flatMap(n=>['private/'+n,...[0,1,2,3].map(i=>'private/campaign-workers/'+i+'/private/'+n)]);
export function cacheFiles(root){const files=[];function visit(dir){if(!fs.existsSync(dir))return;for(const e of fs.readdirSync(dir,{withFileTypes:true})){const f=path.join(dir,e.name);if(e.isSymbolicLink())continue;if(e.isDirectory())visit(f);else if(e.isFile()){const relative=path.relative(root,f).split(path.sep).join('/');if(!allowed(relative)||relative.includes('\n')||relative.includes('\r'))throw Error('CACHE_PATH_INVALID');files.push({relative,bytes:fs.statSync(f).size});}}}for(const dir of mediaRoots)visit(path.join(root,dir));return files;}
export async function packCache({root,key,aad,out,limit=CACHE_LIMIT}){
 const files=cacheFiles(root),bytes=files.reduce((n,f)=>n+f.bytes,0);if(!files.length)return {saved:false,files:0,bytes:0};if(bytes>limit)return {saved:false,files:files.length,bytes,reason:'CACHE_CAPACITY_EXCEEDED'};
 fs.mkdirSync(path.dirname(out),{recursive:true});const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',key,iv);cipher.setAAD(Buffer.from(aad));const temp=out+'.partial';fs.writeFileSync(temp,Buffer.concat([Buffer.from('RMC1'),iv]));
 const tar=spawn('tar',['-czf','-','--no-recursion',...(process.platform==='win32'?[]:['--hard-dereference']),'--null','-T','-'],{cwd:root,stdio:['pipe','pipe','pipe'],windowsHide:true});let error='';tar.stderr.on('data',d=>{error+=d.toString();});const completed=new Promise((resolve,reject)=>{tar.once('error',reject);tar.once('close',code=>code===0?resolve():reject(Error('CACHE_ARCHIVE_FAILED')));});tar.stdin.end(files.map(f=>f.relative).join('\0')+'\0');
 try{await Promise.all([pipeline(tar.stdout,cipher,fs.createWriteStream(temp,{flags:'a'})),completed]);fs.appendFileSync(temp,cipher.getAuthTag());fs.renameSync(temp,out);return {saved:true,files:files.length,bytes};}finally{if(fs.existsSync(temp))fs.unlinkSync(temp);}
}
export async function restoreCache({root,key,aad,input}){
 if(!fs.existsSync(input))return {restored:false,files:0};const n=fs.statSync(input).size;if(n<33||n>CACHE_LIMIT+16*1024**2)throw Error('CACHE_ENVELOPE_INVALID');const fd=fs.openSync(input,'r'),header=Buffer.alloc(16),tag=Buffer.alloc(16);try{fs.readSync(fd,header,0,16,0);fs.readSync(fd,tag,0,16,n-16);}finally{fs.closeSync(fd);}if(header.subarray(0,4).toString()!=='RMC1')throw Error('CACHE_ENVELOPE_INVALID');
 const temp=input+'.authenticated.tar.gz',dec=createDecipheriv('aes-256-gcm',key,header.subarray(4));dec.setAAD(Buffer.from(aad));dec.setAuthTag(tag);
 try{
  // Authentication completes before tar can write anything into the workspace.
  await pipeline(fs.createReadStream(input,{start:16,end:n-17}),dec,fs.createWriteStream(temp));
  const list=spawnSync('tar',['-tzf',temp],{encoding:'utf8',windowsHide:true,maxBuffer:32*1024**2}),types=spawnSync('tar',['-tvzf',temp],{encoding:'utf8',windowsHide:true,maxBuffer:32*1024**2});
  const names=list.stdout.trim().split('\n').filter(Boolean);if(list.status!==0||types.status!==0||!names.length||names.some(p=>!allowed(p))||types.stdout.split('\n').filter(Boolean).some(l=>l[0]!=='-'))throw Error('CACHE_ARCHIVE_PATH_INVALID');
  const extract=spawnSync('tar',['-xzf',temp,'--keep-old-files'],{cwd:root,encoding:'utf8',windowsHide:true});if(extract.status!==0)throw Error('CACHE_RESTORE_FAILED');return {restored:true,files:names.length};
 }finally{if(fs.existsSync(temp))fs.unlinkSync(temp);}
}
async function main(){
 const root=process.cwd(),repo=process.env.GITHUB_REPOSITORY;if(process.env.GITHUB_ACTIONS!=='true'||!/^mstrangtrieueducation-droid\/(?:kids|shadowing|ielts)-grader-runner$/.test(repo||''))throw Error('TRUSTED_CACHE_RUNTIME_REQUIRED');
 const sa=JSON.parse(process.env.GOOGLE_SERVICE_ACCOUNT_JSON||'{}');if(!sa.private_key)throw Error('CACHE_SERVER_KEY_REQUIRED');const key=createHash('sha256').update('grading-media-cache-v1\n'+repo+'\n'+sa.private_key).digest(),file=path.join(root,'.runtime','encrypted-media-cache.bin'),aad='grading-media-cache-v1/'+repo,mode=process.argv[2];
 try{let result;if(mode==='restore'){result=await restoreCache({root,key,aad,input:file});if(result.restored&&process.env.GITHUB_ENV)fs.appendFileSync(process.env.GITHUB_ENV,'MEDIA_CACHE_RESTORED=true\n');}else if(mode==='save'){result=await packCache({root,key,aad,out:file});if(!result.saved&&fs.existsSync(file))fs.unlinkSync(file);}else throw Error('CACHE_MODE_INVALID');console.log(JSON.stringify({event:'ENCRYPTED_MEDIA_CACHE',mode,...result,providerCalls:0}));}
 catch(e){console.log(JSON.stringify({event:'ENCRYPTED_MEDIA_CACHE_UNAVAILABLE',mode,reason:/^[A-Z0-9_]+$/.test(e.message||'')?e.message:'CACHE_INTEGRITY_OR_TRANSPORT_FAILED',providerCalls:0}));}
}
if(process.argv[1]===fileURLToPath(import.meta.url))main().catch(()=>{console.log(JSON.stringify({event:'ENCRYPTED_MEDIA_CACHE_UNAVAILABLE',providerCalls:0}));});
