import {sheetTruthEnabled} from './sheet-truth-state.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {createSign,createHash,randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {sheetsGate} from './shared-gate.mjs';
const root=path.dirname(fileURLToPath(import.meta.url));
export const pause=ms=>Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,ms);
export class Blob {
 constructor(bytes,mime='application/octet-stream'){this.bytes=Buffer.from(bytes);this.mime=mime;}
 getBytes(){return [...this.bytes];} getDataAsString(){return this.bytes.toString('utf8');} getContentType(){return this.mime;}
}
export class Response {
 constructor(r){this.r=r;this.bytes=Buffer.from(r.bodyBase64||'','base64');}
 getResponseCode(){return this.r.status;} getContentText(){return this.bytes.toString('utf8');}
 getContent(){return [...this.bytes];}
 getAllHeaders(){return this.r.headers;}getBlob(){return new Blob(this.bytes,this.r.headers?.['content-type']);}
}
export function request(q){
 if(sheetTruthEnabled()&&/^https:\/\/(?:www\.)?googleapis\.com\/drive\//.test(q.url))q={...q,timeoutMs:Math.min(Number(q.timeoutMs)||30000,30000)};
 if(process.env.SHADOW_DOWNLOAD_TIMEOUT_MS&&(!q.method||q.method==='GET'))q={...q,timeoutMs:Math.min(Number(process.env.SHADOW_DOWNLOAD_TIMEOUT_MS),q.timeoutMs||240000)};
 const p=spawnSync(process.execPath,[path.join(root,'http-bridge.mjs')],{input:JSON.stringify(q),encoding:'utf8',maxBuffer:350*1024*1024,timeout:(q.timeoutMs||240000)+15000,windowsHide:true});
 let r;try{r=JSON.parse(p.stdout||'{}');}catch{throw Error('NETWORK_OUTCOME_UNKNOWN');}
 if(r.transportError||p.error||!r.status)throw Error('NETWORK_OUTCOME_UNKNOWN');return new Response(r);
}
export class Google {
 constructor(sa){this.sa=sa;this.until=0;this.books=new Map();this.fileMetadata=new Map();this.metrics={sheetCalls:0,sheetMs:0};}
 token(){
  if(this.until>Date.now())return this.access;
  const b=x=>Buffer.from(JSON.stringify(x)).toString('base64url'),now=Math.floor(Date.now()/1000);
  const body=b({alg:'RS256',typ:'JWT'})+'.'+b({iss:this.sa.client_email,scope:'https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/drive.readonly',aud:'https://oauth2.googleapis.com/token',iat:now,exp:now+3600});
  const assertion=body+'.'+createSign('RSA-SHA256').update(body).sign(this.sa.private_key,'base64url');
  const r=request({url:'https://oauth2.googleapis.com/token',method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',assertion}).toString()});
  const j=JSON.parse(r.getContentText());if(!j.access_token)throw Error('SERVICE_ACCOUNT_AUTH_FAILED');this.access=j.access_token;this.until=Date.now()+3300000;return this.access;
 }
 api(url,method='GET',data){
  if(process.env.IELTS_SHEETS_TRANSPORT&&process.env.IELTS_SHEETS_TRANSPORT!=='python')throw Error('IELTS_PYTHON_TRANSPORT_REQUIRED');
  const measuredAt=Date.now(),isSheet=url.startsWith('https://sheets.googleapis.com/');if(isSheet)this.metrics.sheetCalls++;
  let r;for(let attempt=0;attempt<6;attempt++){
   if(url.startsWith('https://sheets.googleapis.com/')){if(process.env.GOOGLE_RATE_GATE_FILE)sheetsGate(process.env.GOOGLE_RATE_GATE_FILE,method==='GET'?'read':'write');else{pause(Math.max(0,(this.nextSheetAt||0)-Date.now()));this.nextSheetAt=Date.now()+1800;}}
   try{const p=spawnSync(process.env.IELTS_PYTHON||'python3',[path.join(root,'google-sheets-python.py')],{input:JSON.stringify({account:this.sa,url,method,data}),encoding:'utf8',maxBuffer:350*1024*1024,timeout:220000,windowsHide:true});let reply;try{reply=JSON.parse(p.stdout||'{}');}catch{throw Error('PYTHON_GOOGLE_RESPONSE_INVALID');}if(p.error||p.status!==0)throw Error('PYTHON_GOOGLE_TRANSPORT_FAILED');if(!reply.ok){if(reply.httpCode)r=new Response({status:reply.httpCode,bodyBase64:Buffer.from('{}').toString('base64')});else throw Error(reply.code||'NETWORK_OUTCOME_UNKNOWN');}else r=new Response({status:200,bodyBase64:Buffer.from(JSON.stringify(reply.result)).toString('base64')});}
   catch(e){if(e.message==='NETWORK_OUTCOME_UNKNOWN'&&['GET','PUT'].includes(method)&&attempt<2){pause(2000*(attempt+1));continue;}throw e;}
   if(r.getResponseCode()!==429||attempt===5)break;pause([5000,10000,20000,40000,60000][attempt]);
  }
  if(r.getResponseCode()<200||r.getResponseCode()>299){const e=Error('GOOGLE_HTTP_'+r.getResponseCode());e.httpCode=r.getResponseCode();throw e;}
  if(isSheet)this.metrics.sheetMs+=Date.now()-measuredAt;return JSON.parse(r.getContentText()||'{}');
 }
 book(id){if(!this.books.has(id))this.books.set(id,new Book(this,id));return this.books.get(id);}
 file(id){const g=this;return {getId:()=>id,isTrashed:()=>!!g.fileMeta(id).trashed,getMimeType:()=>g.fileMeta(id).mimeType,getSize:()=>Number(g.fileMeta(id).size),getLastUpdated:()=>new Date(g.fileMeta(id).modifiedTime),getBlob:()=>new Blob(request({url:'https://www.googleapis.com/drive/v3/files/'+id+'?alt=media',headers:{Authorization:'Bearer '+g.token()}}).bytes,g.fileMeta(id).mimeType),getName:()=>g.fileMeta(id).name};}
 fileMeta(id){const saved=this.fileMetadata.get(id);if(saved&&saved.until>Date.now())return saved.data;const data=this.api('https://www.googleapis.com/drive/v3/files/'+id+'?supportsAllDrives=true&fields=id,name,mimeType,size,modifiedTime,trashed,capabilities(canEdit),videoMediaMetadata(durationMillis)');this.fileMetadata.set(id,{data,until:Date.now()+60000});return data;}
 refreshFileMetadata(){this.fileMetadata.clear();}
 invalidate(){for(const b of this.books.values())b.cache.clear();}
 preloadSource(id,width=7,names=null){
  const b=this.book(id);b.cache.clear();const selected=names?b.sheets.filter(s=>names.includes(s.getName())):b.sheets;
  if(!selected.length)throw Error('SOURCE_TABS_MISSING');
  const ranges=selected.map(s=>quote(s.getName())+'!'+a1(1,1,s.meta.properties.gridProperties.rowCount,Math.min(width,s.meta.properties.gridProperties.columnCount)));
  const qs=ranges.map(r=>'ranges='+encodeURIComponent(r)).join('&');
  const x=this.api('https://sheets.googleapis.com/v4/spreadsheets/'+id+'?'+qs+'&includeGridData=true&fields=sheets(properties(title),data(rowData(values(effectiveValue,userEnteredValue,formattedValue,hyperlink,textFormatRuns,userEnteredFormat,dataValidation,note))))');
  for(const s of x.sheets||[])b.cache.set(s.properties.title+'|master',gridMaster(s.data?.[0]?.rowData||[],width));
 }
}
export function gridMaster(cells,width){
 const typed=v=>v?.numberValue??v?.stringValue??v?.boolValue??'';
 const m={width,cells,UNFORMATTED_VALUE:[],FORMATTED_VALUE:[],FORMULA:[]};let last=0;
 cells.forEach((r,i)=>{const values=(r.values||[]).slice(0,width);m.UNFORMATTED_VALUE.push(values.map(c=>typed(c.effectiveValue)));m.FORMATTED_VALUE.push(values.map(c=>c.formattedValue??String(typed(c.effectiveValue))));m.FORMULA.push(values.map(c=>c.userEnteredValue?.formulaValue??typed(c.effectiveValue)));if(values.some(c=>c.userEnteredValue!==undefined||typed(c.effectiveValue)!==''))last=i+1;});
 for(const mode of ['UNFORMATTED_VALUE','FORMATTED_VALUE','FORMULA'])m[mode].length=last;return m;
}
const col=n=>{let x='';for(;n;n=Math.floor((n-1)/26))x=String.fromCharCode(65+(n-1)%26)+x;return x;};
const quote=s=>"'"+s.replaceAll("'","''")+"'";
const a1=(r,c,nr,nc)=>col(c)+r+':'+col(c+nc-1)+(r+nr-1);
export class Book {
 constructor(g,id){this.g=g;this.id=id;this.cache=new Map();this.refresh();}
 refresh(){const m=this.g.api('https://sheets.googleapis.com/v4/spreadsheets/'+this.id+'?fields=spreadsheetId,properties(title),sheets(properties,merges)');this.meta=m;this.sheets=m.sheets.map(s=>new Sheet(this,s));}
 getId(){return this.id;}getUrl(){return 'https://docs.google.com/spreadsheets/d/'+this.id+'/edit';}
 invalidateSheet(name){for(const key of this.cache.keys())if(key.startsWith(name+'|'))this.cache.delete(key);}
 getSheets(){return this.sheets;} getSheetByName(n){return this.sheets.find(s=>s.getName()===n)||null;}
 insertSheet(n){this.batch([{addSheet:{properties:{title:n}}}]);this.refresh();return this.getSheetByName(n);}
 batch(requests){const r=this.g.api('https://sheets.googleapis.com/v4/spreadsheets/'+this.id+':batchUpdate','POST',{requests});this.cache.clear();return r;}
}
export class Sheet {
 constructor(book,meta){this.book=book;this.meta=meta;}
 getName(){return this.meta.properties.title;} getSheetId(){return this.meta.properties.sheetId;}
 getRange(r,c,nr=1,nc=1){if(typeof r==='string'){const m=/^([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?$/.exec(r);if(!m)throw Error('ADAPTER_RANGE_INVALID');const cn=s=>[...s].reduce((n,c)=>n*26+c.charCodeAt(0)-64,0);return new Range(this,+m[2],cn(m[1]),m[4]?+m[4]-+m[2]+1:1,m[3]?cn(m[3])-cn(m[1])+1:1);}return new Range(this,r,c,nr,nc);}
 table(){const master=this.book.cache.get(this.getName()+'|master');if(master)return {last:master.FORMATTED_VALUE.length,lastCol:Math.max(1,...master.FORMATTED_VALUE.map(r=>r.length))};const key=this.getName()+'|extent';if(!this.book.cache.has(key)){const max=this.meta.properties.gridProperties.rowCount;let last=0,lastCol=0;for(let start=1;start<=max;start+=5000){const v=this.values(a1(start,1,Math.min(5000,max-start+1),Math.min(/^(Jobs|RunnerArtifacts|RunnerReferences|Audit)$/.test(this.getName())?2:8,this.meta.properties.gridProperties.columnCount)),'FORMATTED_VALUE');v.forEach((r,i)=>{if(r.some(x=>x!=='')){last=start+i;lastCol=Math.max(lastCol,r.length);}});}this.book.cache.set(key,{last,lastCol});}return this.book.cache.get(key);}
 getLastRow(){return this.table().last;}getLastColumn(){const master=this.book.cache.get(this.getName()+'|master'),headers=master?master.FORMATTED_VALUE.slice(0,4):this.values(a1(1,1,4,this.meta.properties.gridProperties.columnCount),'FORMATTED_VALUE');return Math.max(this.table().lastCol,...headers.map(r=>r.length),this.meta.merges?.reduce((n,m)=>Math.max(n,m.endColumnIndex),0)||0);}
 getDataRange(){return this.getRange(1,1,Math.max(1,this.getLastRow()),Math.max(1,this.getLastColumn()));}
 values(range,render='UNFORMATTED_VALUE',fresh=false){const master=this.book.cache.get(this.getName()+'|master');if(master&&master[render]){const m=/^([A-Z]+)(\d+):([A-Z]+)(\d+)$/.exec(range);const cn=s=>[...s].reduce((n,c)=>n*26+c.charCodeAt(0)-64,0);if(m&&cn(m[3])<=(master.width||Infinity))return master[render].slice(+m[2]-1,+m[4]).map(r=>r.slice(cn(m[1])-1,cn(m[3])));}const key=this.getName()+'|'+range+'|'+render;if(fresh)this.book.cache.delete(key);if(!this.book.cache.has(key)){const uri=encodeURIComponent(quote(this.getName())+'!'+range);const data=this.book.g.api('https://sheets.googleapis.com/v4/spreadsheets/'+this.book.id+'/values/'+uri+'?valueRenderOption='+render+'&dateTimeRenderOption=SERIAL_NUMBER');this.book.cache.set(key,data.values||[]);}return this.book.cache.get(key);}
 appendRow(v){return this.appendRows([v]);}
 appendRows(v){const result=this.book.g.api('https://sheets.googleapis.com/v4/spreadsheets/'+this.book.id+'/values/'+encodeURIComponent(quote(this.getName())+'!A1')+':append?valueInputOption=RAW&insertDataOption=INSERT_ROWS','POST',{values:v.map(r=>r.map(serialize))});const m=/![A-Z]+(\d+)(?::[A-Z]+(\d+))?$/.exec(result.updates?.updatedRange||'');if(m){this.lastAppendRow=Number(m[1]);this.meta.properties.gridProperties.rowCount=Math.max(this.meta.properties.gridProperties.rowCount,Number(m[2]||m[1]));}this.book.invalidateSheet(this.getName());return this;}
 setFrozenRows(){return this;}setColumnWidth(){return this;}hideColumns(){return this;}autoResizeRows(){return this;}
}
const serialize=v=>v instanceof Date?v.toISOString():v;
function grid(r){return {sheetId:r.sheet.getSheetId(),startRowIndex:r.r-1,endRowIndex:r.r+r.nr-1,startColumnIndex:r.c-1,endColumnIndex:r.c+r.nc-1};}
export class Range {
 constructor(sheet,r,c,nr,nc){if(!Number.isInteger(r)||r<1||c<1||nr<1||nc<1)throw Error('ADAPTER_RANGE_INVALID');Object.assign(this,{sheet,r,c,nr,nc});}
 getRow(){return this.r;}getColumn(){return this.c;}getLastRow(){return this.r+this.nr-1;}getLastColumn(){return this.c+this.nc-1;}
 getCell(r,c){return new Range(this.sheet,this.r+r-1,this.c+c-1,1,1);}
 isPartOfMerge(){return this.getMergedRanges().length>0;}
 getDataValidation(){return this.cells()[0]?.values?.[0]?.dataValidation||null;}
 getA1Notation(){return this.nr===1&&this.nc===1?col(this.c)+this.r:a1(this.r,this.c,this.nr,this.nc);}
 matrix(render){const v=this.sheet.values(a1(this.r,this.c,this.nr,this.nc),render);return Array.from({length:this.nr},(_,i)=>Array.from({length:this.nc},(_,j)=>v[i]?.[j]??''));}
 getDisplayValues(){return this.matrix('FORMATTED_VALUE').map(r=>r.map(String));}getDisplayValue(){return this.getDisplayValues()[0][0];}
 getValues(){const v=this.matrix('UNFORMATTED_VALUE'),head=this.sheet.values('A1:A1','FORMATTED_VALUE')[0]?.[0];if(/DẤU THỜI GIAN/i.test(head||'')&&this.c===1)v.forEach((r,i)=>{if(this.r+i>1&&typeof r[0]==='number')r[0]=new Date(Math.round((r[0]-25569)*86400000)-25200000);});return v;}getValue(){return this.getValues()[0][0];}
 getFormulas(){return this.matrix('FORMULA').map(r=>r.map(v=>typeof v==='string'&&v.startsWith('=')?v:''));}getFormula(){return this.getFormulas()[0][0];}
 cells(){const master=this.sheet.book.cache.get(this.sheet.getName()+'|master');if(master?.cells)return master.cells.slice(this.r-1,this.r+this.nr-1).map(r=>({values:(r.values||[]).slice(this.c-1,this.c+this.nc-1)}));const range=encodeURIComponent(quote(this.sheet.getName())+'!'+this.getA1Notation());const x=this.sheet.book.g.api('https://sheets.googleapis.com/v4/spreadsheets/'+this.sheet.book.id+'?ranges='+range+'&includeGridData=true&fields=sheets(data(rowData(values(effectiveValue,formattedValue,hyperlink,textFormatRuns,userEnteredFormat,dataValidation,note))))');return x.sheets?.[0]?.data?.[0]?.rowData||[];}
 getRichTextValues(){const rows=this.cells(),values=this.getDisplayValues();return Array.from({length:this.nr},(_,i)=>Array.from({length:this.nc},(_,j)=>Rich.fromCell(rows[i]?.values?.[j]||{},values[i][j])));}
 getRichTextValue(){const x=this.cells()[0]?.values?.[0]||{};return Rich.fromCell(x,x.formattedValue??this.getDisplayValue());}
 getTextStyle(){if(!this.baseTextStyle){const f=this.cells()[0]?.values?.[0]?.userEnteredFormat?.textFormat||{};this.baseTextStyle={format:f,color:hex(f.foregroundColorStyle?.rgbColor||f.foregroundColor||{red:0.09,green:0.196,blue:0.3}),bold:!!f.bold};}return new Style({...this.baseTextStyle});}getNote(){return this.cells()[0]?.values?.[0]?.note||'';}canEdit(){return !!this.sheet.book.g.fileMeta(this.sheet.book.id).capabilities?.canEdit;}
 getMergedRanges(){return (this.sheet.meta.merges||[]).filter(m=>m.startRowIndex<this.r+this.nr-1&&m.endRowIndex>=this.r&&m.startColumnIndex<this.c+this.nc-1&&m.endColumnIndex>=this.c).map(m=>new Range(this.sheet,m.startRowIndex+1,m.startColumnIndex+1,m.endRowIndex-m.startRowIndex,m.endColumnIndex-m.startColumnIndex));}
 setValues(v){this.sheet.book.g.api('https://sheets.googleapis.com/v4/spreadsheets/'+this.sheet.book.id+'/values/'+encodeURIComponent(quote(this.sheet.getName())+'!'+this.getA1Notation())+'?valueInputOption=RAW','PUT',{values:v.map(r=>r.map(serialize))});const gp=this.sheet.meta.properties.gridProperties;gp.rowCount=Math.max(gp.rowCount,this.r+this.nr-1);gp.columnCount=Math.max(gp.columnCount,this.c+this.nc-1);this.sheet.book.invalidateSheet(this.sheet.getName());return this;}
 setValue(v){return this.setValues([[v]]);}clearContent(){this.sheet.book.g.api('https://sheets.googleapis.com/v4/spreadsheets/'+this.sheet.book.id+'/values/'+encodeURIComponent(quote(this.sheet.getName())+'!'+this.getA1Notation())+':clear','POST',{});this.sheet.book.invalidateSheet(this.sheet.getName());return this;}
 setRichTextValue(rich){const runs=rich.runs.map(r=>{const format={...(r.style.format||{}),foregroundColorStyle:{rgbColor:rgb(r.style.color)},bold:!!r.style.bold,...(r.link?{link:{uri:r.link}}:{})};delete format.foregroundColor;return {startIndex:r.start,format};});this.sheet.book.batch([{updateCells:{range:grid(this),rows:[{values:[{userEnteredValue:{stringValue:rich.text},textFormatRuns:runs,userEnteredFormat:{wrapStrategy:'WRAP',verticalAlignment:'TOP'}}]}],fields:'userEnteredValue,textFormatRuns,userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment'}}]);return this;}
 setNote(note){this.sheet.book.batch([{repeatCell:{range:grid(this),cell:{note},fields:'note'}}]);return this;}
 // Recovery changes character formatting only: never replace text or yellow/late backgrounds.
 setRichTextFormats(rich){if(this.nr!==1||this.nc!==1)throw Error('COLOR_REPAIR_RANGE_INVALID');const runs=rich.runs.map(r=>{const format={...(r.style.format||{}),foregroundColorStyle:{rgbColor:rgb(r.style.color)},bold:!!r.style.bold,...(r.link?{link:{uri:r.link}}:{})};delete format.foregroundColor;return {startIndex:r.start,format};});this.sheet.book.batch([{updateCells:{range:grid(this),rows:[{values:[{textFormatRuns:runs}]}],fields:'textFormatRuns'}}]);return this;}
 setWrap(){return this;}setFontColor(){return this;}setBackground(){return this;}setFontWeight(){return this;}setFontSize(){return this;}setVerticalAlignment(){return this;}setNumberFormat(){return this;}
}
const rgb=hex=>Object.fromEntries(['red','green','blue'].map((k,i)=>[k,parseInt((hex||'#17324d').slice(1+i*2,3+i*2),16)/255]));
const hex=rgb=>'#'+['red','green','blue'].map(k=>Math.round((rgb?.[k]||0)*255).toString(16).padStart(2,'0')).join('');
export class Style {constructor(v={}){this.v=v;}copy(){return new Style({...this.v});}setForegroundColor(color){this.v.color=color;return this;}setBold(bold){this.v.bold=bold;return this;}build(){return {...this.v};}getForegroundColor(){return this.v.color||'#17324d';}isBold(){return !!this.v.bold;}}
export class Rich {
 constructor(text='',runs=[]){this.text=text;this.runs=runs;}
 static fromCell(cell,text){const base=cell.userEnteredFormat?.textFormat||{},raw=cell.textFormatRuns||[];const starts=[...new Set([0,...raw.map(x=>x.startIndex||0)])].filter(x=>x<text.length).sort((a,b)=>a-b);return new Rich(text,starts.map((start,i)=>{const format={...base,...raw.find(x=>(x.startIndex||0)===start)?.format};return {start,end:starts[i+1]??text.length,style:{format,color:hex(format.foregroundColorStyle?.rgbColor||format.foregroundColor||{red:0.09,green:0.196,blue:0.3}),bold:!!format.bold},link:format.link?.uri||cell.hyperlink||null};}));}
 getText(){return this.text;}getRuns(){return this.runs.map(r=>({getText:()=>this.text.slice(r.start,r.end),getStartIndex:()=>r.start,getEndIndex:()=>r.end,getTextStyle:()=>new Style(r.style),getLinkUrl:()=>r.link||null}));}
 copy(){return new RichBuilder(this.text,this.runs.map(r=>({...r,style:{...r.style}})));}
}
export class RichBuilder {
 constructor(text='',runs=[]){this.text=text;this.runs=runs;}
 setText(text){this.text=text;this.runs=[{start:0,end:text.length,style:{color:'#17324d'}}];return this;}
 setTextStyle(a,b,style){if(b===undefined){this.runs.forEach(r=>r.style=a instanceof Style?a.build():a);return this;}this.runs=this.runs.flatMap(r=>{if(r.end<=a||r.start>=b)return [r];const out=[];if(r.start<a)out.push({...r,end:a});out.push({...r,start:Math.max(a,r.start),end:Math.min(b,r.end),style:style instanceof Style?style.build():style});if(r.end>b)out.push({...r,start:b});return out;});return this;}
 setLinkUrl(a,b,link){if(link===undefined){link=a;a=0;b=this.text.length;}this.runs.forEach(r=>{if(r.start>=a&&r.end<=b)r.link=link;});return this;}
 build(){return new Rich(this.text,this.runs);}
}
export function utilities(){return {DigestAlgorithm:{SHA_256:'sha256'},computeDigest:(_,x)=>[...createHash('sha256').update(typeof x==='string'?x:Buffer.from(x)).digest()],getUuid:randomUUID,sleep:pause,base64Encode:x=>Buffer.from(x).toString('base64'),newBlob:(x,mime)=>new Blob(typeof x==='string'?Buffer.from(x):x,mime),formatDate:(d,zone,fmt)=>{const z=new Intl.DateTimeFormat('en-GB',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(d).replace(',','');if(fmt==='dd/MM/yyyy HH:mm')return z;if(fmt==='yyyy-MM-dd'){const [day,month,year]=z.split(' ')[0].split('/');return `${year}-${month}-${day}`;}throw Error('UNSUPPORTED_DATE_FORMAT');}};}
