const fs=require('fs'),{chromium}=require(process.env.PLAYWRIGHT_MODULE);
(async()=>{let browser,page;try{
 browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox','--disable-gpu',...(process.env.TRUSTED_TLS_SPKI?['--ignore-certificate-errors-spki-list='+process.env.TRUSTED_TLS_SPKI]:[])]});
 const context=await browser.newContext({httpCredentials:{username:'opencode',password:process.env.CANDIDATE_PASSWORD}});
 page=await context.newPage();
 await page.goto(process.env.CANDIDATE_BASE+'/new-session',{waitUntil:'domcontentloaded',timeout:30000});
 const password=page.getByLabel('Password',{exact:true});
 // Current app builds open on a pairing screen; the password form sits behind "Use password".
 const usePassword=page.getByText('Use password',{exact:true}).first();
 await usePassword.or(password).or(page.getByRole('button',{name:'Add project',exact:true}).first()).first().waitFor({state:'visible',timeout:30000});
 if(await usePassword.isVisible().catch(()=>false))await usePassword.click();
 await password.or(page.getByRole('button',{name:'Add project',exact:true}).first()).first().waitFor({state:'visible',timeout:30000});
 if(await password.isVisible().catch(()=>false)){
  await page.getByLabel('Server address',{exact:true}).fill(process.env.CANDIDATE_BASE);
  await password.fill(process.env.CANDIDATE_PASSWORD);
  await page.getByRole('button',{name:'Connect',exact:true}).click();
  await password.waitFor({state:'hidden',timeout:30000});
 }
 if(process.env.NATIVE_REPLAY_SESSION){
  const encoded=Buffer.from(process.env.CANDIDATE_BASE).toString('base64url');
  await page.goto(process.env.CANDIDATE_BASE+'/server/'+encoded+'/session/'+process.env.NATIVE_REPLAY_SESSION,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('[data-action="composer-model"]')?.textContent.includes('Swift'),{timeout:30000});
  const editor=page.locator('[contenteditable="true"]').first();await editor.waitFor({timeout:20000});
  const journal=process.env.EVIDENCE+'/gui-submission.json';if(fs.existsSync(journal))throw Error('Inspect existing GUI admission; never submit twice');
  fs.writeFileSync(journal,JSON.stringify({status:'PREPARED',session:process.env.NATIVE_REPLAY_SESSION},null,2));
  await editor.fill(process.env.NATIVE_REPLAY_PROMPT);
  await page.locator('[data-action="composer-submit"]').click();
  if(process.env.NATIVE_SUBMIT_ONLY){
   const auth='Basic '+Buffer.from('opencode:'+process.env.CANDIDATE_PASSWORD).toString('base64');
   const deadline=Date.now()+20000;let recorded=false;
   while(Date.now()<deadline){
    const response=await context.request.get(process.env.CANDIDATE_BASE+'/api/session/'+process.env.NATIVE_REPLAY_SESSION+'/message',{headers:{Authorization:auth}});
    if(response.ok()){const value=await response.json();recorded=(value.data||[]).some(x=>x.type==='user');if(recorded)break;}
    await new Promise(r=>setTimeout(r,250));
   }
   if(!recorded)throw Error('GUI prompt was not recorded by the authenticated server');
   await page.screenshot({path:process.env.EVIDENCE+'/native-gui-submitted.png',fullPage:true});
   fs.writeFileSync(process.env.EVIDENCE+'/native-gui-submission.json',JSON.stringify({status:'SUBMITTED',authenticated_gui_submission:true,server_prompt_recorded:true,session:process.env.NATIVE_REPLAY_SESSION},null,2));
   console.log(JSON.stringify({status:'SUBMITTED',server_prompt_recorded:true}));return;
  }
  await page.waitForFunction(id=>document.body.innerText.includes(id),process.env.NATIVE_REPLAY_TOOLKIT_JOB,{timeout:120000});
  await page.screenshot({path:process.env.EVIDENCE+'/native-replay-gui.png',fullPage:true});
  fs.writeFileSync(process.env.EVIDENCE+'/native-replay-browser.json',JSON.stringify({status:'PASS',authenticated_gui_submission:true,session:process.env.NATIVE_REPLAY_SESSION,toolkit_job:process.env.NATIVE_REPLAY_TOOLKIT_JOB},null,2));
  console.log(JSON.stringify({status:'PASS',authenticated_gui_submission:true}));return;
 }
 if(process.env.CREATIVE_ROUTE_SESSION){
  const encoded=Buffer.from(process.env.CANDIDATE_BASE).toString('base64url');
  await page.goto(process.env.CANDIDATE_BASE+'/server/'+encoded+'/session/'+process.env.CREATIVE_ROUTE_SESSION,{waitUntil:'domcontentloaded'});
  const expected=JSON.parse(process.env.CREATIVE_ARTIFACT_JOBS||'[]');
  if(!expected.length)throw Error('Actual completed creative artifact identities required');
  await page.waitForFunction(ids=>ids.every(id=>document.body.innerText.includes(id)),expected,{timeout:30000});
  const visible=await page.locator('body').innerText();
  await page.screenshot({path:process.env.EVIDENCE+'/creative-authenticated-gui.png',fullPage:true});
  fs.writeFileSync(process.env.EVIDENCE+'/creative-browser.json',JSON.stringify({status:'PASS',authenticated_gui:'PASS',route:process.env.CANDIDATE_BASE,session:process.env.CREATIVE_ROUTE_SESSION,visible_artifact_jobs:expected,body:visible},null,2));
  console.log(JSON.stringify({status:'PASS',visible_artifact_jobs:expected}));return;
 }
 if(process.env.MEMORY_ROUTE_SESSION){
  const encoded=Buffer.from(process.env.CANDIDATE_BASE).toString('base64url');
  await page.goto(process.env.CANDIDATE_BASE+'/server/'+encoded+'/session/'+process.env.MEMORY_ROUTE_SESSION,{waitUntil:'domcontentloaded'});
  await page.locator('[data-slot="session-timeline-memory"]').filter({hasText:process.env.MEMORY_GUI_FACT}).first().waitFor({timeout:20000});
  await page.screenshot({path:process.env.EVIDENCE+'/traefik-memory-gui.png',fullPage:true});
  fs.writeFileSync(process.env.EVIDENCE+'/traefik-browser.json',JSON.stringify({status:'PASS',authenticated_gui:'PASS',route:process.env.CANDIDATE_BASE},null,2));
  console.log(JSON.stringify({status:'PASS',route:'Traefik'}));return;
 }
 const add=page.getByRole('button',{name:'Add project',exact:true}).first();
 await add.waitFor({timeout:30000});await add.click();
 const dialog=page.getByRole('dialog');await dialog.waitFor();
 // Finish the picker's asynchronous initial location load before entering a path.
 // Otherwise its initial home navigation can overwrite the automation's input.
 await page.waitForFunction(()=>performance.getEntriesByType('resource').some(e=>e.name.includes('/api/location')));
 await dialog.getByRole('button',{name:'Root',exact:true}).click();
 await page.waitForFunction(()=>{const d=document.querySelector('[role="dialog"]');return d&&Array.from(d.querySelectorAll('button')).some(b=>b.textContent==='Select folder'&&!b.disabled)});

 await dialog.locator('input').fill(process.env.MEMORY_PROJECT_DIRECTORY||'/workspace');await dialog.locator('input').press('Enter');
 await dialog.getByRole('button',{name:'Select folder',exact:true}).click();
 await dialog.waitFor({state:'hidden',timeout:15000});
 await page.locator('[data-action="home-new-session"]').click();
 const editor=page.locator('[contenteditable="true"]').first();await editor.waitFor({timeout:20000});
 await editor.fill('/remember');
 await page.screenshot({path:process.env.EVIDENCE+'/candidate-slash-menu.png',fullPage:true});
 const menu=await page.locator('body').innerText();
 if(!menu.includes('remember'))throw Error('Remember command missing from GUI');
 const fact=process.env.MEMORY_GUI_FACT||'GUI-owned-memory-fact-20261016T204420Z';
 await editor.fill('/remember '+fact);
 await page.locator('[data-action="composer-submit"]').click();
 await page.waitForURL(/\/session\//,{timeout:20000});
 const sessionID=page.url().split('/session/')[1].split(/[/?#]/)[0];
 await page.waitForTimeout(500);
 await page.screenshot({path:process.env.EVIDENCE+'/candidate-remember-gui.png',fullPage:true});
 const body=await page.locator('body').innerText();
 const api=async(path,body)=>page.evaluate(async({path,body,auth})=>{const response=await fetch(path,{method:body?'POST':'GET',headers:{Authorization:auth,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});if(!response.ok)throw Error('GUI API status '+response.status);const raw=await response.text();return raw?JSON.parse(raw):null},{path,body,auth:'Basic '+Buffer.from('opencode:'+process.env.CANDIDATE_PASSWORD).toString('base64')});
 const messages=await api('/api/session/'+sessionID+'/message');
 if(!JSON.stringify(messages).includes('verified receipt'))throw Error('GUI command did not save memory');
 await editor.fill('/recall '+fact);
 await page.locator('[data-action="composer-submit"]').click();
 await page.waitForTimeout(500);
 const recalled=await api('/api/session/'+sessionID+'/message');
 if(!JSON.stringify(recalled).includes(fact))throw Error('GUI recall missing fact');
 await page.locator('[data-slot="session-timeline-memory"]').filter({hasText:fact}).waitFor({timeout:10000});
 if(!(await page.locator('[data-slot="session-timeline-memory"]').first().innerText()).includes('verified receipt'))throw Error('Receipt not visibly rendered');
 await page.screenshot({path:process.env.EVIDENCE+'/candidate-recall-gui.png',fullPage:true});
 const result={status:'PASS',authenticated_gui:'PASS',commands:['remember','recall'],sessionID,url:page.url(),body};
 fs.writeFileSync(process.env.EVIDENCE+'/candidate-browser.json',JSON.stringify(result,null,2));console.log(JSON.stringify({status:'PASS',sessionID}));
}catch(error){if(page){await page.screenshot({path:process.env.EVIDENCE+'/candidate-browser-failure.png',fullPage:true}).catch(()=>{});fs.writeFileSync(process.env.EVIDENCE+'/candidate-browser-failure.json',JSON.stringify({error:error.message,url:page.url(),body:await page.locator('body').innerText()},null,2));}console.log(JSON.stringify({status:'FAIL',error:error.message}));process.exitCode=1;}finally{if(browser)await browser.close();}})();
