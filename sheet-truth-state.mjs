// Shared, explicit class-cell states. A queue acknowledgement is not a grade.
import {receiptDate} from './master-policy.mjs';
export const SHEET_TRUTH_VERSION='teacher-sheet-truth-20261023';
export const PENDING_BODY='⏳ ĐANG CHỜ CHẤM — Hệ thống đã nhận bài và đang xử lý. Không cần nộp lại.';
export const TECHNICAL_BODY='⏳ ĐANG CHỜ XỬ LÝ — Hệ thống đang kiểm tra hoặc khôi phục kết quả. Không cần nộp lại.';
export const sheetTruthEnabled=()=>process.env.SHEET_TRUTH_SYNC==='true';
export const isWaitingFeedback=text=>{const body=String(text||'').split(/NHẬN XÉT GV\s*[—–-]*/u).slice(1).join('').trim();return body===PENDING_BODY||body===TECHNICAL_BODY;};
export const isResubmissionFeedback=text=>/(?:^|\n)\s*(?:❌\s*)?CẦN[ _]NỘP[ _]LẠI|^ĐÃ NỘP — Link (?:cần mở quyền xem|không hợp lệ)/u.test(String(text||''));
export const sourceTime=s=>receiptDate(s?.at??s?.time,new Date(0)).getTime();
export const sourceTask=s=>[s?.className,String(s?.name||s?.student||'').normalize('NFC').trim().toUpperCase(),s?.code].join('|');
export function receiptTimeFromCell(text){const m=String(text||'').match(/(\d{1,2})\/(\d{1,2})\/(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?/);return m?Date.parse(`${m[3]}-${m[2].padStart(2,'0')}-${m[1].padStart(2,'0')}T${m[4].padStart(2,'0')}:${m[5]}:${m[6]||'00'}+07:00`):0;}
export function mayReopenNotice(source,text,jobs=[],approved=false){
 if(!isResubmissionFeedback(text))return false;if(approved)return true;
 const held=jobs.filter(x=>sourceTask(x.source||x.receipt)===sourceTask(source)&&isResubmissionFeedback(x.autoNotice||'')).map(x=>sourceTime(x.source||x.receipt));
 const previous=held.length?Math.max(...held):receiptTimeFromCell(text);return previous>0&&sourceTime(source)>previous;
}
export function sourceInputReason(j){
 const s=j.sourceIntake;if(s?.state==='missing')return 'Bài nộp chưa đính kèm link video/file. Vui lòng nộp lại kèm tệp hoặc link bài.';
 if(s?.state==='access')return 'Không truy cập được tệp (quyền xem bị từ chối). Vui lòng bật quyền bất kỳ ai có link đều xem được rồi nộp lại.';
 if(s?.state==='invalid')return s.reason==='EMPTY_OR_REMOVED_FILE'?'Tệp bài nộp rỗng hoặc đã bị xóa. Vui lòng tải lại tệp đầy đủ.':s.reason==='UNSUPPORTED_FILE_FORMAT'?'Tệp đính kèm không chứa định dạng bài được giao. Vui lòng kiểm tra và nộp lại đúng tệp.':'Link bài nộp không hợp lệ hoặc tệp không còn tồn tại. Vui lòng kiểm tra và nộp lại link đúng.';
 const e=String(j.error||j.internalDiagnostic||'');
 if(/^(?:SOURCE_HTTP_403|SOURCE_ACCESS_REQUIRED|YOUTUBE_UNAVAILABLE)$/.test(e))return 'Link bài nộp chưa mở quyền xem. Vui lòng bật quyền công khai/bất kỳ ai có link rồi nộp lại.';
 if(/^(?:SOURCE_HTTP_(?:404|410)|SOURCE_NOT_FOUND|SPEAKING_AUDIO_EMPTY|PREFLIGHT_FILE_MISSING_OR_INVALID)$/.test(e))return 'Tệp bài nộp rỗng, đã xóa hoặc không còn tồn tại. Vui lòng tải lại tệp đầy đủ.';
 // A model's assessable=false is NOT evidence of acoustic silence or a bad video.
 if((j.media||[]).filter(m=>!m.isReference).length&&(j.media||[]).filter(m=>!m.isReference).every(m=>m.localSilence?.silent===true))return 'Tệp không có tiếng nói theo kiểm tra âm thanh trực tiếp. Vui lòng kiểm tra micro và nộp lại bản có tiếng.';
 if(e==='LOCAL_OLD_GRADED_FILE')return 'Tệp này đã dùng cho bài cũ được nhận xét trước đó. Vui lòng nộp đúng tệp của bài hiện tại.';
 return null;
}
