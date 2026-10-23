import {request} from './google-adapter.mjs';
const repos=new Set(['mstrangtrieueducation-droid/kids-grader-runner','mstrangtrieueducation-droid/shadowing-grader-runner','mstrangtrieueducation-droid/ielts-grader-runner']);
// Never delete/replace a live writer's lease. A replacement is permitted only
// after GitHub confirms the exact old run has fully completed in this repo.
export function completedLeaseOwner(lease,{env=process.env,fetcher=request}={}){
 if(env.GITHUB_ACTIONS!=='true'||!repos.has(env.GITHUB_REPOSITORY)||!env.RUNNER_GITHUB_TOKEN||!/^\d+$/.test(String(lease.runId||''))||String(lease.runId)===env.GITHUB_RUN_ID)return false;
 try{const r=fetcher({url:'https://api.github.com/repos/'+env.GITHUB_REPOSITORY+'/actions/runs/'+lease.runId,headers:{Authorization:'Bearer '+env.RUNNER_GITHUB_TOKEN,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'},timeoutMs:30000});if(r.getResponseCode()!==200)return false;const run=JSON.parse(r.getContentText());return String(run.id)===String(lease.runId)&&run.status==='completed'&&run.repository?.full_name===env.GITHUB_REPOSITORY;}catch{return false;}
}
