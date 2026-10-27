import assert from 'node:assert/strict';
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
import {createMediaService,MAX_PART_BYTES,driveConfirmation} from './universal-media.mjs';
import {submissionUrls} from './ingestion-policy.mjs';
import {sourceInput} from './submission-source-policy.mjs';
const root=fs.mkdtempSync(path.join(os.tmpdir(),'shared-core-media-'));
const folder='synthetic_folder_123456789',ids=['synthetic_video_one_12345','synthetic_video_two_12345','synthetic_video_ten_12345'];
const files=ids.map((id,i)=>({id,name:['Video 1.mp4','Video 2.mov','Video 10.mp4'][i],mimeType:'video/mp4',size:String((120+i*110)*1024*1024),modifiedTime:'2026-10-01T00:00:00Z'}));
const meta=new Map([[folder,{mimeType:'application/vnd.google-apps.folder'}],...files.map(f=>[f.id,f])]);
let lists=0,ranges=0,largest=0,transcodes=0;
const g={universalTransientInstalled:true,token:()=> 'synthetic-token',fileMeta:id=>meta.get(id)||{},api:url=>{lists++;const u=new URL(url);assert.equal(u.searchParams.get('q'),"'"+folder+"' in parents and trashed = false");return u.searchParams.has('pageToken')?{files:files.slice(0,2)}:{files:[files[2]],nextPageToken:'second'};}};
const download=q=>{assert(q.url.includes('alt=media')&&q.outputFile&&!q.body);const id=q.url.match(/files\/([^?]+)/)[1],size=+meta.get(id).size,m=/bytes=(\d+)-(\d+)/.exec(q.headers.Range),start=+m[1],end=+m[2];assert.equal(start,fs.existsSync(q.outputFile)?fs.statSync(q.outputFile).size:0);assert.equal(q.expectedContentRange,'bytes '+start+'-'+end+'/'+size);largest=Math.max(largest,end-start+1);ranges++;const fd=fs.openSync(q.outputFile,fs.existsSync(q.outputFile)?'r+':'w+');try{fs.ftruncateSync(fd,end+1);}finally{fs.closeSync(fd);}return {getResponseCode:()=>206,getAllHeaders:()=>({'content-range':q.expectedContentRange})};};
const run=(bin,args)=>{if(args.includes('-c:a')){transcodes++;assert(args.includes('16000')&&args.includes('64k')&&args.includes('-vn'));assert.equal(args[args.indexOf('-ac')+1],'1');fs.writeFileSync(args.at(-1),Buffer.alloc(16000));return {status:0};}return {status:1,stderr:'Duration: 00:00:10.00\nStream #0:0: Audio: aac, 16000 Hz, mono (default)'};};
try{
 const service=createMediaService({g,root,download,run,nativeYouTube:false});
 // Required case 1: MIME-detected folder, paginated children >100MiB, numeric order.
 const link='https://drive.google.com/open?id='+folder;
 assert.deepEqual(service.ids(link),ids);assert.equal(lists,2);assert(service.resolutionInfo(link).hasFolder);
 for(const f of files)assert(service.verifyDownload({id:f.id,mime:f.mimeType,size:+f.size,modified:f.modifiedTime}).complete);
 assert(ranges>80);assert(largest<=8*1024*1024);
 // Required case 2: >300MiB individual source, bounded disk transport and normalized audio.
 const f=files[2];assert(+f.size>300*1024*1024);
 const audio=service.prepare({id:f.id,mime:f.mimeType,size:+f.size,modified:f.modifiedTime});
 assert.equal(audio.channels,1);assert.equal(audio.sampleRate,16000);assert.equal(audio.bitrate,64000);assert(transcodes>0);
 assert(audio.segments.every(x=>x.bytes>10240&&x.bytes<MAX_PART_BYTES));
 // Required case 3: two URLs separated by spaces, commas, semicolons or line breaks.
 const links=ids.slice(0,2).map(id=>'https://drive.google.com/file/d/'+id+'/view');
 for(const sep of [' ', ';', ',', '\n','\r\n','\t']){assert.deepEqual(submissionUrls(links.join(sep)),links);assert.deepEqual(service.ids(links.join(sep)),ids.slice(0,2));}
 assert.deepEqual(service.legacySourceIds(links.join(';')),ids.slice(0,1),'old source signature projection stays unchanged despite corrected media expansion');
 assert.deepEqual(service.legacySourceIds(folder),[],'new bare-ID transport must not change old signatures');
 assert.deepEqual(sourceInput(folder).driveIds,[folder]);assert.deepEqual(service.ids(folder),ids);
 // Required case 4: YouTube sharing suffix, downloader-first android,web.
 const yr=path.join(root,'youtube'),video='AbCdEfGhIjK';let attempts=0;
 const yt=createMediaService({g:{universalTransientInstalled:true,api:()=>({}),fileMeta:()=>({})},root:yr,nativeYouTube:false,download:()=>{throw Error('LIVE_NETWORK_FORBIDDEN');},run:(bin,args)=>{attempts++;assert(args.includes('youtube:player_client=android,web')&&args.includes('-x')&&args.includes('mp3'));assert.equal(args.at(-1),'https://www.youtube.com/watch?v='+video);fs.writeFileSync(path.join(yr,'private','universal-media',video+'.mp3'),Buffer.alloc(18000));return {status:0};}});
 const yid=yt.ids('https://youtu.be/'+video+'?si=synthetic-share');assert.deepEqual(yid,['yt_'+video]);assert.equal(yt.youtube(yid[0]).size,'18000');assert.equal(attempts,1);
 const confirm=driveConfirmation('<form action="https://drive.usercontent.google.com/download"><input name="id" value="'+folder+'"><input name="confirm" value="synthetic"></form>',{'set-cookie':'download_warning_test=cookie; Path=/'},folder);
 assert.equal(new URL(confirm.url).searchParams.get('confirm'),'synthetic');assert.equal(confirm.headers.Cookie,'download_warning_test=cookie');
 assert.equal(driveConfirmation('<form action="https://example.test/download"></form>',{},folder),null);
 console.log('PASS four generic media cases, folder pagination/order, >300MiB streaming, normalized audio, multi-link splitting, YouTube suffix/clients and confirmation host guard; 0 AI/0 live writes.');
}finally{assert.equal(path.dirname(path.resolve(root)),path.resolve(os.tmpdir()));assert(path.basename(root).startsWith('shared-core-media-'));fs.rmSync(root,{recursive:true,force:true});}
