// Read-only version check. A new revision drains owned work; it never kills a child or provider call.
let last=0,changed=false;
export async function mainRevisionChanged(env=process.env,{fetcher=fetch,now=Date.now}={}){
 if(changed)return true;
 if(env.GITHUB_ACTIONS!=='true'||!/^mstrangtrieueducation-droid\/(?:kids|shadowing|ielts)-grader-runner$/.test(env.GITHUB_REPOSITORY||'')||!env.GITHUB_SHA||!env.RUNNER_GITHUB_TOKEN)return false;
 if(now()-last<60000)return false;last=now();
 try{const r=await fetcher('https://api.github.com/repos/'+env.GITHUB_REPOSITORY+'/git/ref/heads/main',{headers:{Authorization:'Bearer '+env.RUNNER_GITHUB_TOKEN,Accept:'application/vnd.github+json'},signal:AbortSignal.timeout(10000)});if(!r.ok)return false;const value=await r.json();changed=/^[a-f0-9]{40}$/.test(value.object?.sha||'')&&value.object.sha!==env.GITHUB_SHA;return changed;}catch{return false;}
}
