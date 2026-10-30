// A detailed returned assessment owns its mark. Prose is never a routing key.
const sections=d=>Array.isArray(d?.roseSections)?d.roseSections:Object.values(d?.sections||{});
export function scoredAssessment(d){
 if(!d||d.assessable===false)return false;
 const score=String(d.rubricBand??d.band??'').trim().match(/^(\d+(?:[.,]\d+)?)\s*%?$/);
 const number=score?Number(score[1].replace(',','.')):NaN;
 return Number.isFinite(number)&&number>=0&&number<=100&&sections(d).some(s=>[s?.text,s?.praise,s?.correction].some(v=>typeof v==='string'&&v.trim()));
}
export function completeScoredResponse(raw,d){
 const finish=raw?.candidates?.[0]?.finishReason;
 return !raw?.promptFeedback?.blockReason&&(!finish||finish==='STOP')&&scoredAssessment(d);
}
const identity=code=>{const m=String(code||'').normalize('NFD').replace(/\p{M}/gu,'').toUpperCase().match(/^(D[1-4]|FF[12]|OP[1-4])\s*(?:-\s*TIET\s*|-L\s*)(\d+)(?!\d)/);return m?{family:m[1],lesson:Number(m[2])}:null;};
export function explicitDistantAssignment(d,job){
 if(scoredAssessment(d))return false;
 const check=d?.submissionCheck;
 if(check?.status!=='wrong_assignment'&&check?.category!=='wrong_assignment')return false;
 // Only structured, explicit task codes count. Never parse teacher prose,
 // observedTask, titles, transcripts, topic words or rubric row positions.
 const expected=identity(job.receipt?.code||job.route?.code||job.source?.code);
 const observed=identity(check.observedCode);
 return !!expected&&!!observed&&(expected.family!==observed.family||Math.abs(expected.lesson-observed.lesson)>3);
}
export const SCORED_ASSESSMENT_INSTRUCTION='GIỮ ĐIỂM ĐÃ CHẤM: Nhãn Ngữ pháp/Đọc/Từ vựng và cách gọi tên chủ đề trong cùng Unit có thể khác nhau. Chấm phần học sinh thực hiện theo barem đã cung cấp; không kết luận nộp nhầm chỉ vì đọc văn bản hay câu mẫu của cùng Unit. Nếu đủ căn cứ chấm, trả assessable=true, điểm và đầy đủ lời chữa; lời diễn đạt trong nhận xét không được dùng để tự đổi mã bài. Chỉ khi hoàn toàn khác nội dung và không thể chấm mới trả wrong_assignment, không có điểm, cùng observedCode xác định được từ nguồn.';
