import {percentBand,receiptDate} from './master-policy.mjs';
export const COMPLETION_VERSION='content-completion-caps-v1-20261014';
export const COMPLETION_INSTRUCTION=`Kiểm tra KHỐI LƯỢNG HOÀN THÀNH trên toàn bộ barem và tất cả tệp học sinh trong cùng một lượt chấm. completionCheck: assessed chỉ true khi có căn cứ; completedFraction là phần nội dung thực sự hoàn thành (0–1), không dùng tỉ lệ thời lượng video. missingParts nêu đúng tên phần/câu hỏi còn thiếu, basis ghi căn cứ. Không mặc định con đã làm đủ chỉ vì phần từ vựng tốt. Bỏ 1–2 câu nhỏ: tối đa 85% (80–85% khi các mặt còn lại tốt). Bỏ hẳn một phần quan trọng hoặc thiếu 30–50% nội dung: tối đa 60%, bắt buộc Cần theo dõi, chỉ rõ phần bỏ sót và yêu cầu quay bổ sung. Hoàn thành dưới 50%: dưới 60%, CẦN NỘP LẠI (Chưa hoàn thành đủ nội dung bài học). Không tăng điểm thấp do lỗi khác. Không nói giảm thành 'hãy thử thách bản thân ở bài sau' khi con chưa hoàn thành bài hiện tại. Không bịa phần thiếu khi chưa có căn cứ; hình thức thuyết trình sai vẫn ưu tiên không điểm theo quy tắc riêng.`;
export const completionSchema={type:'object',properties:{assessed:{type:'boolean'},completedFraction:{type:'number',minimum:0,maximum:1},majorPartOmitted:{type:'boolean'},minorMissingSentences:{type:'integer',minimum:0},missingParts:{type:'array',items:{type:'string'}},basis:{type:'string'}},required:['assessed','completedFraction','majorPartOmitted','minorMissingSentences','missingParts','basis'],additionalProperties:false};
export function completionDecision(draft,j={}){
 if(j.route?.kind==='ielts_speaking'||draft.assessable===false)return null;
 const c=j.teacherConfirmedCompletion||draft.completionCheck;if(!c?.assessed||!Number.isFinite(c.completedFraction)||c.completedFraction<0||c.completedFraction>1)return null;
 const missing=c.missingParts?.filter(s=>typeof s==='string'&&s.trim())||[];
 if(c.completedFraction<0.5)return {cap:55,resubmit:true,missing};
 if(c.majorPartOmitted||c.completedFraction<=0.7)return {cap:60,resubmit:false,missing};
 if(c.minorMissingSentences>=1&&c.minorMissingSentences<=2)return {cap:85,resubmit:false,missing};
 return null;
}
export function applyCompletionPolicy(draft,j={}){
 const decision=completionDecision(draft,j);if(!decision)return draft;
 const g=structuredClone(draft),score=percentBand(String(g.rubricBand||g.band||'').replace('%',''));
 if(score!==null){g.band=Math.min(score,decision.cap)+'%';g.rubricBand=g.band;}
 g.forceAttention=decision.cap<75;g.completionPolicy={version:COMPLETION_VERSION,...decision};
 if(decision.cap<=60){
  const sections=Array.isArray(g.roseSections)?g.roseSections:Object.values(g.sections||{}),s=sections.find(s=>/thuộc lời|nội dung|đọc đúng|dịch đúng/i.test(s.label))||sections[0];
  if(s){s.text=s.text.replace(/(?:Ở những bài sau[^.!?]*[.!?]|Con hãy thử thách bản thân[^.!?]*[.!?])/gi,'').trim();
   if(!/bỏ sót|chưa hoàn thành|còn thiếu/i.test(s.text))s.text+='\nCon chưa hoàn thành '+(decision.missing.length?decision.missing.join('; '):'đầy đủ nội dung bài học')+'.';
   if(!/quay (?:bổ sung|lại)/i.test(s.text))s.text+=' Con cần quay bổ sung phần còn thiếu để hoàn thành trọn vẹn bài học nhé!';delete s.spans;
  }
 }
 return g;
}
export function incompleteFeedback(draft,j,render){
 const g=applyCompletionPolicy(draft,j);if(!g.completionPolicy?.resubmit)return null;
 const result=render(g),stamp=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Bangkok',dateStyle:'short',timeStyle:'short',hourCycle:'h23'}).format(receiptDate(j.receipt?.time)).replace(',','');
 result.text=result.text.replace(/^[\s\S]*?(?=— NHẬN XÉT GV —)/,'❌ CẦN NỘP LẠI (Chưa hoàn thành đủ nội dung bài học) '+stamp+'\n');
 return {...result,status:'COMPLETED_INCOMPLETE_RESUBMISSION'};
}
