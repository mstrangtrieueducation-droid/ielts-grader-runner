// A listening result is not the teacher's video assessment. Classify without
// changing the original text, then merge the listening prefix verbatim.
const markerPattern=/[—–-]*[\t ]*NHẬN XÉT GV[\t ]*[—–-]*/iu;
const clean=value=>String(value??'').normalize('NFC').replace(/[\u200B-\u200D\uFEFF]/g,'');
export function emptyTeacherBody(value){const text=clean(value),marker=markerPattern.exec(text);return !!marker&&!text.slice(marker.index+marker[0].length).trim();}
export function hasTeacherReview(value){const text=clean(value),marker=markerPattern.exec(text);return !!marker&&!!text.slice(marker.index+marker[0].length).trim();}
function withoutListeningScores(text){
 return text.replace(/(?:^|\n)[\t ]*🎧[\t ]*ĐIỂM NGHE[^\r\n]*\r?\n(?:[\t ]*(?:Lần[\t ]+\d+[\t ]*:[\t ]*)?Điểm[\t ]+\d+[\t ]*\/[\t ]*\d+[\t ]*\([\t ]*\d+(?:[.,]\d+)?[\t ]*%[\t ]*\)[\t ]*(?:\r?\n|$))+/giu,'\n')
  .replace(/(?:^|\n)[\t ]*(?:🎧[\t ]*)?(?:Điểm nghe\s*:\s*|Điểm\s+)?\d+\s*\/\s*\d+(?:\s*\(\s*\d+(?:[.,]\d+)?\s*%\s*\))?[\t ]*(?=\r?\n|$)/giu,'')
  .replace(/(?:^|\n)[\t ]*(?:Điểm nghe\s*:\s*)?\d+(?:[.,]\d+)?\s*%[\t ]*(?=\r?\n|$)/giu,'');
}
export function receiptOnlyCell(value){
 let text=clean(value).trim();if(!text)return true;if(hasTeacherReview(text))return false;
 text=withoutListeningScores(text);
 if(/\d+(?:[.,]\d+)?\s*%/.test(text))return false; // reconcile unknown legacy teacher marks; never blind regeneration
 text=text.replace(markerPattern,'');
 text=text.replace(/\[?\d{1,2}\/\d{1,2}\/\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\]?/g,'');
 text=text.replace(/(?:Lần đầu|Lần mới|Thời gian|Lần nộp\s*\d+|Lần\s*\d+|Lượt\s*\d+)\s*:?/giu,'');
 text=text.replace(/\d+\s+(?:lượt|lần)/giu,'');
 text=text.replace(/(?:ĐÃ NỘP(?:\s+MUỘN|\s+\d+\s+LẦN)?|ĐÃ GHI NHẬN|NỘP MUỘN|CHƯA GHI NHẬN|CHƯA NỘP|NHẬN XÉT GV)/giu,'');
 return text.replace(/[✅☑✔❌⚠🔁\uFE0F\[\]():·—–\-\s]/gu,'')==='';
}
export function auxiliaryListeningOnly(value){const text=clean(value);return withoutListeningScores(text)!==text&&receiptOnlyCell(text);}
export function teacherFeedbackPrefix(before,fallback=''){
 const text=String(before??''),marker=markerPattern.exec(text);
 if(marker)return text.slice(0,marker.index)||fallback;
 if(auxiliaryListeningOnly(text))return text+(text.endsWith('\n')?'':'\n')+(/ĐÃ NỘP/iu.test(text)?'':fallback);
 return fallback;
}
