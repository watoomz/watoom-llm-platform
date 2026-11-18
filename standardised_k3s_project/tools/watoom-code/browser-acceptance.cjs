const {chromium}=require('playwright');
(async()=>{let browser,page,sessionID,api;try{
 browser=await chromium.launch({headless:true,args:['--no-sandbox','--host-resolver-rules=MAP watoom-code.internal.homelab.example '+process.env.WATOOM_RESOLVE_IP]});
 const context=await browser.newContext({ignoreHTTPSErrors:true,httpCredentials:{username:'opencode',password:process.env.WATOOM_AUTH_PASS}});
 page=await context.newPage();
 api=async(path,body)=>page.evaluate(async({path,auth,body})=>{const r=await fetch(path,{method:body===undefined?'GET':'POST',headers:{Authorization:auth,'content-type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});if(r.status===404)return {pending:true};if(!r.ok)throw Error('Authenticated API '+r.status);return r.json();},{path,body,auth:'Basic '+Buffer.from('opencode:'+process.env.WATOOM_AUTH_PASS).toString('base64')});
 await page.goto('https://watoom-code.internal.homelab.example/new-session',{waitUntil:'domcontentloaded',timeout:45000});
 await page.getByLabel('Server address',{exact:true}).fill('https://watoom-code.internal.homelab.example');
 await page.getByLabel('Password',{exact:true}).fill(process.env.WATOOM_AUTH_PASS);
 await page.getByRole('button',{name:'Connect',exact:true}).click();
 await page.getByLabel('Password',{exact:true}).waitFor({state:'hidden',timeout:30000});
 await page.getByRole('button',{name:'Add project',exact:true}).first().click();
 const dialog=page.getByRole('dialog');await dialog.waitFor();
 await dialog.locator('input').fill(process.env.WATOOM_WORKSPACE);
 await dialog.locator('input').press('Enter');
 await dialog.getByRole('button',{name:'Select folder',exact:true}).click();
 await dialog.waitFor({state:'hidden',timeout:30000});
 await page.locator('[data-action="home-new-session"]').click();
 const control=page.locator('[data-action="composer-model"]');await control.waitFor({timeout:30000});
 const initial=await control.innerText();await control.click();
 const options=await page.locator('[data-option-key]').evaluateAll(es=>es.map(e=>({key:e.getAttribute('data-option-key'),text:e.innerText,disabled:e.getAttribute('aria-disabled')})));
 const expectedLocal=['active-model','swift-qwen38-coder','qwen38-general','qwen38-uncensored-mtp','ornith-1.5-9b','qwen35-defiant-fable-9b','gemma-4-e4b','tiel-coder-35b-a3b-mtp','llama-mesh'];
 for(const id of expectedLocal)if(!options.some(x=>x.key==='watoom:'+id&&x.disabled!=='true'))throw Error('Missing local selection '+id);
 await page.locator('[data-option-key="watoom:gemma-4-e4b"]').click();
 await page.waitForFunction(()=>document.querySelector('[data-action="composer-model"]')?.textContent.includes('Gemma'));
 await control.click();await page.locator('[data-option-key="opencode:mimo-v2.6-flash-free"]').click();
 await page.waitForFunction(()=>document.querySelector('[data-action="composer-model"]')?.textContent.includes('MiMo'));
 const editors=page.locator('[contenteditable="true"]');await editors.first().fill('Reply only FREE_MODEL_OK. Do not use tools.');
 await page.locator('[data-action="composer-submit"]').click();
 await page.waitForURL(/\/session\//,{timeout:30000});
 const id=page.url().split('/session/')[1].split(/[/?#]/)[0];
 sessionID=id;const deadline=Date.now()+180000;let session;
 while(Date.now()<deadline){session=(await api('/api/session/'+id)).data;if(session?.outcome)break;await new Promise(r=>setTimeout(r,250));}
 if(session?.model?.providerID!=='opencode'||session?.model?.id!=='mimo-v2.6-flash-free')throw Error('Explicit free model was not committed to native session');
 const messages=await api('/api/session/'+id+'/message?type=assistant');
 const requestResult={sessionID:id,model:session.model,outcome:session.outcome,replyMarker:JSON.stringify(messages.data).includes('FREE_MODEL_OK')};
 await page.reload({waitUntil:'domcontentloaded'});await control.waitFor({timeout:30000});
 const persistedSelection=await control.innerText();
 if(requestResult.outcome!=='succeeded'||!requestResult.replyMarker)process.exitCode=1;
 console.log(JSON.stringify({status:requestResult.outcome==='succeeded'&&requestResult.replyMarker?'PASS':'FAIL',initial,options,requestResult,persistedSelection,url:page.url(),body:(await page.locator('body').innerText()).slice(-1800),screenshot:(await page.screenshot({fullPage:true,animations:"disabled"})).toString('base64')}));
} catch(e){console.log(JSON.stringify({status:'FAIL',error:e.message,url:page?.url(),sessionID,body:page?(await page.locator('body').innerText()).slice(-4000):'',buttons:page?await page.locator('button').evaluateAll(es=>es.map(e=>({text:e.innerText,aria:e.getAttribute('aria-label')}))):[]}));process.exitCode=1;}finally{
 if(api&&sessionID&&page&&!page.isClosed()){
  try{const current=await api('/api/session/'+sessionID);if(current.data&&!current.data.outcome)await api('/api/session/'+sessionID+'/interrupt',{resume:false});}
  catch(error){console.error('Own acceptance session cleanup failed: '+error.message);process.exitCode=1;}
 }
 if(browser)await browser.close();
}})();