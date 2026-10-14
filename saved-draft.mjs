// Recover the original paid response locally. Never request another generation.
export function decodeSavedDraft(raw){
 if(typeof raw?.assessable==='boolean'&&(raw.sections||raw.roseSections))return raw;
 const text=(raw?.candidates?.[0]?.content?.parts||[]).filter(p=>!p.thought&&p.text).map(p=>p.text).join('');
 for(const candidate of [text,text.replace(/^\s*```(?:json)?\s*|\s*```\s*$/g,'').replace(/,\s*([}\]])/g,'$1')])try{return JSON.parse(candidate);}catch{}
 const sections=[],re=/"label"\s*:\s*("(?:\\.|[^"\\])*")[\s\S]*?"text"\s*:\s*("(?:\\.|[^"\\])*")/g;
 for(const m of text.matchAll(re))try{sections.push({label:JSON.parse(m[1]),text:JSON.parse(m[2])});}catch{}
 const band=text.match(/"(?:rubricBand|band)"\s*:\s*"(\d+(?:\.\d+)?%)"/)?.[1]||'';
 return sections.length?{assessable:true,band,roseSections:sections}:{assessable:false,band:'',reason:'Con gửi lại phần bài được giao để cô nhận xét nhé. Cô đợi bài của con.'};
}
