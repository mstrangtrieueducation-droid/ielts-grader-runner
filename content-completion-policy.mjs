import {percentBand,receiptDate} from './master-policy.mjs';
import {applyScreenGrounding,completedScreenScope,hasSupportedOmission,onlyTheoryOmissions,SCREEN_FIRST_INSTRUCTION} from './screen-grounding.mjs';
export const COMPLETION_VERSION='content-completion-caps-v1-20261014';
export const COMPLETION_INSTRUCTION=SCREEN_FIRST_INSTRUCTION+`\nKiểm tra KHỐI LƯỢNG HOÀN THÀNH của ĐỀ THỰC HÀNH được giao, không phải mọi ví dụ trong barem. completionCheck.assessed chỉ true khi có căn cứ. completedFraction là phần câu thực hành đã thực hiện (0–1), không dùng tỉ lệ thời lượng video. Chỉ ghi missingParts và áp dụng mức khống chế khi xác nhận abrupt_stop hoặc major_section_omitted; evidenceSource=visible_web hoặc verified_web_assignment và basis chỉ rõ căn cứ. book_only/unknown không đủ. Nếu đã thực hiện đủ từ câu đầu tới câu cuối trên web, completedFraction=1, missingParts=[]; không trừ vì câu minh họa/lý thuyết. Bỏ dở 1–2 câu nhỏ được xác nhận: tối đa 85%. Bỏ hẳn phần quan trọng hoặc thiếu 30–50% đề thật: tối đa 60%, Cần theo dõi. Hoàn thành dưới 50% đề thật: dưới 60%, CẦN NỘP LẠI. Không tăng điểm thấp do lỗi ngôn ngữ khác. Hình thức thuyết trình sai vẫn theo quy tắc riêng.`;
export const completionSchema={type:'object',properties:{assessed:{type:'boolean'},completedFraction:{type:'number',minimum:0,maximum:1},majorPartOmitted:{type:'boolean'},minorMissingSentences:{type:'integer',minimum:0},missingParts:{type:'array',items:{type:'string'}},basis:{type:'string'},omissionEvidence:{type:'string',enum:['none','abrupt_stop','major_section_omitted','uncertain']},evidenceSource:{type:'string',enum:['visible_web','verified_web_assignment','teacher_confirmation','book_only','audio_only','unknown']}},required:['assessed','completedFraction','majorPartOmitted','minorMissingSentences','missingParts','basis','omissionEvidence','evidenceSource'],additionalProperties:false};
export function completionDecision(draft,j={}){
 if(j.route?.kind==='ielts_speaking'||draft.assessable===false)return null;
 if(completedScreenScope(draft,j))return null;
 const c=j.teacherConfirmedCompletion||draft.completionCheck;if(!c?.assessed||!Number.isFinite(c.completedFraction)||c.completedFraction<0||c.completedFraction>1)return null;
 if(onlyTheoryOmissions(c,j.verifiedWebPracticeScope))return null;
 if(!hasSupportedOmission(c,j))return null;
 const missing=c.missingParts?.filter(s=>typeof s==='string'&&s.trim())||[];
 if(c.completedFraction<0.5)return {cap:55,resubmit:true,missing};
 if(c.majorPartOmitted||c.completedFraction<=0.7)return {cap:60,resubmit:false,missing};
 if(c.minorMissingSentences>=1&&c.minorMissingSentences<=2)return {cap:85,resubmit:false,missing};
 return null;
}
export function applyCompletionPolicy(draft,j={}){
 draft=applyScreenGrounding(draft,j);
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
