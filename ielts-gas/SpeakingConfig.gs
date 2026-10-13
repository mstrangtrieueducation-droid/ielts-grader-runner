/** IELTS Speaking homework grader. Disabled until the teacher reviews the pilot. */
const ISG = Object.freeze(JSON.parse(PropertiesService.getScriptProperties().getProperty('IELTS_SPEAKING_NATIVE_CONFIG') || '{}'));

function isgProps_() { return PropertiesService.getScriptProperties(); }
function isgAssert_(ok, code) { if (!ok) throw new Error(code); }
function isgName_(v) { return String(v || '').normalize('NFC').trim().replace(/\s+/g, ' ').toUpperCase(); }
function isgNorm_(v) { return isgName_(v).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/Đ/g, 'D'); }
function isgCode_(v) {
  const s = String(v || '').trim().toUpperCase();
  const m = /(?:^|[^A-Z0-9])S(\d{1,2})(?!\d)/.exec(s) || /^(\d{1,2})$/.exec(s);
  return m && Number(m[1]) > 0 ? 'S' + ('0' + Number(m[1])).slice(-2) : '';
}
function isgClass_(v) {
  const m = /^IELTS\s*(\d+)(?:\.[12])?$/.exec(isgName_(v));
  return m ? 'IELTS ' + Number(m[1]) : '';
}
function isgHash_(v) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, JSON.stringify(v))
    .map(b => ('0' + ((b + 256) % 256).toString(16)).slice(-2)).join('');
}
let isgOwnerVerified_ = false;
function isgLock_(fn) {
  // Every mutation executes as the dashboard owner. A user lock isolates this
  // queue from long-running dashboard refreshes that use the project script lock.
  if (!isgOwnerVerified_) {
    const owner = DriveApp.getRootFolder().getOwner();
    isgAssert_(owner && String(owner.getEmail()).toLowerCase() === ISG.owner, 'SPEAKING_OWNER_REQUIRED');
    isgOwnerVerified_ = true;
  }
  const lock = LockService.getUserLock();
  isgAssert_(lock.tryLock(15000), 'SPEAKING_BUSY');
  try { return fn(); } finally { lock.releaseLock(); }
}
function isgKey_() {
  const key = (isgProps_().getProperty('IELTS_SPEAKING_GEMINI_API_KEY') || '').trim();
  isgAssert_(key && !/[\s,]/.test(key), 'SPEAKING_API_KEY_MISSING');
  return key;
}
function isgTable_() {
  const book = isgControl_();
  let sheet = book.getSheetByName(ISG.jobs);
  if (!sheet) {
    sheet = book.insertSheet(ISG.jobs);
    sheet.getRange(1, 1, 1, 6).setValues([['Job ID', 'Trạng thái', 'Cập nhật', 'Thử lại sau', 'Số lần API', 'Checkpoint']]);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, 6).setFontWeight('bold').setBackground('#17324D').setFontColor('#FFFFFF');
    sheet.setColumnWidths(1, 2, 180); sheet.setColumnWidths(3, 2, 160);
    sheet.hideColumns(6);
  }
  return sheet;
}
function isgControl_() {
  let id = isgProps_().getProperty('IELTS_SPEAKING_CONTROL_ID');
  if (!id) {
    const book = SpreadsheetApp.create('IELTS SPEAKING — Điều phối chấm Gemini');
    id = book.getId(); isgProps_().setProperty('IELTS_SPEAKING_CONTROL_ID', id);
    book.getSheets()[0].setName('HƯỚNG DẪN');
    book.getSheets()[0].getRange('A1:B5').setValues([
      ['IELTS SPEAKING · CHẤM BÀI TẬP VỀ NHÀ','BẢN THỬ — CHƯA BẬT TỰ ĐỘNG'],
      ['Model',ISG.model],['Chấm thử','Chạy testChamIeltsSpeaking trong Apps Script để xem nhận xét ở tab SPEAKING CHẤM THỬ.'],
      ['Bật sau khi duyệt','Chạy enableIeltsSpeakingAutomation; chỉ nhận bài nộp từ thời điểm bật.'],
      ['Dừng','Chạy stopIeltsSpeakingAutomation. Nhận xét có sẵn được giữ nguyên.']
    ]).setWrap(true).setVerticalAlignment('top');
    book.getSheets()[0].getRange('A1:B1').setBackground('#17324D').setFontColor('#FFFFFF').setFontWeight('bold');
    book.getSheets()[0].setColumnWidth(1,300); book.getSheets()[0].setColumnWidth(2,740);
  }
  return SpreadsheetApp.openById(id);
}
function isgSave_(sheet, row, job) {
  job.updatedAt = new Date().toISOString();
  sheet.getRange(row, 1, 1, 6).setValues([[job.id, job.status, job.updatedAt, job.retryAt || '', job.attempts || 0, JSON.stringify(job)]]);
  SpreadsheetApp.flush();
}
function isgArtifact_(label, value) {
  let id = isgProps_().getProperty('IELTS_SPEAKING_ARTIFACT_FOLDER');
  if (!id) { id = DriveApp.createFolder('IELTS Speaking AI - Hồ sơ chấm riêng').getId(); isgProps_().setProperty('IELTS_SPEAKING_ARTIFACT_FOLDER', id); }
  return DriveApp.getFolderById(id).createFile(label + '.json', JSON.stringify(value), 'application/json').getId();
}
function isgReadArtifact_(id) { return JSON.parse(DriveApp.getFileById(id).getBlob().getDataAsString('UTF-8')); }