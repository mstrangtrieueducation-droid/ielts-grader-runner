import assert from 'node:assert/strict';
import {hasTeacherReview,emptyTeacherBody,receiptOnlyCell} from './teacher-feedback-state.mjs';
const base='✅ ĐÃ NỘP\n11/10/2026 08:54\n— NHẬN XÉT GV —\n✅ ĐÃ NỘP\n11/10/2026 08:54:31';
for(const text of [base,base+'\n— NHẬN XÉT GV —',base.replaceAll('ĐÃ NỘP','ĐÃ NỘP MUỘN')]){assert(!hasTeacherReview(text));assert(emptyTeacherBody(text));assert(receiptOnlyCell(text));}
for(const body of ['Chất lượng: đạt 0%.','60%','Em đã nộp nhưng cần luyện thêm.','Con đã nộp nhưng cần luyện thêm.','❌ CẦN NỘP LẠI: Video chưa mở quyền.']){assert(hasTeacherReview(base+'\n'+body));assert(!receiptOnlyCell(base+'\n'+body));}
console.log('PASS repeated native receipt scaffold is not teacher feedback; true prose, zero scores and resubmission comments remain intact; 0 API/0 Sheet writes.');
