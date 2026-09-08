// Public pages only. Fresh anonymous context per request; never reuse user cookies.
import {createInterface} from 'node:readline';
import {lookup} from 'node:dns/promises';
const {chromium}=await import(process.env.CAREER_PLAYWRIGHT);
const browser=await chromium.launch({headless:true});
async function publicUrl(value){
  try{
    const u=new URL(value);
    if(!['http:','https:'].includes(u.protocol)||u.username||u.password||u.port&&!['80','443'].includes(u.port))return false;
    const addresses=await lookup(u.hostname,{all:true});
    return addresses.length>0&&addresses.every(({address:a})=> !/^(127\.|10\.|192\.168\.|169\.254\.|0\.|172\.(1[6-9]|2\d|3[01])\.|::|fc|fd|fe[89ab])/i.test(a));
  }catch{return false;}
}
for await(const line of createInterface({input:process.stdin})){
  let context;
  try{
    const {url}=JSON.parse(line);if(!await publicUrl(url))throw Error('public URL required');
    context=await browser.newContext({locale:'ko-KR',viewport:{width:1280,height:900}});
    await context.route('**/*',async route=>{
      const request=route.request();
      if(['image','font','media'].includes(request.resourceType())||!await publicUrl(request.url()))return route.abort();
      return route.continue();
    });
    const page=await context.newPage();
    const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:30000});
    if(response&&[401,403,429].includes(response.status()))throw Error('HTTP '+response.status());
    await page.waitForTimeout(1800);
    await page.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));
    await page.waitForTimeout(800);
    const html=[];
    for(const frame of page.frames())try{html.push(await frame.content());}catch{}
    process.stdout.write(JSON.stringify({html:html.join('\n'),url:page.url()})+'\n');
  }catch(e){process.stdout.write(JSON.stringify({error:String(e.message).slice(0,180)})+'\n');}
  finally{if(context)await context.close();}
}
await browser.close();
