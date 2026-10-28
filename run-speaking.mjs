import {SERVICE_MS} from './workload-lanes.mjs';
import {execFileSync} from 'node:child_process';
import './hosted-bootstrap.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {gunzipSync} from 'node:zlib';
const root=path.dirname(fileURLToPath(import.meta.url));
const required=name=>{const value=process.env[name]?.trim();if(!value)throw Error('MISSING_'+name);return value;};
const unpack=name=>JSON.parse(gunzipSync(Buffer.from(required(name),'base64')).toString('utf8'));
async function main(){
 process.env.IELTS_SHEETS_TRANSPORT='python';
 for(const test of ['encrypted-media-cache-tests.mjs','cooperative-upgrade-tests.mjs','worker-ownership-tests.mjs','lane-pool-tests.mjs','workload-lanes-tests.mjs','audio-completeness-tests.mjs','sheet-truth-merge-chunk-tests.mjs','speaking-target-identity-tests.mjs','speaking-queue-capacity-tests.mjs','unpaid-google-retry-tests.mjs','receipt-body-tests.mjs','submission-source-tests.mjs','native-youtube-tests.mjs','current-roster-policy-tests.mjs','core-media-resolver-tests.mjs','media-source-notice-recovery-tests.mjs'])execFileSync(process.execPath,[test],{cwd:root,stdio:'inherit',windowsHide:true,env:{...process.env,NATIVE_YOUTUBE_INPUT:'false'}});
 const mode=process.env.MODE||'audit';if(!['audit','grade'].includes(mode))throw Error('MODE_INVALID');
 const config=unpack('IELTS_RUNNER_CONFIG_GZIP_B64'),barem=unpack('IELTS_SPEAKING_BAREM_GZIP_B64'),key=required('GEMINI_KEY_IELTS_SPEAKING'),sa=JSON.parse(required('GOOGLE_SERVICE_ACCOUNT_JSON'));
 if(!config.ielts?.controlId||sa.client_email!==config.serviceAccount)throw Error('PRIVATE_CONFIGURATION_MISMATCH');
 if(process.env.GITHUB_ACTIONS==='true'){
  if(process.env.GITHUB_REF!=='refs/heads/'+required('RUNNER_DEFAULT_BRANCH'))throw Error('TRUSTED_DEFAULT_BRANCH_REQUIRED');
  if(process.env.GITHUB_REPOSITORY!==config.approvedRepository)throw Error('APPROVED_REPOSITORY_REQUIRED');
 }
 if(mode==='grade'&&process.env.SPEAKING_ENABLED!=='true')throw Error('SPEAKING_HANDOFF_NOT_ENABLED');
 if(mode==='grade'){process.env.AUTOMATIC_GRADING_AUTHORIZED='true';process.env.MASTER_CROSS_CLASS_SWEEP='true';}
 const privateDir=path.join(root,'.runtime');fs.mkdirSync(privateDir,{recursive:true,mode:0o700});const catalogFile=path.join(privateDir,'speaking-barem.json');fs.writeFileSync(catalogFile,JSON.stringify(barem),{mode:0o600});
 process.env.RUNNER_CONFIG=JSON.stringify(config);process.env.GOOGLE_CREDENTIALS=JSON.stringify(sa);process.env.GEMINI_API_KEY=key;process.env.SPEAKING_BAREM_CATALOG=catalogFile;process.env.RUNNER_HOST='github';if(config.nonStudentAudioRegistry){fs.mkdirSync(path.join(root,'private'),{recursive:true});fs.writeFileSync(path.join(root,'private/non-student-audio-registry.json'),JSON.stringify(config.nonStudentAudioRegistry));}
 const {Google,request,pause}=await import('./google-adapter.mjs'),{runIelts}=await import('./ielts-runner.mjs'),{speakingCatalog}=await import('./speaking-barem-runtime.mjs'),{localGuard}=await import('./runner-state.mjs');
 speakingCatalog(barem);const google=new Google(sa),release=localGuard(path.join(privateDir,'runner.lock'));
 let finished=0,requests=0;const deadline=Date.now()+SERVICE_MS;
 // Public logs contain only aggregate counters; names, source IDs and feedback stay in private Sheets.
 const emit=e=>{if(e.event==='IELTS_COMPLETE'||e.event==='IELTS_AUDIT')console.log(JSON.stringify({event:e.event,counts:e.counts}));else if(e.event==='SPEAKING_SOURCE_DEFERRED')console.log(JSON.stringify({event:e.event,tab:e.tab,reason:e.reason}));};
 try{
  if(mode==='audit'){
   const metadata=request({url:'https://generativelanguage.googleapis.com/v1beta/models/'+encodeURIComponent(config.ielts.model),headers:{'x-goog-api-key':key},timeoutMs:30000});if(metadata.getResponseCode()!==200)throw Error('MODEL_PREFLIGHT_FAILED');
   const result=runIelts({google,config,key,root,deadline,emit,audit:true});console.log(JSON.stringify({preflight:true,providerGenerateCalls:0,...result}));return;
  }
  const {runLanePool}=await import('./lane-pool.mjs');
  const drained=await runLanePool({lane:'ielts',root,google,config,key,deadline,plan:()=>{google.invalidate();const current=runIelts({google,config,key,root,deadline,emit,planOnly:true,resumeExisting:true,maxJobs:0,maxApiCalls:0});return current.work?.length?current:runIelts({google,config,key,root,deadline,emit,planOnly:true,maxJobs:0,maxApiCalls:0});}});finished=drained.finished;requests=drained.paidCalls;
  const result={finished,providerGenerateCalls:requests};console.log(JSON.stringify(result));
  if(process.env.GITHUB_STEP_SUMMARY)fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY,`IELTS Speaking: ${finished} results returned; ${requests} provider requests.\n`);
 }finally{release();}
}
main().catch(error=>{const code=/^[A-Z][A-Z0-9_]+$/.test(error.message)?error.message:'RUN_FAILED';console.error(JSON.stringify({failed:true,code}));process.exitCode=1;});
