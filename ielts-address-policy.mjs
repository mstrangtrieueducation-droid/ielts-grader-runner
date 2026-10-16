export const IELTS_ADDRESS_VERSION='teacher-ielts-em-20261016';
export const isIeltsClass=name=>/^IELTS(?=\s|\d|[-_]|$)/iu.test(String(name||'').trim());
export const ieltsAddressInstruction=name=>isIeltsClass(name)?'QUY ƯỚC XƯNG HÔ IELTS BẮT BUỘC: Viết trực tiếp cho người học bằng em/Em, tuyệt đối không gọi người nhận là con/Con trong lời khen, chuyển ý, sửa lỗi, nhận xét và lời khuyên. Quy tắc này áp dụng cả IELTS Speaking và Shadowing của lớp IELTS, ưu tiên hơn cách xưng hô của mẫu Kids. Giữ nguyên câu trích dẫn, từ tiếng Anh, IPA, mốc thời gian, điểm và nội dung lỗi.':'';
const ordinaryNoun=/^\s+(?:số|người|đường|vật|trai|gái|cái|chim|mèo|chó|cá|voi|sông|thuyền|tôm|kiến|bọ|ngựa|vịt|gà)(?=$|[^\p{L}])/iu;
export function ieltsAddressText(value){
 return String(value).replace(/Nghe:\s*[^\n]*?(?=\.\s+(?:Sửa|Cách sửa):|;\s*\[file|$|\n)|"[^"\n]*"|“[^”\n]*”|'[^'\n]*'|‘[^’\n]*’|\/[a-zA-Zɐ-ʯˈˌːˑθðŋæɑɒɔʊəɛɪʌɜɡɲɕɾr()\u0300-\u036f .-]+\/|(?<![\p{L}\p{N}_])(?:Con|CON|con)(?![\p{L}\p{N}_])|(^|[.!?\n]\s*)([ \t]*(?:-\s*)?)(?:Học sinh|HỌC SINH|học sinh)(?=\s|[:,])/gu,(match,boundary,prefix,offset,input)=>{
  if(boundary!==undefined)return boundary+prefix+'Em';
  if(!/^(?:Con|CON|con)$/u.test(match))return match;
  const rest=input.slice(offset+match.length);
  if(ordinaryNoun.test(rest)||/^\s*(?:→|->|\/)/u.test(rest))return match;
  return match==='con'?'em':'Em';
 });
}
export function ieltsAddressSegments(segments,className){return isIeltsClass(className)?segments.map(s=>({...s,text:ieltsAddressText(s.text)})):segments;}
export function addressedSpeakingGrade(grade){
 const g=structuredClone(grade),text=v=>typeof v==='string'?ieltsAddressText(v):v,list=v=>Array.isArray(v)?v.map(text):v;
 for(const key of ['limitation','reason'])g[key]=text(g[key]);g.advice=list(g.advice);
 if(g.pronunciation){g.pronunciation.praise=list(g.pronunciation.praise);for(const key of ['endings','stress','intonation','fewerThanThreeReason'])g.pronunciation[key]=text(g.pronunciation[key]);for(const error of g.pronunciation.errors||[])for(const key of ['error','correction','errorType'])error[key]=text(error[key]);}
 for(const name of ['fluency','lexical','grammar'])if(g[name]){g[name].praise=list(g[name].praise);g[name].corrections=list(g[name].corrections);g[name].observation=text(g[name].observation);}
 return g;
}
export function installIeltsAddress(c){
 c.isgStudentAddress_=ieltsAddressText;const rich=c.isgRichText_;
 c.isgRichText_=(grade,...args)=>{const addressed=addressedSpeakingGrade(grade),normalize=c.isgStudentAddress_;c.isgStudentAddress_=value=>String(value);try{return rich(addressed,...args);}finally{c.isgStudentAddress_=normalize;}};
}
export const withIeltsNoticeAddress=(write,defaultText)=>(job,cell,save,session,text=defaultText,status)=>write(job,cell,save,session,isIeltsClass(job.source?.className)?ieltsAddressText(text):text,status);
