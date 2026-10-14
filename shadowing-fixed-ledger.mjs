import {targetWords,spokenShadowTranscript} from './quant-score.mjs';
export const FIXED_LEDGER_VERSION='shadow-single-pass-explicit-coverage-v2';
export function requestLedger(transcript){
 const spoken=spokenShadowTranscript(transcript),units=targetWords(spoken);
 const phrases=spoken.split(/\n+/).map(s=>s.trim()).filter(s=>targetWords(s).length);
 if(!units.length||!phrases.length)throw Error('SHADOW_FIXED_LEDGER_SOURCE_MISSING');
 return {version:FIXED_LEDGER_VERSION,units,prosody:phrases,fluency:phrases};
}
export function sparseSchema(schema){
 const copy=structuredClone(schema);
 for(const name of ['units','prosody','fluency']){const item=copy.properties.scoreLedger.properties[name];delete item.properties.targets;item.required=item.required.filter(k=>k!=='targets');item.properties.outcomes={type:'string',description:'One explicit verdict per target in order: C=heard correct, I=heard incorrect, M=missing, U=unheard/uncompared'};item.required.push('outcomes');}
 copy.properties.scoreLedger.properties.phraseChecks={type:'array',items:{type:'object',properties:{phraseIndex:{type:'integer'},time:{type:'string'},heardStudentText:{type:'string'}},required:['phraseIndex','time','heardStudentText'],additionalProperties:false}};copy.properties.scoreLedger.required.push('phraseChecks');
 return copy;
}
export function indexedLedger(template){return {version:template.version,unitsCount:template.units.length,phraseCount:template.prosody.length,units:template.units.map((word,i)=>i+'='+word).join(' '),prosodyAndFluency:template.prosody.map((phrase,i)=>i+'='+phrase).join('\n')};}
export function restoreFixedTargets(grade,template){
 if(!template)return grade;
 if(![FIXED_LEDGER_VERSION,'shadow-single-pass-fixed-ledger-v1'].includes(template.version))throw Error('SHADOW_FIXED_LEDGER_VERSION_INVALID');
 for(const name of ['units','prosody','fluency']){
  const block=grade.scoreLedger?.[name];if(!block||Array.isArray(block)||!Array.isArray(block.errors)||!Array.isArray(block.unclearIndexes)||!Array.isArray(template[name])||!template[name].length)throw Error('SHADOW_FIXED_LEDGER_OUTPUT_INVALID');
  // The reference lists belong to the request. Acoustic verdicts, evidence,
  // completeness and uncertainty are supplied only by Gemini.
  block.targets=[...template[name]];
 }
 return grade;
}
export const fixedLedgerInstruction='Danh sách mục tiêu đã được code cố định và đánh số trong requestLedger, chỉ số 0-based. units là index=từng từ, gồm từng lần xuất hiện; prosody và fluency dùng chung prosodyAndFluency, index=từng dòng/cụm đọc. Dùng đúng index đã cho, KHÔNG tự đếm index. Nghe toàn bộ audio học sinh trong lượt này, đối chiếu TẤT CẢ mục tiêu. KHÔNG chép lại targets trong JSON trả về: chỉ ghi errors=[{unitIndex,evidenceIndexes}] và unclearIndexes cho từng nhóm. Với mỗi lỗi phải có bằng chứng thực nghe, liên kết evidenceIndexes đúng loại. Mọi evidence phải được một errors entry sử dụng; không ghi lỗi trong lời nhận xét mà thiếu evidence. Một từ có nhiều lỗi gom chung một errors entry. complete=true chỉ khi đã thực sự đối chiếu hết; không có lỗi rõ thì errors=[]; không chắc thì ghi unclearIndexes, không bịa lỗi. Code gắn lại đúng targets đã gửi và tự tính điểm theo 50–25–25; không tự chọn điểm hoặc tự đếm lại số từ.';

export const explicitCoverageInstruction='QUY TẮC ƯU TIÊN: KHÔNG coi mục không ghi lỗi là đúng. Mỗi bảng units/prosody/fluency PHẢI có outcomes chứa đúng một ký tự cho TỪNG mục tiêu, theo thứ tự: C=đã nghe rõ và đúng; I=đã nghe rõ và sai; M=thiếu; U=chưa nghe/không đối chiếu được. Chỉ đánh C khi đã đối chiếu mục đó với chính giọng học sinh. Mỗi I/M cần errors liên kết bằng chứng; U cần unclearIndexes. Cung cấp phraseChecks đủ từng dòng mẫu gồm phraseIndex, time của giọng HỌC SINH, heardStudentText thực nghe; khi thiếu câu, ghi văn bản [MISSING] và mốc khoảng thiếu, không chép mẫu thay cho lời thực nghe. Không đánh complete=true nếu bỏ sót phần nào. Mọi nhận xét lỗi/ngập ngừng/ngắt sai đều cần evidence theo timestamp và errors tương ứng trong cùng một lượt; không chỉ ghi vài lỗi tiêu biểu. Nếu không đủ bằng chứng, vẫn trả nhận xét trung thực và U, không giả định đúng. Hoàn thành kiểm tra cả ba tiêu chí ngay trong một lần gọi, không yêu cầu gọi lại.';
