// Media transport only. Does not classify homework, identity or submission state.
export function submissionUrls(text){
 return (String(text||'').replace(/\\n/g,'\n').match(/https?:\/\/[^\s,<>"']+/gi)||[]).map(s=>s.replace(/[).;\]}]+$/,''));
}
export function youtubeDownloadArgs({url,node,output,client='android,web'}){
 return ['-m','yt_dlp','--js-runtimes','node:'+node,'--no-playlist','--no-progress','--no-warnings','--socket-timeout','10','--retries','0','--fragment-retries','0',...(client?['--extractor-args','youtube:player_client='+client]:[]),'-f','bestaudio/best','-x','--audio-format','mp3','--audio-quality','64K','--print','after_move:%(filepath)s','-o',output,url];
}
export function driveErrorEvidence(status,body={}){
 const e=body.error||{},reasons=[e.status,...(e.errors||[]).map(x=>x.reason)].filter(Boolean),message=String(e.message||'');
 const technical=status===401||status===429||status>=500||/rateLimit|quota|dailyLimit|accessNotConfigured|serviceDisabled|insufficientAuthenticationScopes|authError|backendError|insufficient authentication scopes|invalid credentials|invalid_grant/i.test(reasons.join('|')+' '+message);
 return {provider:'drive',http:status,reasons,technical,permissionConfirmed:!technical&&status===403&&/forbidden|insufficientFilePermissions|permission denied|does not have sufficient permissions|caller does not have permission/i.test(reasons.join('|')+' '+message),missingConfirmed:!technical&&status===404&&/notFound|not found/i.test(reasons.join('|')+' '+message)};
}
