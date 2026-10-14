// Gemini includes internal reasoning in maxOutputTokens. Reserve the existing
// 12k cap for the full four-criterion response rather than increasing that cap.
export function withSpeakingOutputReserve(config,model){
 if(model!=='gemini-3.8-flash')return config;
 return {...config,thinkingConfig:{...config.thinkingConfig,thinkingLevel:'low',includeThoughts:false}};
}
