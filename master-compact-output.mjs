// Teacher master policy, 23 October 2026. Old paid responses remain byte-exact.
export const COMPACT_VERSION='teacher-master-compact-20261023';
export const OUTPUT_TOKENS=2048;
export const COMPACT_INSTRUCTION=`QUY CHUẨN MỚI ƯU TIÊN: Nghe đủ mọi tệp trong MỘT request. Chỉ trả JSON theo schema gọn; không xuất transcript, bảng đếm từ, coverage dài hoặc tự thuật suy nghĩ. Tối đa 300 từ tiếng Việt toàn phản hồi; khen có căn cứ và sửa cụ thể, gộp lỗi cùng loại. Lời sửa có ví dụ đúng và giải thích ngắn, IPA chỉ cho từ đơn, không gán IPA cho câu ngữ pháp. Chất lượng % là bội số 5; không có dữ liệu thì để score=null, không bịa điểm. Chỉ lấy số câu thực hành trên web/ảnh bài được giao, không cộng ví dụ sách. Với Science G1/G2/G3 nghe đủ cả mindmap và câu hỏi, ghi số câu trả lời đúng/thiếu trong mục Nội dung. Với D.E, Science K, Critical: kiểm tra ảnh giây 10/40; chỉ khi ảnh rõ cho thấy chỉ quay màn hình, không thấy người, capture=screen_only/filming_screen và nêu bằng chứng; score=null, không chấm chi tiết. Hình thiếu/mờ không đủ để kết luận. Không viết lời thanh minh về transcript/audio mẫu. Trả xong JSON đầy đủ trong 2048 token.`;
const obj=properties=>({type:'object',properties,required:Object.keys(properties),additionalProperties:false});
const str={type:'string'};
export function compactSchema(labels,{speaking=false,foundation=false,visual=false}={}){
 return obj({v:{type:'string',enum:[COMPACT_VERSION]},ok:{type:'boolean'},score:{type:['number','null'],minimum:0,maximum:speaking&&!foundation?9:100},why:str,
  ...(visual?{capture:{type:'string',enum:['student','screen_only','filming_screen','unknown']},visualBasis:str,fileIndex:{type:'integer',minimum:0}}:{}),
  sections:{type:'array',minItems:0,maxItems:labels.length,items:obj({label:{type:'string',enum:labels},praise:str,correction:str,...(speaking&&!foundation?{band:{type:['number','null'],minimum:0,maximum:9}}:{})})}});
}
export function compactResponse(raw){
 const text=(raw?.candidates?.[0]?.content?.parts||[]).filter(p=>!p.thought&&typeof p.text==='string').map(p=>p.text).join('').replace(/^\s*```(?:json)?\s*|\s*```\s*$/g,'');
 let g;try{g=JSON.parse(text);}catch{return null;}if(g?.v!==COMPACT_VERSION)return null;
 if(typeof g.ok!=='boolean'||!Array.isArray(g.sections)||g.ok&&!g.sections.length||g.sections.some(s=>!s.label||typeof s.praise!=='string'||typeof s.correction!=='string'||!(s.praise+s.correction).trim())||g.ok&&(!Number.isFinite(g.score)||g.score<0)||!g.ok&&!String(g.why||g.visualBasis||'').trim())throw Error('COMPACT_RESULT_INCOMPLETE');
 return g;
}
export function expandKidsCompact(raw){
 const g=compactResponse(raw);if(!g)return null;const score=g.ok&&g.score<=100?Math.round(g.score/5)*5:null;
 return {assessable:g.ok,band:score===null?'':score+'%',rubricBand:score===null?'':score+'%',reason:g.why||'',speechStatus:'UNCERTAIN',
  presentationVisualCheck:{confirmed:!!g.visualBasis&&['screen_only','filming_screen'].includes(g.capture),studentVisible:g.capture==='student',capture:g.capture||'unknown',basis:g.visualBasis||'',sourceFileIndex:g.fileIndex||0},
  roseSections:g.sections.map(s=>{const spans=[s.praise?{text:s.praise,tone:'praise'}:null,s.correction?{text:(s.praise?'\n':'')+s.correction,tone:'correction'}:null].filter(Boolean);return {label:s.label,text:spans.map(p=>p.text).join(''),spans};}),compactPolicy:COMPACT_VERSION};
}
export function expandShadowCompact(raw){
 const g=compactResponse(raw);if(!g)return null;if(g.score!==null&&g.score>100)throw Error('COMPACT_SCORE_INVALID');
 return {assessable:g.ok,overallPercent:g.ok?Math.round(g.score/5)*5:null,reason:g.why||'',sections:g.sections.map(s=>({...s,score:null})),evidence:[],uncertainty:[],compactPolicy:COMPACT_VERSION};
}
export function compactGeneration(config,model){
 // Flash 3.8 rejects the 2.5-only thinkingBudget=0/minimal setting.
 // Keep the lowest validated setting instead of issuing a known-invalid request.
 return {...config,maxOutputTokens:OUTPUT_TOKENS,thinkingConfig:model.startsWith('gemini-2.5-')?{thinkingBudget:0,includeThoughts:false}:{thinkingLevel:model==='gemini-3.8-flash'?'low':'minimal',includeThoughts:false}};
}
export function installCompactKids(c){
 const system=c.kidsSystemInstruction_;c.kidsSystemInstruction_=()=>system()+'\n'+COMPACT_INSTRUCTION;
 c.kidsEvidenceSchema_=form=>compactSchema(form,{visual:true});
 const config=c.kidsGenerationConfig_;c.kidsGenerationConfig_=(model,form)=>compactGeneration(config(model,form),model);
}
