import {receiptDate} from './master-policy.mjs';import {confirmedScriptReading} from './presentation-resubmission.mjs';
export const PRESENTATION_RESUBMISSION_STATUS='COMPLETED_PRESENTATION_RESUBMISSION';
export const PRESENTATION_KINDS=new Set(['de','scienceK','science','critical','project']);
export const PRESENTATION_REASON='Bài học yêu cầu con tự thuyết trình trực diện (thấy rõ khuôn mặt, ánh mắt nhìn camera và cử chỉ tay tương tác). Video của con đang chỉ quay màn hình/chĩa vào máy tính/đọc bài viết sẵn, chưa đạt yêu cầu thuyết trình.';
export const PRESENTATION_PRACTICE='Con hãy nhìn vào hình ảnh/mindmap, tập nói thành câu hoàn chỉnh và nhờ bố mẹ quay trực diện thấy người con nộp lại cho cô nhé!';
export const STRICT_PRESENTATION_RULE='QUY TẮC ƯU TIÊN CAO NHẤT CHO BÀI THUYẾT TRÌNH D.E, Science K/G1–G3, Critical, Project: nếu ảnh xác nhận chỉ quay màn hình/chĩa vào laptop/TV không thấy mặt con, hoặc đọc bài viết sẵn, phải assessable=false, band rỗng, roseSections=[]; không cho 75%, 80%, 65%, không chữa chi tiết phát âm/từ vựng. presentationVisualCheck confirmed=true, studentVisible=false, capture=screen_only hoặc filming_screen, basis quan sát cụ thể, sourceFileIndex đúng. Nếu đọc bài viết sẵn thì presentationReadingCheck ghi đúng bằng chứng. Không suy đọc giấy từ giọng yếu/chậm hoặc một lần nhìn xuống. Không áp quy tắc này cho Shadowing/Peppa/bài đọc hay bài cho phép đọc văn bản.';
export function presentationNotice(j){
 const stamp=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Bangkok',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(receiptDate(j.receipt?.time||j.source?.time||j.source?.at)).replace(',','');
 return {text:'❌ CẦN NỘP LẠI '+stamp+'\n— NHẬN XÉT GV —\nChất lượng: Chưa đạt (Yêu cầu quay lại).\n• Lý do yêu cầu nộp lại: '+PRESENTATION_REASON+'\n• Hướng dẫn luyện tập: '+PRESENTATION_PRACTICE,score:null,status:PRESENTATION_RESUBMISSION_STATUS,sections:[{label:'Lý do yêu cầu nộp lại',text:PRESENTATION_REASON,spans:[{text:PRESENTATION_REASON,tone:'correction'}]},{label:'Hướng dẫn luyện tập',text:PRESENTATION_PRACTICE,spans:[{text:PRESENTATION_PRACTICE,tone:'praise'}]}]};
}
export function knownInvalidPresentation(j,history=[]){
 const previous=history.map(x=>x.job||x).filter(p=>p.route?.code===j.route?.code).flatMap(p=>p.presentationResubmissionRequired?.invalidFileIds||[]),invalid=[...(j.presentationResubmissionRequired?.invalidFileIds||[]),...previous],current=[...(j.media||[]).filter(m=>!m.isReference).map(m=>m.id),...String(j.receipt?.links||j.source?.link||'').matchAll(/(?:[?&]id=|\/d\/)([-\w]{20,})/g)].filter(Boolean).map(v=>typeof v==='string'?v:v[1]);
 return PRESENTATION_KINDS.has(j.route?.kind)&&invalid.length>0&&current.some(id=>invalid.includes(id));
}
export function confirmedPresentationMismatch(draft,j,snapshot={}){
 if(!PRESENTATION_KINDS.has(j.route?.kind||snapshot.kind))return false;
 if(knownInvalidPresentation(j)||confirmedScriptReading(draft,j,snapshot))return true;
 const x=draft.presentationVisualCheck,visual=j.masterVisualFileIndexes||[];
 return x?.confirmed===true&&x.studentVisible===false&&['screen_only','filming_screen'].includes(x.capture)&&!!x.basis?.trim()&&visual.includes(x.sourceFileIndex);
}
