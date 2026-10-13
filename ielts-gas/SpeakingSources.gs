function isgDriveIds_(text) {
  const ids = []; const re = /(?:https:\/\/drive\.google\.com\/(?:file\/d\/|open\?id=|uc\?(?:export=download&)?id=))([A-Za-z0-9_-]{20,})/g;
  let m; while ((m = re.exec(String(text || '')))) if (ids.indexOf(m[1]) < 0) ids.push(m[1]);
  return ids;
}
function isgSourceRows_() {
  const book = SpreadsheetApp.openById(ISG.source), out = [];
  ISG.sourceTabs.forEach(name => {
    const sheet = book.getSheetByName(name); isgAssert_(sheet, 'SPEAKING_SOURCE_TAB_MISSING');
    if (sheet.getLastRow() < 2) return;
    const rows = sheet.getRange(1, 1, sheet.getLastRow(), sheet.getLastColumn()).getValues();
    const heads = rows.shift().map(isgNorm_);
    const unique = label => { const matches = heads.map((h, i) => h === label ? i : -1).filter(i => i >= 0); isgAssert_(matches.length === 1, 'SPEAKING_SOURCE_HEADER'); return matches[0]; };
    const ix = {time: unique('DAU THOI GIAN'), name: unique('HO VA TEN DAY DU'), className: unique('LOP'), code: unique('MA BAI')};
    const audio = heads.map((h, i) => /^(FILE GHI AM|GHI AM PHAN [12])$/.test(h) ? i : -1).filter(i => i >= 0);
    isgAssert_(audio.length, 'SPEAKING_AUDIO_HEADER_MISSING');
    rows.forEach((r, i) => {
      const className = isgClass_(r[ix.className]), code = isgCode_(r[ix.code]);
      if (!ISG.classes[className] || !code) return;
      const ids = Array.from(new Set(audio.reduce((a, c) => a.concat(isgDriveIds_(r[c])), [])));
      if (!ids.length) return;
      const at = r[ix.time];
      isgAssert_(at instanceof Date && !isNaN(at.getTime()), 'SPEAKING_SOURCE_TIMESTAMP');
      const s = {sheetId: sheet.getSheetId(), sheetName: name, row: i + 2, className, code,
        name: String(r[ix.name]).trim(), at: at.toISOString(), fileIds: ids};
      s.signature = isgHash_(s); out.push(s);
    });
  });
  return out.sort((a, b) => b.at.localeCompare(a.at) || b.row - a.row);
}
function isgLatest_(rows) {
  const seen = {};
  return rows.filter(s => { const k = s.className + '|' + isgName_(s.name) + '|' + s.code; if (seen[k]) return false; seen[k] = true; return true; });
}
function isgLatestStudents_(rows) {
  const seen = new Set();
  return rows.slice().sort((a,b)=>b.at.localeCompare(a.at)||b.row-a.row).filter(s=>{
    const key=s.className+'|'+isgName_(s.name); if(seen.has(key))return false; seen.add(key);return true;
  });
}
function isgEligibleStudents_(rows,since) { return isgLatestStudents_(rows).filter(s=>s.at>=since); }
function isgRolloutCandidates_(rows,since,activatedAt) {
  const initial=isgEligibleStudents_(rows.filter(s=>s.at<activatedAt),since).map(s=>({source:s,policy:'LATEST_STUDENT_CATCHUP'}));
  const incoming=isgLatest_(rows.filter(s=>s.at>=activatedAt&&s.at>=since)).map(s=>({source:s,policy:'NEW_SUBMISSION'}));
  return initial.concat(incoming);
}
function isgIsLatestStudent_(source) {
  const current=isgLatestStudents_(isgSourceRows_()).find(s=>s.className===source.className&&isgName_(s.name)===isgName_(source.name));
  return !!current&&current.signature===source.signature;
}
function isgFresh_(source) {
  const current = isgLatest_(isgSourceRows_()).find(s => s.className === source.className && isgName_(s.name) === isgName_(source.name) && s.code === source.code);
  isgAssert_(current && current.signature === source.signature, 'SPEAKING_SOURCE_CHANGED');
}
function isgGuideline_(code) {
  const sheet = SpreadsheetApp.openById(ISG.guide).getSheetByName(ISG.guideTab);
  isgAssert_(sheet, 'SPEAKING_GUIDELINES_MISSING');
  const rows = sheet.getRange(2, 1, Math.max(1, sheet.getLastRow() - 1), 3).getDisplayValues();
  const found = rows.filter(r => isgCode_(r[0]) === code);
  isgAssert_(found.length === 1 && found[0][1].trim() && found[0][2].trim(), 'SPEAKING_GUIDELINE_AMBIGUOUS');
  return {code, topic: found[0][1].trim(), instructions: found[0][2].trim()};
}
function isgHasFeedback_(text) {
  const s = String(text || '').trim(); if (!s) return false;
  const i = s.indexOf(ISG.marker);
  if (i >= 0) return !!s.slice(i + ISG.marker.length).trim() || isgHasFeedback_(s.slice(0,i));
  // Only known receipt-only lines may be replaced. Unknown prose is teacher feedback.
  return s.split(/\r?\n/).some(line => {
    const t = line.trim();
    return t && !/^(?:✅ ĐÃ NỘP|⚠️ ĐÃ NỘP MUỘN|⛔ QUÁ HẠN|— CHƯA GHI NHẬN|\d{1,2}\/\d{1,2}\/\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?)$/.test(t);
  });
}
function isgFindColumn_(headers, code) {
  const hits = [];
  for (let c = 0; c < headers[0].length; c++) {
    const column = headers.map(r => r[c] || '');
    const codes = column.join('\n').match(/IELTS-SPEAKING-S\d{1,2}(?!\d)/g) || [];
    if (/SPEAKING/.test(isgNorm_(column[0])) && /BAI TAP VE NHA/.test(isgNorm_(column[2])) && codes.some(v => isgCode_(v) === code)) hits.push(c + 1);
  }
  isgAssert_(hits.length === 1, 'SPEAKING_TARGET_COLUMN_AMBIGUOUS'); return hits[0];
}
function isgHeaders_(sheet) {
  const range=sheet.getRange(1,1,5,sheet.getLastColumn()),headers=range.getDisplayValues();
  range.getMergedRanges().forEach(r=>{
    const value=headers[r.getRow()-1]?.[r.getColumn()-1]??'';
    for(let y=r.getRow()-1;y<Math.min(5,r.getLastRow());y++)
      for(let x=r.getColumn()-1;x<r.getLastColumn();x++)headers[y][x]=value;
  });
  return headers;
}
/** Last day of a single or two-day lesson; never infer a date from its deadline. */
function isgLessonDate_(label) {
  const s=String(label||''),dates=[];
  const re=/(?:(\d{1,2})\s*-\s*)?(\d{1,2})\/(\d{1,2})\/(\d{4})/g;let m;
  while((m=re.exec(s))){
    const d=Number(m[2]),month=Number(m[3]),year=Number(m[4]),at=new Date(Date.UTC(year,month-1,d));
    isgAssert_(at.getUTCDate()===d&&at.getUTCMonth()===month-1,'SPEAKING_LESSON_DATE_INVALID');
    if(m[1])isgAssert_(Number(m[1])>0&&Number(m[1])<=d,'SPEAKING_LESSON_DATE_INVALID');
    dates.push(at.toISOString().slice(0,10));
  }
  return dates.sort().pop()||'';
}
function isgLastClassHomework_(headers,beforeDate) {
  const groups={};
  for(let c=0;c<headers[0].length;c++){
    if(!/SPEAKING/.test(isgNorm_(headers[0][c])))continue;
    const label=headers[1][c]||'',m=/BUOI(?: HOC)?(?: SO)?\s*(\d+)/.exec(isgNorm_(label));
    if(!m)continue;
    const date=isgLessonDate_(label);if(!date||date>=beforeDate)continue;
    const key=m[1]+'|'+date,g=groups[key]||(groups[key]={lesson:Number(m[1]),lessonDate:date,codes:[]});
    if(/BAI TAP VE NHA/.test(isgNorm_(headers[2][c]))){
      const code=isgCode_(headers[3][c]);if(code&&g.codes.indexOf(code)<0)g.codes.push(code);
    }
  }
  const sorted=Object.values(groups).sort((a,b)=>b.lessonDate.localeCompare(a.lessonDate));
  if(!sorted.length)return {status:'NO_COMPLETED_SPEAKING_LESSON',minimumLesson:5};
  const last=sorted[0];isgAssert_(sorted.length===1||sorted[1].lessonDate!==last.lessonDate,'SPEAKING_LAST_LESSON_AMBIGUOUS');
  const out={lesson:last.lesson,lessonDate:last.lessonDate,minimumLesson:Math.max(5,last.lesson)};
  if(last.lesson<5)return Object.assign(out,{status:'BELOW_LESSON_5'});
  if(!last.codes.length)return Object.assign(out,{status:'NO_HOMEWORK_LATEST_LESSON'});
  isgAssert_(last.codes.length===1&&Number(last.codes[0].slice(1))===last.lesson,'SPEAKING_LAST_HOMEWORK_AMBIGUOUS');
  isgFindColumn_(headers,last.codes[0]);return Object.assign(out,{status:'HOMEWORK',code:last.codes[0]});
}
function isgScopeAllows_(source) {
  const saved=isgProps_().getProperty('IELTS_SPEAKING_HOMEWORK_POLICY');if(!saved)return true;
  const policy=JSON.parse(saved),minimum=policy.minimumByClass[source.className];
  // The historical lesson floor does not exclude a freshly submitted homework.
  if(policy.newSubmissionsSince&&source.at>=policy.newSubmissionsSince)return true;
  return Number(source.code.slice(1))>=Math.max(5,minimum||5);
}
function isgTarget_(source) {
  const spreadsheetId = ISG.classes[source.className]; isgAssert_(spreadsheetId, 'SPEAKING_CLASS_UNCONFIGURED');
  const sheet = SpreadsheetApp.openById(spreadsheetId).getSheetByName(ISG.tab); isgAssert_(sheet, 'SPEAKING_TARGET_TAB_MISSING');
  const headers = isgHeaders_(sheet);
  const col = isgFindColumn_(headers, source.code);
  const names = sheet.getRange(7, 1, Math.max(1, sheet.getLastRow() - 6), 2).getDisplayValues();
  const matches = names.map((r, i) => /^\d+$/.test(r[0]) && Number(r[0]) > 0 && isgName_(String(r[1]).split(/\r?\n/)[0]) === isgName_(source.name) ? i + 7 : 0).filter(Boolean);
  isgAssert_(matches.length === 1, 'SPEAKING_STUDENT_AMBIGUOUS');
  const range = sheet.getRange(matches[0], col);
  isgAssert_(!range.getFormula() && !range.isPartOfMerge() && !range.getDataValidation(), 'SPEAKING_TARGET_NOT_PLAIN_CELL');
  return {spreadsheetId, range, address: range.getA1Notation(), text: range.getDisplayValue(), note: range.getNote()};
}
function isgAudioMime_(name,mime) {
  const ext=/\.([a-z0-9]+)$/i.exec(name),kind=ext?ext[1].toLowerCase():'';
  const byExt={m4a:'audio/m4a',mp3:'audio/mpeg',wav:'audio/wav',aac:'audio/aac',ogg:'audio/ogg',flac:'audio/flac'};
  const byMime={'audio/x-m4a':'audio/m4a','audio/m4a':'audio/m4a','audio/mp4':'audio/m4a','audio/mpeg':'audio/mpeg','audio/mp3':'audio/mpeg','audio/wav':'audio/wav','audio/x-wav':'audio/wav','audio/aac':'audio/aac','audio/ogg':'audio/ogg','audio/flac':'audio/flac','audio/x-flac':'audio/flac'};
  if(byMime[mime])return byMime[mime];
  if(byExt[kind]&&(mime==='application/octet-stream'||(kind==='m4a'&&mime==='video/mp4')))return byExt[kind];
  throw Error('SPEAKING_AUDIO_FORMAT_UNSUPPORTED');
}
function isgMedia_(source) {
  isgAssert_(source.fileIds.length <= ISG.maxFiles, 'SPEAKING_TOO_MANY_FILES');
  const files = source.fileIds.map(id => {
    const f = DriveApp.getFileById(id), mime = f.getMimeType(), name = f.getName();
    if(source.at>=ISG.audioOnlySince){
      try{isgAudioMime_(name,mime);}catch(e){if(/^video\//.test(mime))throw Error('SPEAKING_AUDIO_REQUIRED');throw e;}
    }
    isgAssert_(!f.isTrashed(), 'SPEAKING_FILE_TRASHED');
    const originalModified=f.getLastUpdated().toISOString();
    let prepared;const saved=isgProps_().getProperty('IELTS_SPEAKING_PREPARED_AUDIO_'+id);
    if(saved){
      const p=JSON.parse(saved);isgAssert_(source.className==='IELTS 49'&&p.originalSize===f.getSize()&&p.originalModified===originalModified,'SPEAKING_PREPARED_SOURCE_CHANGED');
      prepared=DriveApp.getFileById(p.preparedId);
      isgAssert_(!prepared.isTrashed()&&prepared.getSize()===p.size&&prepared.getLastUpdated().toISOString()===p.preparedModified,'SPEAKING_PREPARED_AUDIO_CHANGED');
    }
    const audioMime=isgAudioMime_(prepared?prepared.getName():name,prepared?prepared.getMimeType():mime);
    const audioSize=prepared?prepared.getSize():f.getSize();isgAssert_(audioSize>0,'SPEAKING_AUDIO_EMPTY');
    const result={id,size:audioSize,modified:originalModified,mime:audioMime};
    if(prepared){result.preparedId=prepared.getId();result.preparedModified=prepared.getLastUpdated().toISOString();}
    return result;
  });
  isgAssert_(files.reduce((n, f) => n + f.size, 0) <= ISG.maxBytes, 'SPEAKING_AUDIO_TOTAL_OVER_12_MIB');
  return files;
}
