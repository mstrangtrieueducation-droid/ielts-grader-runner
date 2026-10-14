import {receiptDate,publicText} from './master-policy.mjs';
export const READING_RESUBMISSION_STATUS='CẦN_NỘP_LẠI_DO_ĐỌC_BÀI';
export const PRESENTATION_RULE=`QUY TẮC SƯ PHẠM BẮT BUỘC: D.E, Science và Critical chỉ áp dụng khi bài yêu cầu TỰ THUYẾT TRÌNH theo hình/mindmap. Nếu có bằng chứng rõ học sinh đọc bài viết sẵn/đọc thoại từng chữ thụ động thay cho thuyết trình: assessable=false, band và rubricBand rỗng, roseSections=[], không chấm các tiêu chí chi tiết; presentationReadingCheck phải nêu requiresPresentation=true, readsPreparedScript=true, confirmed=true, basis là quan sát cụ thể và sourceFileIndex, time nếu biết. Trả lời yêu cầu luyện nói từ hình/mindmap rồi quay lại nhìn camera. Chỉ nhìn hình, đọc từ khóa mindmap, một lần nhìn xuống, giọng chậm hay chỉ có audio KHÔNG chứng minh đọc bài viết sẵn. Không áp dụng quy tắc này cho bài đọc/dịch, lồng tiếng, shadowing hoặc bài được phép đọc văn bản.`;
export function confirmedScriptReading(g,j,snapshot={}){
 if(!['de','scienceK','science','critical','project'].includes(j.route?.kind||snapshot.kind))return false;
 const mode=snapshot.barem?.requirements?.contract?.mode;
 if(['read_text','dubbing','shadowing','translate'].includes(mode))return false;
 const x=g.presentationReadingCheck;
 if(Array.isArray(j.masterVisualFileIndexes)&&!j.masterVisualFileIndexes.includes(x?.sourceFileIndex))return false;
 // No visual input means the model cannot certify reading a prepared script.
 const visual=(j.media||[]).filter(m=>!m.isReference).some(m=>m.runnerPdfFrame||m.runnerContextFrames?.length||m.mime?.startsWith('video/')&&j.runnerAudioOnly!==true&&!j.mediaDecision?.mode?.startsWith('audio'));
 if(!visual)return false;
 if(x?.requiresPresentation===true&&x.readsPreparedScript===true&&x.confirmed===true&&x.basis?.trim())return true;
 const recordings=Array.isArray(g.recordingChecks)?g.recordingChecks:Object.values(g.recordingChecks||{});
 return recordings.some(r=>r.textUseStatus==='visible_reading'&&r.compliance==='not_met'&&/bài viết sẵn|đọc (?:giấy|thoại|văn bản)|chỉ.*đọc chữ/i.test([r.textUseBasis,r.feedback].join(' ')));
}
export function readingResubmission(g,j){
 const stamp=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Bangkok',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(receiptDate(j.receipt?.time)).replace(',','');
 const observation=publicText(g.presentationReadingCheck?.basis||'').trim();
 const reason='Bài này yêu cầu con tự thuyết trình theo hình/mindmap, nhưng con đang đọc bài viết sẵn/nhìn chữ đọc thoại thay cho phần tự trình bày.'+(observation?' '+observation:'');
 const practice='Con nhìn hình/mindmap, tập nói từng ý thành câu bằng lời của mình. Khi đã nói liền mạch, con quay lại video nhìn camera rồi nộp lại nhé. Cô đợi bài của con.';
 return {text:'❌ CẦN NỘP LẠI '+stamp+'\n— NHẬN XÉT GV —\nChất lượng: Chưa đạt (Yêu cầu quay lại).\n• Lý do yêu cầu nộp lại: '+reason+'\n• Hướng dẫn luyện tập: '+practice,sections:[{label:'Lý do yêu cầu nộp lại',text:reason,spans:[{text:reason,tone:'correction'}]},{label:'Hướng dẫn luyện tập',text:practice,spans:[{text:practice,tone:'praise'}]}],score:null,status:READING_RESUBMISSION_STATUS};
}
