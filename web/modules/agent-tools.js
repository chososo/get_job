// Only public records are exposed. Private experiences and documents are never returned.
export function registerPublicTools(context,getJobs,openJob) {
  if(!context?.registerTool)return null;
  const lifecycle=new AbortController();
  const register=tool=>{try{Promise.resolve(context.registerTool(tool,{signal:lifecycle.signal})).catch(()=>{});}catch{}};
  register({name:'search_public_jobs',title:'공개 공고 검색',description:'Search public job records only. Never reads the private vault.',inputSchema:{type:'object',properties:{query:{type:'string'}},required:['query'],additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},execute(input){if(!input||typeof input.query!=='string'||Object.keys(input).some(k=>k!=='query'))throw Error('query must be a string');return getJobs().filter(j=>`${j.company} ${j.title}`.toLowerCase().includes(input.query.toLowerCase())).slice(0,50).map(j=>({id:j.id,company:j.company,title:j.title,country:j.country,sourceUrl:j.sourceUrl,status:j.status}));}});
  register({name:'open_public_job',title:'공개 공고 상세 열기',description:'Open a public job detail view. Does not save private data or submit an application.',inputSchema:{type:'object',properties:{id:{type:'string'}},required:['id'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:true},execute(input){if(!input||typeof input.id!=='string'||Object.keys(input).some(k=>k!=='id')||!getJobs().some(j=>j.id===input.id))throw Error('Unknown public job');openJob(input.id);return {opened:input.id};}});
  return lifecycle;
}
