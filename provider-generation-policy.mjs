// A recitation rejection is saved before its one explicitly authorized new call.
// Network failures and unknown outcomes are never retried here.
export const PROVIDER_POLICY='teacher-feedback-recovery-20261030';
export const ORIGINAL_FEEDBACK='Chỉ viết lời nhận xét sư phạm bằng tiếng Việt do cô tự diễn đạt. Không chép hoặc hoàn thành lời sách, bài hát hay phim. Không xuất transcript. Chỉ trích dẫn từ đơn lẻ cần sửa phát âm; mô tả lỗi và cách luyện bằng lời riêng.';
export const SAFETY_SETTINGS=['HARASSMENT','HATE_SPEECH','SEXUALLY_EXPLICIT','DANGEROUS_CONTENT'].map(x=>({category:'HARM_CATEGORY_'+x,threshold:'BLOCK_NONE'}));
export function feedbackPayload(value,{retry=false}={}){
 const p=structuredClone(typeof value==='string'?JSON.parse(value):value);
 p.generationConfig={...p.generationConfig,temperature:retry?0.4:0.25};
 p.safetySettings=SAFETY_SETTINGS.map(x=>({...x}));
 p.systemInstruction={...p.systemInstruction,parts:[...(p.systemInstruction?.parts||[]),{text:ORIGINAL_FEEDBACK}]};
 return p;
}
export function requestFeedback({job,options,send,persist,saveArtifact,onRetry=()=>{},validate=()=>{}}){
 const p=feedbackPayload(options.body);validate(p);
 let response=send({...options,body:JSON.stringify(p)});
 if(response.getResponseCode()!==200)return response;
 let raw;try{raw=JSON.parse(response.getContentText());}catch{return response;}
 if(raw?.candidates?.[0]?.finishReason!=='RECITATION'||job.recitationRecovery?.retryReservedAt)return response;
 const rawId=saveArtifact(raw);if(!rawId)throw Error('RECITATION_RESPONSE_NOT_DURABLE');
 job.recitationRecovery={policy:PROVIDER_POLICY,rawId,usage:raw.usageMetadata||null,retryReservedAt:new Date().toISOString(),maxAdditionalCalls:1};
 job.generateRequests=(Number(job.generateRequests)||1)+1;
 persist();onRetry();
 const retry=feedbackPayload(options.body,{retry:true});validate(retry);
 response=send({...options,body:JSON.stringify(retry)});
 return response;
}
