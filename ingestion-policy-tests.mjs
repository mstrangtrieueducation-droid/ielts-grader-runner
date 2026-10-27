import assert from 'node:assert/strict';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
import {submissionUrls,youtubeDownloadArgs,driveErrorEvidence} from './ingestion-policy.mjs';
import {sourceIds,youtubeId,createMediaService} from './universal-media.mjs';
import {sourceInput,sourceFailure,classifyYouTubeFailure} from './submission-source-policy.mjs';
const links=['https://youtu.be/AbCdEfGhIjK?si=x','https://www.youtube.com/shorts/XyZaBcDeFgH','https://drive.google.com/open?id=12345678901234567890'];
for(const delimiter of [' ', ',', '\n','\\n']){const text=links.join(delimiter);assert.deepEqual(submissionUrls(text),links);assert.equal(sourceInput(text).urls.length,3);assert.deepEqual(sourceIds(text),['yt_AbCdEfGhIjK','yt_XyZaBcDeFgH','12345678901234567890']);}
assert.equal(youtubeId('https://www.youtube.com/watch?v=AbCdEfGhIjK&si=test'),'AbCdEfGhIjK');assert.equal(youtubeId('https://youtube.com.attacker.test/watch?v=AbCdEfGhIjK'),null);
const args=youtubeDownloadArgs({url:links[0],node:'fixture-node',output:'fixture-output'});assert(args.includes('youtube:player_client=android,web'));assert(args.includes('--no-playlist'));assert(args.includes('mp3'));
assert.equal(classifyYouTubeFailure({stderr:"Sign in to confirm you're not a bot. HTTP Error 403"}),'TRANSIENT_MEDIA_YOUTUBE_AUTH_CHALLENGE');
assert.equal(classifyYouTubeFailure({stderr:'This video is private'}),'YOUTUBE_PRIVATE');assert.notEqual(classifyYouTubeFailure({stderr:'members-only content'}),'YOUTUBE_PRIVATE');
for(const reason of ['rateLimitExceeded','dailyLimitExceeded','insufficientAuthenticationScopes','accessNotConfigured']){const evidence=driveErrorEvidence(403,{error:{errors:[{reason}]}});assert(evidence.technical);assert.equal(sourceFailure({httpCode:403,driveEvidence:evidence}).state,'pending');}
assert(driveErrorEvidence(404,{error:{errors:[{reason:'notFound'}]}}).missingConfirmed);assert(driveErrorEvidence(403,{error:{errors:[{reason:'insufficientFilePermissions'}]}}).permissionConfirmed);
const root=fs.mkdtempSync(path.join(os.tmpdir(),'ingestion-fixture-'));const service=createMediaService({g:{universalTransientInstalled:true,api:()=>({files:[{id:'child-video',mimeType:'video/mp4'}]}),fileMeta:()=>({mimeType:'application/vnd.google-apps.folder'})},root,nativeYouTube:false});assert.deepEqual(service.ids('https://drive.google.com/drive/folders/12345678901234567890'),['child-video']);
for(const file of fs.readdirSync(root))assert.equal(file,'private');
console.log('PASS multi-link delimiters, YouTube variants/clients, bot-vs-private evidence, Drive quota/auth-vs-permission and folder children; 0 AI/0 live Sheet writes.');

assert.equal(sourceFailure({httpCode:403,driveEvidence:driveErrorEvidence(403,{error:{message:'Request had insufficient authentication scopes.'}})}).state,'pending');
assert.equal(sourceFailure({httpCode:403,driveEvidence:driveErrorEvidence(403,{error:{message:'Unclassified service refusal'}})}).state,'pending');
assert.equal(sourceFailure({httpCode:403,driveEvidence:driveErrorEvidence(403,{error:{message:'The caller does not have permission'}})}).state,'access');
const quotaService=createMediaService({root,g:{universalTransientInstalled:true,token:()=> 'synthetic-token',fileMeta:()=>({})},nativeYouTube:false,download:()=>({getResponseCode:()=>403,getContentText:()=>JSON.stringify({error:{errors:[{reason:'downloadQuotaExceeded'}]}})})});
assert.throws(()=>quotaService.verifyDownload({id:'synthetic-drive-source',modified:'one',size:30000}),e=>sourceFailure(e).state==='pending');
