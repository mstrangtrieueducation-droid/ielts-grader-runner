import {percentBand,publicText,receiptDate} from './master-policy.mjs';
import {applyCompletionPolicy} from './content-completion-policy.mjs';
import {pedagogicSection} from './pedagogical-language.mjs';
export const SAVED_FEEDBACK_VERSION='kids-saved-feedback-v1';
const array=x=>Array.isArray(x)?x:Object.values(x||{});
const tone=text=>/chưa|nhầm|thiếu|sai|nuốt|nghe:|đọc thành|→|Con (?:cần|chú ý|nhớ|luyện)|cần sửa|lưu ý/i.test(text)&&!(/(?:rất tốt|phát âm (?:đúng|rõ|tốt)|đọc (?:đúng|rõ|tốt))/i.test(text)&&!/chưa|nhầm|thiếu|sai|nuốt|nghe:|đọc thành|→/i.test(text))?'correction':'praise';
const parts=text=>String(text).split(/(?<=\n)|(?<=[.!?])(?=\s+(?:Con|Cô|Tuy nhiên)\b)/u).filter(Boolean).map(text=>({text,tone:tone(text)}));
const valid=s=>s.spans?.length&&s.spans.every(p=>['praise','correction','neutral'].includes(p.tone))&&s.spans.map(p=>p.text).join('')===s.text;
export function savedSections(g,snapshot={}){
 const supplied=array(g.roseSections||g.sections).filter(s=>typeof s.text==='string'&&publicText(s.text).trim());
 // Keep the complete model-authored reply when one exists. Missing ancillary
 // evidence fields must not remove or downgrade any of its corrections.
 if(supplied.length)return supplied.map(s=>{const text=publicText(s.text);return pedagogicSection({...s,text,spans:text===s.text&&valid(s)?s.spans:parts(text)});});
 const findings=array(g.rubricFindings),labels=snapshot.form?.length?snapshot.form:findings.map(f=>f.label).filter(Boolean);
 const sections=(labels.length?labels:['Nội dung','Phát âm & ngữ pháp','Cách luyện']).map(label=>({label,text:'',spans:[]}));
 const add=(s,text,t='neutral')=>{text=publicText(text);if(!text?.trim()||s.spans.some(p=>p.text.trim()===text.trim()))return;s.spans.push({text:(s.spans.length?'\n':'')+text.trim(),tone:t});s.text=s.spans.map(p=>p.text).join('');};
 const matching=pattern=>sections.find(s=>pattern.test(s.label));
 for(const f of findings){const s=sections.find(s=>s.label===f.label)||sections[0];for(const p of f.strengths||[])add(s,p.basis,'praise');}
 for(const check of g.contentChecks||[])add(matching(/nội dung|thuộc|dịch|ngữ pháp/i)||sections[0],check.feedback||check.heard,tone(check.feedback||check.heard||''));
 for(const e of g.evidence||[]){
  const s=e.type==='grammar'?(matching(/ngữ pháp|ngôn ngữ/i)||sections[0]):e.type==='pronunciation'?(matching(/phát âm|ngôn ngữ/i)||sections[0]):e.type==='intonation'||e.type==='fluency'?(matching(/trôi chảy|tốc độ|ngữ điệu/i)||sections.at(-1)):(matching(/nội dung/i)||sections[0]);
  const time=e.time?' ở đoạn '+e.time:'',ipa=e.ipa?(String(e.ipa).startsWith('/')?e.ipa:'/'+e.ipa+'/'):'';
  let text;
  if(e.type==='grammar')text='Con sửa câu'+time+': '+[e.observed,e.correction].filter(Boolean).join(' → ');
  else if(e.type==='pronunciation')text='Con chú ý từ '+[e.word,ipa].filter(Boolean).join(' ')+time+': '+(e.observed?(/^Con\s/i.test(e.observed)?e.observed:'con đọc thành '+e.observed)+'. ':'')+(e.correction?(/^Con\s/i.test(e.correction)?e.correction:'Con đọc lại: '+e.correction):'');
  else text=[e.observed,e.correction,e.time].filter(Boolean).join(' — ');
  add(s,text,'correction');
 }
 for(const o of g.presentation?.observations||[])add(matching(/phong thái|biểu cảm|trình bày/i)||sections.at(-1),o.assessment||o.correction||o.observation,o.tone||'neutral');
 for(const r of array(g.recordingChecks))if(r.feedback?.trim())add(sections.at(-1),r.feedback,'correction');
 if(!sections.some(s=>s.text)&&g.reason)add(sections[0],g.reason,tone(g.reason));
 return sections.filter(s=>publicText(s.text).trim()).map(pedagogicSection);
}
export function savedFeedback(g,j,before='',snapshot={}){
 g=applyCompletionPolicy(g,j);
 const sections=savedSections(g,snapshot);if(!sections.length)throw Error('SAVED_FEEDBACK_EMPTY');
 const marker='— NHẬN XÉT GV —',prefix=before.includes(marker)?before.slice(0,before.indexOf(marker)):'';
 let date=receiptDate(j.receipt?.time);
 const stamp=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Bangkok',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(date).replace(',','');
 const current=before.match(/Chất lượng:\s*(?:đạt(?: khoảng)?\s*)?(\d+(?:[.,]\d+)?)\s*%/i),raw=String(g.rubricBand||g.band||'').match(/^(\d+(?:[.,]\d+)?)\s*%$/),value=Number((raw||current)?.[1]?.replace(',','.')??NaN),score=percentBand(value);
 const heading=j.route?.kind==='ielts_speaking'?'IELTS Speaking: Band ước tính '+g.band+'.\n':(score===null?'':'Chất lượng: đạt khoảng '+score+'%.\n')+(score!==null&&(score<75||g.forceAttention)?'⚠️ Cần theo dõi\n':'');
 const text=(prefix.includes('ĐÃ NỘP')?prefix:'✅ ĐÃ NỘP '+stamp+'\n')+marker+'\n'+heading+sections.map(s=>'• '+s.label+': '+s.text).join('\n');
 return {text,sections,score,version:SAVED_FEEDBACK_VERSION};
}
export function savedFeedbackRich(c,cell,text,sections){
 const b=c.coloredFeedback_(cell,text,null).copy();
 for(const s of sections){const title='• '+s.label+': ',start=text.indexOf(title);if(start<0)continue;const end=start+title.length;b.setTextStyle(start,end,c.SpreadsheetApp.newTextStyle().setForegroundColor('#0D47A1').setBold(true).build());let at=end;
  for(const p of valid(s)?s.spans:parts(s.text)){b.setTextStyle(at,at+p.text.length,c.SpreadsheetApp.newTextStyle().setForegroundColor(p.tone==='correction'?'#C2185B':p.tone==='praise'?'#1B5E20':'#0D47A1').build());at+=p.text.length;}
 }
 const warning=text.indexOf('⚠️ Cần theo dõi');if(warning>=0)b.setTextStyle(warning,warning+'⚠️ Cần theo dõi'.length,c.SpreadsheetApp.newTextStyle().setForegroundColor('#C2185B').build());return b.build();
}
