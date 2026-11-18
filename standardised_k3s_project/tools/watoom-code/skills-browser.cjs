const fs = require("fs"), { chromium } = require(process.env.PLAYWRIGHT_MODULE);
(async () => {
  let browser, page;
  const evidence = process.env.EVIDENCE;
  try {
    browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome", headless: true,
      args: ["--no-sandbox", "--disable-gpu", ...(process.env.TRUSTED_TLS_SPKI ? ["--ignore-certificate-errors-spki-list=" + process.env.TRUSTED_TLS_SPKI] : [])] });
    const context = await browser.newContext({ colorScheme: process.env.SKILL_COLOR_SCHEME || "light", httpCredentials: { username: "opencode", password: process.env.CANDIDATE_PASSWORD } });
    page = await context.newPage();
    const failures = [];
    page.on("response", async response => {
      if (new URL(response.url()).pathname === "/api/agent") {
        const payload=await response.json().catch(()=>null);
        console.log(JSON.stringify({agentResponse:response.status(),url:response.url(),agents:payload?.data?.map(item=>({id:item.id,hidden:item.hidden}))}));
      }
    });
    page.on("pageerror", error => failures.push(error.message));
    const base = process.env.CANDIDATE_BASE;
    await page.goto(base + "/new-session", { waitUntil: "domcontentloaded" });
    const password = page.getByLabel("Password", { exact: true });
    // OpenCode v2.2.5 opens the connect screen on a pairing link; the password form sits behind "Use password".
    const usePassword = page.getByText("Use password", { exact: true });
    await password.or(usePassword).or(page.getByRole("button", { name: "Add project", exact: true }).first()).first().waitFor({ timeout: 30000 });
    if (await usePassword.isVisible().catch(() => false)) {
      await usePassword.click();
      await password.waitFor({ timeout: 30000 });
    }
    if (await password.isVisible().catch(() => false)) {
      await page.getByLabel("Server address", { exact: true }).fill(base);
      await password.fill(process.env.CANDIDATE_PASSWORD);
      await page.getByRole("button", { name: "Connect", exact: true }).click();
      await password.waitFor({ state: "hidden", timeout: 30000 });
    }
    await page.getByRole("button", { name: "Add project", exact: true }).first().waitFor({timeout:30000});
    // From the v2.2.5 GUI-plugin release the Skills page is a settings page opened by the watoom plugin's titlebar
    // pill; earlier releases had an app titlebar link to /skills. Either way the page below is the same.
    await page.getByRole("button", { name: "Skills", exact: true }).or(page.locator('[data-action="skills-navigation"]')).first().click();
    await page.waitForURL(/\/skills|[?&]tab=watoom-skills/);
    await page.getByRole("heading", { name: "Skills", exact: true }).waitFor();
    await page.locator('[data-testid="skill-catalog-counts"]').waitFor();
    await page.screenshot({ path: evidence + "/skills-main-navigation.png", fullPage: true });
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.locator('[data-testid="skill-catalog-counts"]').waitFor();
    const settleMenu=async()=>page.getByRole("listbox").evaluate(async node=>{
      const animations=new Set();
      for(let current=node;current;current=current.parentElement)
        for(const animation of current.getAnimations())animations.add(animation);
      await Promise.all([...animations].map(animation=>animation.finished.catch(()=>{})));
    }).then(async()=>{
      const node=await page.getByRole("listbox").elementHandle();
      await page.waitForFunction(node=>{for(let current=node;current;current=current.parentElement)if(Number(getComputedStyle(current).opacity)<.99)return false;return true},node,{timeout:10000});
    });
    const projectPicker=page.locator('[data-component="select-v2"][aria-label="Project directory"]');
    await projectPicker.click();
    await page.getByRole("option").filter({hasText:"Server default project"}).waitFor();
    await page.waitForFunction(()=>document.querySelectorAll('[role="option"]').length>1,undefined,{timeout:30000});
    await settleMenu();
    const projectLabels=await page.getByRole("option").allTextContents();
    fs.writeFileSync(evidence+"/project-options.json",JSON.stringify(projectLabels,null,2));
    await page.screenshot({path:evidence+"/skills-project-dropdown-"+(process.env.SKILL_COLOR_SCHEME||"light")+".png",fullPage:true});
    await page.keyboard.press("Escape");
    await page.locator('[data-slot="select-v2-content"]').last().waitFor({state:"hidden"});
    const agentPicker = page.locator('[data-component="select-v2"][aria-label="Agent defaults"]');
    await agentPicker.click();
    for (const agent of ["watoom-workflow","watoom-builder","watoom-investigator","watoom-reviewer","watoom-critic","watoom-kali"])
      await page.getByRole("option", {name:agent,exact:true}).waitFor({timeout:45000});
    await settleMenu();
    await page.screenshot({path:evidence+"/skills-agent-dropdown-"+(process.env.SKILL_COLOR_SCHEME||"light")+".png",fullPage:true});
    const contrast = await page.getByRole("option").evaluateAll(nodes => nodes.map(node=>{
      const rgb=value=>value.match(/[0-9.]+/g)?.slice(0,3).map(Number);
      const luminance=rgb=>rgb.map(x=>{const s=x/255;return s<=.04045?s/12.92:((s+.055)/1.055)**2.4}).reduce((sum,x,i)=>sum+x*[.2126,.7152,.0722][i],0);
      let parent=node,background="rgba(0, 0, 0, 0)";
      while(parent){background=getComputedStyle(parent).backgroundColor;if(background!=="rgba(0, 0, 0, 0)"&&background!=="transparent")break;parent=parent.parentElement;}
      const color=getComputedStyle(node).color,a=luminance(rgb(color)),b=luminance(rgb(background));
      return {text:node.textContent,color,background,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
    }));
    fs.writeFileSync(evidence+"/agent-dropdown-contrast.json",JSON.stringify(contrast,null,2));
    if(contrast.some(item=>!Number.isFinite(item.ratio)||item.ratio<4.5))throw Error("Agent option contrast below4.5:1 before hover");
    await page.keyboard.press("Escape");
    await page.getByRole("tab", { name: "Installed", exact: true }).click();
    await page.getByRole("heading", { name: "Native skills", exact: true }).waitFor();
    await page.getByRole("tab", { name: "Available", exact: true }).click();
    const readableQuery=process.env.SKILL_READABILITY_QUERY;
    if(readableQuery){
      await page.getByLabel("Search skill names and descriptions",{exact:true}).fill(readableQuery);
      await page.getByRole("button",{name:"Search",exact:true}).click();
      const row=page.locator('[data-skill-id="github:agentbay-ai/agentbay-skills:agentbay-aio-skills"]');
      await row.locator('[data-testid="skill-display-name"]').filter({hasText:"AgentBay Code Execution"}).waitFor();
      if(!(await row.locator('[data-testid="skill-display-description"]').innerText()).includes("Python"))throw Error("English summary missing");
      await row.locator('[data-testid="skill-original-description"] summary').click();
      if(!(await row.locator('[data-testid="skill-original-description"]').innerText()).includes("用于"))throw Error("Original source description lost");
      await page.screenshot({path:evidence+"/skills-readable-english.png",fullPage:true});
      await page.getByLabel("Search skill names and descriptions",{exact:true}).fill("animation");
      await page.getByRole("button",{name:"Search",exact:true}).click();
      if(await page.locator('[data-testid="skill-catalog-rows"]').innerText().then(text=>text.includes("KNOWLEDGE_REFERENCE")))throw Error("Knowledge candidate still visible");
    }
    const fixture = process.env.SKILL_FIXTURE_ID;
    if (fixture) {
      await page.locator('[data-component="select-v2"][aria-label="Project directory"]').click();
      await page.getByRole("option").filter({hasText:process.env.SKILL_PROJECT}).click();
      // The picker shows the chosen project; earlier releases also put it in the URL, the settings page does not.
      await page.locator('[data-component="select-v2"][aria-label="Project directory"]').filter({hasText:process.env.SKILL_PROJECT}).waitFor();
      await page.getByLabel("Search skill names and descriptions", { exact: true }).fill(fixture.endsWith(":unsafe") ? "skill-manager-unsafe" : "skill-manager-control");
      await page.getByRole("button", { name: "Search", exact: true }).click();
      const target = page.locator('[data-skill-id="' + fixture + '"]');
      await target.waitFor();
      await target.getByRole("button", { name: "Review details", exact: true }).click();
      await target.locator('[data-testid="skill-instructions"]').waitFor();
      if (!["github:owned/manager:control", "github:owned/manager:unsafe"].includes(fixture) || process.env.SKILL_PROJECT !== "/workspace/skills-project")
        throw Error("Only isolated owned test records may be mutated");
      const phase = process.env.SKILL_PHASE || "install";
      const waitState = async (expected) => page.waitForFunction(expected => [...document.querySelectorAll('[role="status"]')].some(node => node.textContent.includes(expected)), expected);
      const lifecycle = async (labels) => {
        const expected = {Stage:"STAGED","Review update":"STAGED","Confirm review":"REVIEWED",Validate:"VALIDATED",Approve:"APPROVED",Install:"INSTALLED",Enable:"ENABLED"};
        for (const label of labels) {
          await target.getByRole("button", { name: label, exact: true }).click();
          await waitState(expected[label]);
        }
      };
      if (phase === "install") await lifecycle(["Stage", "Confirm review", "Validate", "Approve", "Install", "Enable"]);
      if (phase === "update") await lifecycle(["Review update", "Confirm review", "Validate", "Approve", "Install", "Enable"]);
      if (phase === "disable") {
        await target.getByRole("button", { name: "Disable", exact: true }).click();
        await waitState("DISABLED");
      }
      if (phase === "rollback") {
        await target.getByRole("button", { name: "Restore verified version", exact: true }).locator("..")
          .filter({ hasText: process.env.SKILL_ROLLBACK_BUNDLE.slice(0, 12) })
          .getByRole("button", { name: "Restore verified version", exact: true }).click();
        await waitState("ENABLED");
      }
      if (phase === "unsafe") {
        const stage = target.getByRole("button", { name: "Stage", exact: true });
        if (!(await stage.isDisabled())) throw Error("Unsafe source offered installation");
        const risk = target.getByRole("checkbox");
        if (await risk.count()) await risk.check();
        if (!(await stage.isDisabled())) throw Error("Unsafe source became installable after elevated acknowledgement");
      } else {
        await page.locator('[data-component="select-v2"][aria-label="Agent defaults"]').click();
        await page.getByRole("option",{name:process.env.SKILL_AGENT,exact:true}).click();
        if (["disable", "rollback"].includes(phase)) {
          const remove = page.getByRole("button", { name: "Remove preference", exact: true });
          await remove.waitFor({ timeout: 15000 });
          await remove.click();
          await remove.waitFor({ state: "hidden" });
        }
        if (["install", "update", "rollback"].includes(phase)) {
          await target.getByRole("button", { name: "Select approved version", exact: true }).click();
          await page.getByText("SELECTED_NOT_EXECUTED", { exact: false }).first().waitFor();
        }
        if (process.env.SKILL_EXPECT_MARKER) {
          await target.locator('[data-testid="skill-installed-instructions"]').filter({hasText:process.env.SKILL_EXPECT_MARKER}).waitFor();
        }
      }
      await page.screenshot({ path: evidence + "/skills-" + phase + ".png", fullPage: true });
      if (process.env.SKILL_RUN_SESSION === "1") {
        if (!["install","persist"].includes(phase)) throw Error("Real GUI execution requires an installed owned test record");
        await page.goto(base + "/", {waitUntil:"domcontentloaded"});
        await page.getByRole("button",{name:"Add project",exact:true}).first().click();
        const dialog = page.getByRole("dialog"); await dialog.waitFor();
        await page.waitForFunction(() => performance.getEntriesByType("resource").some(entry => entry.name.includes("/api/location")));
        await dialog.getByRole("button",{name:"Root",exact:true}).click();
        await page.waitForFunction(() => {const node=document.querySelector('[role="dialog"]');return node && [...node.querySelectorAll("button")].some(button => button.textContent==="Select folder" && !button.disabled)});
        await dialog.locator("input").fill(process.env.SKILL_PROJECT); await dialog.locator("input").press("Enter");
        await dialog.getByRole("button",{name:"Select folder",exact:true}).click(); await dialog.waitFor({state:"hidden"});
        await page.locator('[data-action="home-new-session"]').click();
        const editor=page.locator('[contenteditable="true"]').first(); await editor.waitFor();
        await page.getByRole("button",{name:"Choose agent",exact:true}).click();
        await page.getByRole("menuitemradio",{name:new RegExp("^"+process.env.SKILL_AGENT+"$","i")}).click();
        const created=page.waitForResponse(response => new URL(response.url()).pathname==="/api/session" && response.request().method()==="POST" && response.ok());
        await editor.fill("Use the assigned read-only skills manager acceptance check. Load the matching available skill using the native skill function, then return its marker. Do not use any other tool.");
        await page.locator('[data-action="composer-submit"]').click();
        const session=(await (await created).json()).data;
        fs.writeFileSync(evidence+"/runtime-session.json",JSON.stringify({session:session.id,agent:session.agent,project:process.env.SKILL_PROJECT},null,2));
        if(session.agent!==process.env.SKILL_AGENT)throw Error("GUI did not select the requested agent");
        await page.waitForURL(/\/session\//,{timeout:30000});
        await page.waitForFunction(marker=>document.body.innerText.includes(marker),process.env.SKILL_EXPECT_MARKER,{timeout:120000});
        await page.screenshot({path:evidence+"/skills-real-agent-session.png",fullPage:true});
      }

    } else {
      await page.getByLabel("Search skill names and descriptions", { exact: true }).fill("agentbay-aio-skills");
      await page.getByRole("button", { name: "Search", exact: true }).click();
      const row = page.locator('[data-testid="skill-catalog-rows"] article').first();
      await row.waitFor();
      await row.getByRole("button", { name: "Review details", exact: true }).click();
      await row.locator('[data-testid="skill-instructions"]').waitFor();
      const preview = await row.locator('[data-testid="skill-instructions"]').innerText();
      if (!preview.trim()) throw Error("Empty collected skill preview");
      await page.screenshot({ path: evidence + "/skills-collected-review.png", fullPage: true });
      const result = page.waitForResponse(response => response.url().includes("/api/skill/catalog?") && response.url().includes("query=https") && response.ok());
      await page.getByLabel("Search skill names and descriptions", { exact: true }).fill("https");
      await page.getByRole("button", { name: "Search", exact: true }).click();
      const data = (await (await result).json()).data;
      if(await page.getByRole("heading",{name:"Knowledge references",exact:true}).count())throw Error("Knowledge references still displayed");
      if((await page.locator('[data-testid="skill-catalog-rows"]').innerText()).includes("KNOWLEDGE_REFERENCE"))throw Error("Knowledge cards still displayed");
      if(data.matched<=32 && !(await page.getByRole("button",{name:"Next",exact:true}).isDisabled()))throw Error("Reference count still creates empty skill pages");
      await page.screenshot({path:evidence+"/skills-only-no-references.png",fullPage:true});


    }
    if (failures.length) throw Error("Skills page errors: " + failures.join("; "));
    fs.writeFileSync(evidence + "/skills-browser.json", JSON.stringify({ status: "PASS", native_navigation: "PASS", direct_refresh: "PASS", installed: "PASS",
      collected_search_preview: "PASS", fixture: fixture ?? null, fixture_gui_install_assignment: fixture && (!process.env.SKILL_PHASE || process.env.SKILL_PHASE === "install") ? "PASS" : "NOT TESTED", phase: process.env.SKILL_PHASE || "smoke", url: page.url() }, null, 2));
    console.log(JSON.stringify({ status: "PASS", fixture: fixture ?? null }));
  } catch (error) {
    if (page) {
      await page.screenshot({ path: evidence + "/skills-browser-failure.png", fullPage: true }).catch(() => {});
      fs.writeFileSync(evidence + "/skills-browser-failure.json", JSON.stringify({ error: error.message, url: page.url(), body: await page.locator("body").innerText() }, null, 2));
    }
    console.log(JSON.stringify({ status: "FAIL", error: error.message }));
    process.exitCode = 1;
  } finally { if (browser) await browser.close(); }
})();
