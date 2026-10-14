// Destination grids are already owned by the RAM batch. Legacy preload calls
// must not fetch and replace that snapshot for every submission or summary row.
export function reuseDestinationPreloads(g,classes){
 const original=g.preloadSource,byId=new Map();
 for(const c of classes){const names=byId.get(c.spreadsheetId)||new Set();if(c.sheetName)names.add(c.sheetName);byId.set(c.spreadsheetId,names);}
 g.preloadSource=function(id,width=7,names=null){
  const allowed=byId.get(id),requested=names||[...(allowed||[])];
  if(allowed&&requested.length&&requested.every(n=>allowed.has(n))){
   const book=this.book(id);
   if(requested.every(n=>{const m=book.cache.get(n+'|master');return m&&m.width>=width;}))return;
  }
  return original.call(this,id,width,names);
 };
 return ()=>{g.preloadSource=original;};
}
