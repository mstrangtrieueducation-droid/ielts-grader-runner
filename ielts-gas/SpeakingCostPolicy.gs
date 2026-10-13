const ISG_COST_POLICY='speaking-cost-v1-20261010';
function isgCostGenerationConfig_(model){
 // IELTS feedback prioritizes evidence review over minimum generation cost.
 const config={maxOutputTokens:12000,thinkingConfig:model.startsWith('gemini-2.5-')?{thinkingBudget:4096,includeThoughts:false}:{thinkingLevel:'medium',includeThoughts:false}};
 if(model.startsWith('gemini-2.5-')){config.responseMimeType='application/json';config.responseJsonSchema=isgSchema_();}
 else config.responseFormat={text:{mimeType:'APPLICATION_JSON',schema:isgSchema_()}};
 return config;
}
function isgBindCostModel_(job,save){
 if(job.rawId){job.requestModel=job.requestModel||'gemini-3.8-flash';return;}
 if(job.costPolicy!==ISG_COST_POLICY){
  if(job.inputHash)job.priorInputCheckpoint={inputId:job.inputId,inputHash:job.inputHash,model:job.requestModel||'gemini-3.8-flash'};
  delete job.inputHash;delete job.inputId;
  job.requestModel=Number(isgProps_().getProperty('IELTS_SPEAKING_25_UNAVAILABLE_UNTIL')||0)>Date.now()?'gemini-3.8-flash':ISG.model;job.costPolicy=ISG_COST_POLICY;save();
 }
}
