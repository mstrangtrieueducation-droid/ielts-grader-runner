// Private request/response transport for synchronous legacy Apps Script adapters.
// Credentials arrive on stdin, never command-line arguments or logs.
import fs from 'node:fs';
import {Readable} from 'node:stream';
import {pipeline} from 'node:stream/promises';
const q=JSON.parse(fs.readFileSync(0,'utf8'));
try {
 const body=q.bodyFile?fs.readFileSync(q.bodyFile):q.bodyBase64?Buffer.from(q.bodyBase64,'base64'):q.body;
 const r=await fetch(q.url,{method:q.method||'GET',headers:q.headers,body,signal:AbortSignal.timeout(q.timeoutMs||240000)});
 if(q.outputFile&&r.ok){
  if(q.expectedContentRange&&r.headers.get('content-range')!==q.expectedContentRange){await r.body.cancel();process.stdout.write(JSON.stringify({status:r.status,headers:Object.fromEntries(r.headers),bodyBase64:''}));}
  else {await pipeline(Readable.fromWeb(r.body),fs.createWriteStream(q.outputFile,{flags:q.append?'a':'w'}));process.stdout.write(JSON.stringify({status:r.status,headers:Object.fromEntries(r.headers),file:q.outputFile}));}
 }
 else process.stdout.write(JSON.stringify({status:r.status,headers:Object.fromEntries(r.headers),bodyBase64:Buffer.from(await r.arrayBuffer()).toString('base64')}));
}catch(e){process.stdout.write(JSON.stringify({transportError:'NETWORK_OUTCOME_UNKNOWN'}));process.exitCode=1;}
