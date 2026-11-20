// Production UI acceptance; uses an isolated NSS trust/profile, never TLS bypass flags.
const fs=require('fs'),assert=require('assert');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const password=fs.readFileSync(0,'utf8').trim(),out=process.env.BROWSER_EVIDENCE;
 const context=await chromium.launchPersistentContext(out+'/profile',{headless:true,args:["--disable-gpu","--disable-software-rasterizer"],ignoreHTTPSErrors:false,viewport:{width:1440,height:1000},env:{...process.env,HOME:out+'/home'}});
 let page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 try{
  await page.goto('https://glance.internal.homelab.example/llm-lab',{waitUntil:'networkidle',timeout:45000});
  const link=page.getByRole('link',{name:'Model Manager',exact:true}).first();
  assert((await link.getAttribute('href')).includes('/model-manager/'));
  if(await link.getAttribute('target')==='_blank'){
   const next=context.waitForEvent('page');await link.click();page=await next;
  }else await link.click();
  await page.waitForLoadState('domcontentloaded');
  if(page.url().includes('/login')){
   assert((await page.locator('body').innerText()).includes('.private/llm-passwords.json'));
   await page.locator('input[type=password]').fill(password);
   await page.locator('button[type=submit],button').first().click();
  }
  await page.getByRole('heading',{name:'Model Manager',exact:true}).waitFor();
  await page.locator('#url').fill('https://huggingface.co/thejagstudio/3d-animation-style-sdxl');
  await page.locator('#inspect button').click();
  await page.locator('#details').waitFor({state:'visible',timeout:60000});
  assert((await page.locator('#repoBadges').textContent()).includes('SDXL LoRA'));
  assert((await page.locator('#repoBadges').textContent()).includes('stabilityai/stable-diffusion-xl-base-1.0'));
  assert((await page.locator('#files').textContent()).includes('228,679,500'));
  assert(await page.locator('#settings select').count()>0);
  assert((await page.locator('#base').innerText()).includes('stable-diffusion-xl-base-1.0'));
  assert((await page.locator('#modelGrid').textContent()).includes('✓ Registered'));
  assert((await page.locator('#modelGrid .card').count())>=10); // managed and pre-Model-Manager system models together
  await page.screenshot({path:out+'/production.png',fullPage:true});
  assert.deepStrictEqual(errors,[]);
  const code=await context.newPage();
  await code.goto('https://watoom-code.internal.homelab.example',{waitUntil:'networkidle',timeout:45000});
  await code.getByText(/Password reminder:/).first().waitFor({timeout:30000});
  assert((await code.locator('body').innerText()).includes('.private/llm-passwords.json'));
  await code.screenshot({path:out+'/code-login.png',fullPage:true});

  fs.writeFileSync(out+'/browser.json',JSON.stringify({state:'PASS',url:page.url(),glance_link:'PASS',login:'PASS',password_file_reminders:'PASS (manager and code)',live_lora_inspection:'PASS',exact_bytes:228679500,settings_dropdowns:'PASS',required_base:'PASS',durable_installed_models:'PASS',tls:'Validated through isolated NSS CA trust; no TLS bypass',mutation:'No installation, generation or deletion requested'},null,2));
 }finally{await context.close()}
})().catch(e=>{console.error(e.message);process.exitCode=1});
