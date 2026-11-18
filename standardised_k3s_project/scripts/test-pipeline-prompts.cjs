// Read-only live UI test. Requires an isolated CA-trusting browser profile.
const fs=require("fs"),assert=require("assert");
const expected=require("../config/glance/pipeline-prompts.json").templates.length;
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||"playwright");
(async()=>{
 const out=process.env.BROWSER_EVIDENCE;
 const context=await chromium.launchPersistentContext(out+"/profile",{headless:true,args:["--disable-gpu","--disable-software-rasterizer"],ignoreHTTPSErrors:false,viewport:{width:1440,height:1000},env:{...process.env,HOME:out+"/home"}});
 const page=await context.newPage(),errors=[];page.on("pageerror",e=>errors.push(String(e)));
 try{
  await page.goto("https://glance.internal.homelab.example/llm-lab",{waitUntil:"networkidle",timeout:45000});
  const link=page.getByRole("link",{name:"Pipeline Prompt Templates",exact:true}).first();
  const url=await link.getAttribute("href");assert(url.endsWith("/guide/pipeline-prompts.html"));
  await page.goto(url,{waitUntil:"networkidle"});
  await page.getByRole("heading",{name:"Pipeline prompt templates",exact:true}).waitFor();
  assert.equal(await page.locator(".prompt-card").count(),expected);
  await page.locator("#search").fill("no-such-pipeline-zzzz");
  assert.equal(await page.locator(".prompt-card:visible").count(),0);assert(await page.locator("#empty").isVisible());
  await page.locator("#search").fill("LLaMA-Mesh");assert(await page.locator(".prompt-card:visible").count()>0);
  await page.locator("#search").fill("");
  await page.locator("#project").fill("/data/ai/projects/games/prompt-ui-test");
  await context.grantPermissions(["clipboard-read","clipboard-write"],{origin:"https://glance.internal.homelab.example"});
  const cards=page.locator(".prompt-card");
  for(let i=0;i<expected;i++){
   await cards.nth(i).locator("button.copy").click();
   const copied=await page.evaluate(()=>navigator.clipboard.readText());
   assert(copied.includes("/data/ai/projects/games/prompt-ui-test"));assert(!copied.includes("[PROJECT_PATH]"));
   assert(copied.endsWith(await cards.nth(i).locator("textarea").inputValue().then(v=>v.split("\n\n").slice(-1)[0])));
  }
  assert((await page.locator("#fixed-map").innerText()).includes("capability-gated"));
  assert((await page.locator("#effects textarea").inputValue()).includes("Static load"));
  await page.screenshot({path:out+"/desktop.png",fullPage:true});
  await page.evaluate(()=>{navigator.clipboard.writeText=async()=>{throw new Error("test denied")};});
  await page.locator("#asset-search button").click();assert(await page.locator("#asset-search details").getAttribute("open")!==null);
  assert((await page.locator("#feedback").innerText()).includes("copy it manually"));
  await page.locator("#project").fill("/data/ai/projects/llm/new-path");await page.locator("#asset-search button").click();assert((await page.locator("#asset-search textarea").inputValue()).includes("/data/ai/projects/llm/new-path"));
  for(const invalid of ["/data/ai/projects/development/old-path","/data/ai/projects/games","/data/ai/projects/games/../private"]){
   await page.locator("#project").fill(invalid);assert.equal(await page.locator("#project").getAttribute("aria-invalid"),"true");
   await page.locator("#asset-search button").click();const text=await page.locator("#asset-search textarea").inputValue();assert(!text.includes(invalid)&&text.includes("[PROJECT_PATH]"));
  }
  const prompt=await page.locator("#asset-search textarea").inputValue();assert(!/\/data\/ai\/projects\/(development|pipelines)\b/.test(prompt));
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:out+"/mobile.png",fullPage:true});
  assert.deepStrictEqual(errors,[]);
  fs.writeFileSync(out+"/browser.json",JSON.stringify({status:"PASS",url,templates:expected,glance_link:"PASS",filter:"PASS",clipboard_all_templates:"PASS",placeholder_substitution:"PASS",clipboard_fallback:"PASS",project_group_validation:"PASS",mobile_no_overflow:"PASS",console_errors:errors,tls:"isolated existing CA; no bypass",jobs_started:0},null,2));
 }finally{await context.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1});
