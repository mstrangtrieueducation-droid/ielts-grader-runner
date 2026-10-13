function isgLease_(fn) {
  const token = Utilities.getUuid();
  isgLock_(() => {
    const p = isgProps_(), old = JSON.parse(p.getProperty('IELTS_SPEAKING_LEASE') || '{}');
    isgAssert_(!old.until || old.until < Date.now(), 'SPEAKING_BUSY');
    p.setProperty('IELTS_SPEAKING_LEASE', JSON.stringify({token, until:Date.now() + 8 * 60000}));
  });
  try { return fn(); }
  finally { isgLock_(() => { const p = isgProps_(); if (JSON.parse(p.getProperty('IELTS_SPEAKING_LEASE') || '{}').token === token) p.deleteProperty('IELTS_SPEAKING_LEASE'); }); }
}
function isgJobs_(sheet) {
  if (sheet.getLastRow() < 2) return [];
  return sheet.getRange(2, 6, sheet.getLastRow() - 1, 1).getValues().map((r, i) => ({row:i + 2, job:JSON.parse(r[0])}));
}
function isgEnqueue_(sheet, source, mode) {
  const id = isgHash_([ISG.version, mode, source.signature]);
  const existing = isgJobs_(sheet).find(j => j.job.id === id); if (existing) return existing;
  const job = {id, source, mode, status:'QUEUED', attempts:0};
  const row = sheet.getLastRow() + 1; isgSave_(sheet, row, job); return {job, row};
}
function isgPreview_(job, rich) {
  const book = isgControl_();
  let sheet = book.getSheetByName(ISG.preview);
  if (!sheet) {
    sheet = book.insertSheet(ISG.preview);
    sheet.getRange('A1:D1').setValues([['Học sinh / lớp / mã bài', 'Nhận xét chấm thử — chưa trả học sinh', 'Trạng thái', 'Job ID']])
      .setBackground('#17324D').setFontColor('#FFFFFF').setFontWeight('bold');
    sheet.setFrozenRows(1); sheet.setColumnWidth(1, 240); sheet.setColumnWidth(2, 880); sheet.setColumnWidth(3, 210); sheet.hideColumns(4);
  }
  const ids = sheet.getLastRow() > 1 ? sheet.getRange(2, 4, sheet.getLastRow() - 1, 1).getDisplayValues() : [];
  const found = ids.findIndex(r => r[0] === job.id), row = found < 0 ? sheet.getLastRow() + 1 : found + 2;
  sheet.getRange(row, 1, 1, 4).setValues([[job.source.name + '\n' + job.source.className + ' · ' + job.source.code, '', job.gradeUsable ? 'CHỜ CÔ DUYỆT' : 'CẦN KIỂM TRA ÂM THANH', job.id]]);
  sheet.getRange(row, 2).setRichTextValue(rich);
  sheet.getRange(row, 1, 1, 3).setWrap(true).setVerticalAlignment('top').setFontSize(11);
  sheet.autoResizeRows(row, 1);
  isgAssert_(sheet.getRange(row, 2).getDisplayValue() === rich.getText(), 'SPEAKING_PREVIEW_READBACK');
  const url = book.getUrl() + '#gid=' + sheet.getSheetId() + '&range=B' + row;
  isgProps_().setProperty('IELTS_SPEAKING_PREVIEW_URL', url); return url;
}
function isgRichSignature_(rich) {
  const out=[];
  rich.getRuns().forEach(r=>{
    const color=String(r.getTextStyle().getForegroundColor()||'').toLowerCase(),link=r.getLinkUrl()||'';
    const prev=out[out.length-1];
    if(prev&&prev.color===color&&prev.link===link)prev.text+=r.getText();
    else out.push({text:r.getText(),color,link});
  });
  return JSON.stringify(out);
}
function isgWrite_(job, rich) {
  isgFresh_(job.source);
  isgAssert_(isgScopeAllows_(job.source),'SPEAKING_OUTSIDE_HOMEWORK_SCOPE');
  if(job.selectionPolicy==='LATEST_STUDENT_CATCHUP')isgAssert_(isgIsLatestStudent_(job.source),'SPEAKING_SUPERSEDED_SUBMISSION');
  const target = isgTarget_(job.source), stamp = '[IELTS_SPEAKING_AI:' + job.id + ']';
  if (target.note.indexOf(stamp) >= 0 && target.text === rich.getText()) return 'DONE';
  if (isgHasFeedback_(target.text)) return 'SKIPPED_EXISTING_FEEDBACK';
  isgAssert_(target.spreadsheetId === job.target.spreadsheetId && target.address === job.target.address && target.text === job.target.text && target.note === job.target.note, 'SPEAKING_TARGET_CHANGED');
  if (!job.beforeId) { const prior=target.range.getRichTextValue(); job.beforeId = isgArtifact_(job.id + '-before', {source:job.source, target:job.target, rich:(prior?prior.getRuns():[]).map(r => ({text:r.getText(), link:r.getLinkUrl(), color:r.getTextStyle().getForegroundColor(), bold:r.getTextStyle().isBold()}))}); }
  // Re-read immediately before writing. Other projects cannot share this script's lock.
  isgAssert_(target.range.getDisplayValue() === target.text && target.range.getNote() === target.note && !target.range.getFormula(), 'SPEAKING_TARGET_CHANGED');
  target.range.setRichTextValue(rich);
  target.range.setNote((target.note ? target.note + '\n' : '') + stamp + '\nModel: ' + (job.requestModel||ISG.model) + '\nSource: ' + job.source.signature);
  SpreadsheetApp.flush();
  isgAssert_(target.range.getDisplayValue() === rich.getText(), 'SPEAKING_WRITE_READBACK');
  isgAssert_(isgRichSignature_(target.range.getRichTextValue())===isgRichSignature_(rich), 'SPEAKING_STYLE_READBACK');
  return 'DONE';
}
function isgProcess_(sheet, item) {
  const job = item.job, save = () => isgSave_(sheet, item.row, job);
  // A new lease is acquired only after the former execution's lease has expired.
  // PROCESSING is checkpointed before the paid call; GENERATING is checkpointed before sending it.
  if(job.status==='PROCESSING'){job.status=job.rawId?'GENERATED':'QUEUED';save();}
  if (job.status==='GENERATING' && !job.rawId) {
    job.status = 'NEEDS_REVIEW'; job.error = 'SPEAKING_PREVIOUS_RUN_INTERRUPTED'; save(); return job;
  }
  if (['QUEUED','RETRY','GENERATED'].indexOf(job.status) < 0) return job;
  delete job.retryAt;
  try {
    isgKey_();
    if(job.mode==='live'&&!isgScopeAllows_(job.source)){job.status='SKIPPED_SCOPE';save();return job;}
    job.status = 'PROCESSING'; save();
    isgFresh_(job.source);
    if(job.selectionPolicy==='LATEST_STUDENT_CATCHUP'&&!isgIsLatestStudent_(job.source)){job.status='SKIPPED_NEWER_SUBMISSION';save();return job;}
    const target = isgTarget_(job.source);
    if (isgHasFeedback_(target.text)) { job.status = 'SKIPPED_EXISTING_FEEDBACK'; save(); return job; }
    if(job.mode==='live')isgAssert_(target.range.canEdit(),'SPEAKING_TARGET_WRITE_PERMISSION');
    const guide = isgGuideline_(job.source.code), media = isgMedia_(job.source);
    isgBindCostModel_(job,save);
    let inputHash = isgHash_({guide, media, model:job.requestModel, version:ISG.version});
    if (job.inputHash) isgAssert_(job.inputHash === inputHash, 'SPEAKING_INPUT_CHANGED');
    else {
      job.inputHash = inputHash;
      job.target = {spreadsheetId:target.spreadsheetId, address:target.address, text:target.text, note:target.note};
      job.inputId = isgArtifact_(job.id + '-input', {guide, media, source:job.source, target:job.target}); save();
    }
    const grade = job.rawId ? isgParseResponse_(isgReadArtifact_(job.rawId), media.length,job.promptVersion) : isgCallGemini_(job, media, guide, save);
    inputHash=job.inputHash;
    job.gradeUsable = grade.usable;
    isgFresh_(job.source);
    isgAssert_(isgHash_({guide:isgGuideline_(job.source.code), media:isgMedia_(job.source), model:job.requestModel, version:ISG.version}) === inputHash, 'SPEAKING_INPUT_CHANGED');
    job.gradeId = job.gradeId || isgArtifact_(job.id + '-grade', grade);
    const rich = isgRichText_(grade, job.source, job.mode === 'live');
    if(job.selectionPolicy==='LATEST_STUDENT_CATCHUP'&&!isgIsLatestStudent_(job.source)){job.status='SKIPPED_NEWER_SUBMISSION';save();return job;}
    if (job.mode === 'preview' || !grade.usable) { job.previewUrl = isgPreview_(job, rich); job.status = grade.usable ? 'PREVIEW_READY' : 'NEEDS_REVIEW'; }
    else job.status = isgWrite_(job, rich);
    if (job.apiFailure) { job.recoveredFailures = (job.recoveredFailures || []).concat([job.apiFailure]); delete job.apiFailure; }
    delete job.error; delete job.retryAt; save();
  } catch (e) {
    // Raw API bodies, API keys, media and URL query strings never enter logs.
    job.error = /^SPEAKING_[A-Z0-9_]+$/.test(String(e.message)) ? e.message : 'SPEAKING_INTERNAL_ERROR';
    if(job.error==='SPEAKING_INTERNAL_ERROR')job.internalDiagnostic=String(e.message||'').replace(/https?:\/\/\S+/g,'[URL]').slice(0,350);
    const uncertain = ['SPEAKING_API_OUTCOME_UNKNOWN','SPEAKING_INTERNAL_ERROR'].indexOf(job.error) >= 0 && job.status === 'GENERATING' && !job.rawId;
    // Failed jobs are logged and skipped; they never delay the next student.
    job.status = 'NEEDS_REVIEW'; delete job.retryAt;
    save();
  }
  return job;
}
