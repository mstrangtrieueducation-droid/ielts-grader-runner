import {SCREEN_FIRST_INSTRUCTION} from './screen-grounding.mjs';
export const PEDAGOGIC_BRIDGE='Tuy nhiên, để bài nói/bài đọc được hoàn thiện và chuẩn xác hơn, con chú ý một số điểm sau đây nhé:';
export const PEDAGOGY_INSTRUCTION=SCREEN_FIRST_INSTRUCTION+`\nQUY CHUẨN SƯ PHẠM DÙNG CHUNG: Viết như cô giáo hướng dẫn con, ấm áp, cụ thể, thẳng thắn với phần chưa đạt. Trong MỖI tiêu chí có cả ưu điểm và lỗi, sau phần khen và trước phần sửa BẮT BUỘC có câu dẫn: "${PEDAGOGIC_BRIDGE}". Gom lỗi cùng bản chất trong chính tiêu chí tương ứng: ngữ pháp/cấu trúc, phát âm/âm đuôi, dịch nghĩa; không liệt kê rời theo thứ tự mốc giây. CẤM dòng cộc lốc dạng "mm:ss: A -> B". Ngữ pháp: giải thích bằng tiếng Việt con thiếu to-be, dùng thừa từ hay thiếu số nhiều..., trích cách con nói và câu đúng; TUYỆT ĐỐI không gán IPA cho cả câu ngữ pháp. Phát âm: nói rõ con đọc từ nào thành từ nào hoặc thiếu âm nào, giữ IPA của từ đích và mốc giây thật nếu có, viết thành câu hướng dẫn. Dịch nghĩa: trích nguyên câu tiếng Anh gốc cùng bản dịch đúng, chỉ rõ chỗ con dịch nhầm; không nói vu vơ "câu này dịch sai". Không bịa nguyên nhân hoặc câu gốc chưa có căn cứ. Giữ đầy đủ lỗi thật, không xóa lời chữa vì thiếu IPA/mốc; không gọi AI thêm để sửa văn phong. Các trường evidence/scoreLedger là dữ liệu nội bộ; phần nhận xét gửi phụ huynh phải là lời cô giáo hoàn chỉnh.`;
export function pedagogicSpans(spans){
 const out=[];let praise=false,bridged=false;for(const p of spans){
  if(p.text?.includes('• ')){praise=false;bridged=false;}
  if(p.text?.includes(PEDAGOGIC_BRIDGE))bridged=true;
  if(p.tone==='correction'&&praise&&!bridged){out.push({text:'\n'+PEDAGOGIC_BRIDGE+'\n',tone:'neutral'});bridged=true;}
  out.push(p);if(p.tone==='praise')praise=true;
 }return out;
}
export function pedagogicSection(section){
 const spans=pedagogicSpans(section.spans||[]);return spans.length?{...section,spans,text:spans.map(p=>p.text).join('')}:section;
}
