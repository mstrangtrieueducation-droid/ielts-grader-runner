export const NETWORK_TIMEOUT_MS = 5000;
export function createReferenceSelector(){
 const cache=new Map();
 return (documented,lesson,obtainAudio)=>{
  if(!documented||documented.videoId!==lesson.videoId)throw Error('SHADOW_TRANSCRIPT_REFERENCE_CHANGED');
  const key=JSON.stringify([lesson.id,lesson.videoId,documented.publisherMediaUrl,documented.transcript,documented.publisherDurationSeconds]);
  if(cache.has(key))return cache.get(key);
  try{const audio=obtainAudio();const result={...audio,meta:{...audio.meta,mode:'audio'}};cache.set(key,result);return result;}
  catch(error){
   const bbc=String(documented.publisherMediaUrl||'').startsWith('https://downloads.bbc.co.uk/');
   if(!bbc||!documented.transcript?.trim())throw error;
   const result={part:null,meta:{videoId:lesson.videoId,mode:'transcript',duration:null,source:'configured_barem',fallbackReason:error.message||'REFERENCE_DOWNLOAD_FAILED'}};
   cache.set(key,result);return result;
  }
 };
}
export function referenceInstructions(mode){
 return mode==='transcript'
  ? 'Chỉ có transcript mẫu và một file âm thanh HỌC SINH. Nghe đầy đủ file học sinh. Đối chiếu từ và phát âm với transcript chuẩn; đánh giá ngữ điệu/ngắt nghỉ tự nhiên theo nội dung câu và độ trôi chảy của học sinh. Không có audio mẫu: không khẳng định đã nghe giọng mẫu, không chấm mức khớp giọng, nhịp hoặc tốc độ của mẫu. Mốc thời gian evidence thuộc file học sinh duy nhất.'
  : 'Audio mẫu được gắn nhãn GIỌNG MẪU; audio học sinh được gắn nhãn HỌC SINH. Nghe đầy đủ và chỉ chấm giọng học sinh. Mốc thời gian evidence thuộc file học sinh.';
}
