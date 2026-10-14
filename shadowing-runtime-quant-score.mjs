import fs from 'node:fs';

import vm from 'node:vm';

const c=vm.createContext({});

vm.runInContext(fs.readFileSync(new URL('./gas/QuantScore.gs',import.meta.url),'utf8'),c);

export const quantitativeSchema=()=>JSON.parse(JSON.stringify(c.quantScoreSchema_()));

export const quantitativeInstruction=c.quantScoreInstruction_()+'\n'+c.weightedWordInstruction_();

export const calculateQuantitative=(ledger,evidence,mode)=>JSON.parse(JSON.stringify(c.quantScore_(ledger,evidence,mode)));

export const targetWords=text=>String(text||'').toLowerCase().replaceAll('’',"'").match(/[a-z]+(?:['-][a-z]+)*|\d+(?:\.\d+)?/g)||[];

// Barem dialogue labels identify speakers; they are not spoken words.
export const spokenShadowTranscript=text=>String(text||'').replace(/^[\t ]*(?:A|J|AS|AM|D|B|Caty|Anna|Andrew):[\t ]*/gm,'').replace(/\[sneeze\]/gi,'');

export function applyShadowQuantitative(g,transcript){

 if(g.scoreQuality?.status==='unscored')return g;
 if(!g.scoreLedger)return g; // Do not rescore old saved successful responses.

 if(g.uncertainty?.length)throw Error('GRADE_SCORE_UNCLEAR');
 // Strip punctuation attached to a single word without changing word count,
 // occurrence order, evidence indexes or the full-reference denominator.
 const canonicalWord=value=>{const words=targetWords(value);return words.length===1?words[0]:value;};
 if(Array.isArray(g.scoreLedger.units)){for(const unit of g.scoreLedger.units)unit.target=canonicalWord(unit.target);}
 else if(Array.isArray(g.scoreLedger.units?.targets))g.scoreLedger.units.targets=g.scoreLedger.units.targets.map(canonicalWord);
 for(const e of g.evidence)if(['pronunciation','content'].includes(e.type)&&e.word)e.word=canonicalWord(e.word);


 for(const e of g.evidence)if(!['pronunciation','content','intonation','fluency'].includes(e.type)||!/^\d{1,2}:[0-5]\d(?:\.\d+)?(?:[-–]\d{1,2}:[0-5]\d(?:\.\d+)?)?$/.test(e.time)||!e.observed?.trim()||!e.correction?.trim())throw Error('SHADOW_QUANT_EVIDENCE_INVALID');

 if(transcript){const targets=targetWords(spokenShadowTranscript(transcript)),units=(Array.isArray(g.scoreLedger.units)?g.scoreLedger.units.map(u=>u.target):g.scoreLedger.units.targets).map(u=>targetWords(u).join(' '));

  if(JSON.stringify(targets)!==JSON.stringify(units))throw Error('GRADE_SCORE_REFERENCE_DENOMINATOR_MISMATCH');

 }

 const evidence=g.evidence.map(e=>({...e,type:e.type||'pronunciation'}));

 const score=calculateQuantitative(g.scoreLedger,evidence,'weighted');g.scoreCalculation=score;

 const category=['units','prosody','fluency'];

 for(const [i,s]of g.sections.entries()){

  s.score=Math.round(score.details[category[i]].percent);

  const errors=i===0?evidence.filter(e=>!['intonation','fluency'].includes(e.type)):evidence.filter(e=>e.type===(i===1?'intonation':'fluency'));

  const original=s.correction;
  const linked=errors.map(e=>(e.type==='pronunciation'?e.word+' '+e.ipa+' — ':'')+e.observed+' → '+e.correction).join('\n');
  s.correction=original||linked;

 }

 return g;

}

