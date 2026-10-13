import fs from 'node:fs';
import vm from 'node:vm';
const policy=vm.createContext({});
vm.runInContext(fs.readFileSync(new URL('./gas/AssessmentPolicy.gs',import.meta.url),'utf8'),policy);
export const assessmentInstruction=type=>policy.assessmentGroundingInstruction_(type);
