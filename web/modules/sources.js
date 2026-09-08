// These exports contain only company names and public recruitment links.
export function recruitmentUrl(value) {
  if (!value?.trim()) return '';
  let input=value.trim();
  if (!/^[a-z][a-z0-9+.-]*:/i.test(input)) input='https://'+input;
  let url; try {url=new URL(input);} catch {throw Error('올바른 채용 사이트 주소를 입력하세요.');}
  const host=url.hostname.toLowerCase();
  if (!['https:','http:'].includes(url.protocol)||url.username||url.password||!host.includes('.')||host.endsWith('.local')||host.endsWith('.localhost')||/^[\d.]+$/.test(host)||host.includes(':')) throw Error('공개 채용 사이트 주소만 등록할 수 있습니다.');
  if ([...url.searchParams.keys()].some(k=>/token|password|secret|session|authorization|api.?key/i.test(k))) throw Error('로그인 정보가 포함된 링크 대신 공개 채용 목록 주소를 입력하세요.');
  url.hash='';return url.href;
}
const nameKey=s=>s.toLowerCase().replace(/주식회사|㈜|\(주\)|\s/g,'').replace(/나이스/g,'nice');
export function makeSource(name,url,catalog=[]) {
  name=name.trim();url=recruitmentUrl(url);
  if (!name&&!url) throw Error('기업명이나 채용 링크를 입력하세요.');
  if (name.length>120||url.length>2000) throw Error('기업명 또는 링크가 너무 깁니다.');
  const known=!url&&catalog.find(s=>nameKey(s.name)===nameKey(name));
  return {name:name||(new URL(url)).hostname,url:url||(known?recruitmentUrl(known.url):''),enabled:true};
}
export function duplicateSource(list,item,exceptId) {
  return list.some(s=>s.id!==exceptId&&nameKey(s.name)===nameKey(item.name)&&s.url===item.url);
}
export function routineExport(sources) {
  return {format:'career-routine-sites',version:1,sources:sources.map(s=>{
    const clean=makeSource(s.name,s.url);
    return {name:clean.name,url:clean.url,enabled:s.enabled!==false};
  })};
}
