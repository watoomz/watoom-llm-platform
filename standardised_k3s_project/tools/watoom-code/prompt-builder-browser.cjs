const fs = require("fs"), { chromium } = require(process.env.PLAYWRIGHT_MODULE);
(async () => {
  let browser, page;
  const out = process.env.EVIDENCE, base = process.env.CANDIDATE_BASE;
  try {
    browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome", headless: true, args: ["--no-sandbox", "--disable-gpu", ...(process.env.TRUSTED_TLS_SPKI ? ["--ignore-certificate-errors-spki-list=" + process.env.TRUSTED_TLS_SPKI] : [])] });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, httpCredentials: { username: "opencode", password: process.env.CANDIDATE_PASSWORD } });
    if (base.startsWith("https:") || ["localhost", "127.0.0.1"].includes(new URL(base).hostname)) await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    page = await context.newPage();
    const errors = []; page.on("pageerror", e => { errors.push(String(e.stack || e)); fs.writeFileSync(out + "/page-errors.json", JSON.stringify(errors, null, 2)); });
    const submitted = [];
    page.on("request", (request) => { if (request.method() === "POST" && /\/api\/(session|specialist)/.test(new URL(request.url()).pathname)) submitted.push(new URL(request.url()).pathname); });
    await page.goto(base + "/new-session", { waitUntil: "domcontentloaded", timeout: 30000 });
    const password = page.getByLabel("Password", { exact: true });
    // OpenCode v2.2.5 opens the connect screen on a pairing link; the password form sits behind "Use password".
    const usePassword = page.getByText("Use password", { exact: true });
    await password.or(usePassword).or(page.getByRole("button", { name: "Add project", exact: true }).first()).first().waitFor({ state: "visible", timeout: 30000 });
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
    await page.getByRole("button", { name: "Add project", exact: true }).first().waitFor({ timeout: 30000 });
    await page.goto(base + "/prompt-builder", { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.getByTestId("prompt-builder").waitFor({ timeout: 30000 });
    await page.getByText("Prompt creation skill: watoom-prompt-creator", { exact: true }).waitFor({ timeout: 30000 });
    const colours = [];
    for (const scheme of ["light", "dark"]) {
      await page.emulateMedia({ colorScheme: scheme });
      await page.waitForTimeout(200);
      const state = await page.locator("#prompt-pipeline").evaluate(select => {
        const option = select.options[1], field = getComputedStyle(select), item = getComputedStyle(option);
        return { field: { background: field.backgroundColor, color: field.color }, option: { background: item.backgroundColor, color: item.color }, label: option.textContent };
      });
      fs.writeFileSync(out + "/pipeline-colour-" + scheme + ".json", JSON.stringify(state, null, 2));
      for (const style of [state.field, state.option]) {
        if (style.background === "rgba(0, 0, 0, 0)" || style.background === "transparent" || style.background === style.color) throw Error("Pipeline dropdown has an unreadable or transparent background in " + scheme);
      }
      colours.push({ scheme, ...state });
      await page.locator("#prompt-pipeline").focus();
      await page.locator("#prompt-pipeline").press("Space");
      await page.screenshot({ path: out + "/pipeline-dropdown-" + scheme + ".png" });
      await page.keyboard.press("Escape");
    }
    fs.writeFileSync(out + "/pipeline-colours.json", JSON.stringify(colours, null, 2));
    const options = await page.locator("#prompt-pipeline option").count();
    if (options !== 28) throw Error("Expected all 27 maintained pipelines");
    await page.locator("#prompt-request").fill("Create a funny stylized wooden park bench");
    await page.getByRole("button", { name: "Prepare questions", exact: true }).click();
    if (!(await page.locator("#prompt-field-dimensions").inputValue()).includes("Propose sensible")) throw Error("Safe dimensional proposal absent");
    if (!(await page.locator("#prompt-field-budget").inputValue()).includes("2,000")) throw Error("Conservative budget absent");
    await page.locator("#prompt-field-dimensions").fill("1.6 m wide × 0.5 m deep × 0.85 m high; seat height 0.45 m");
    await page.locator("#prompt-field-materials").fill("Five seat slats, three back slats, dark metal supports; name parts semantically.");
    await page.getByRole("button", { name: "Build prompt", exact: true }).click();
    const output = page.getByTestId("prompt-output");
    const prompt = await output.inputValue();
    if (!prompt.includes("1.6 m wide") || !prompt.includes("SOURCE_QA") || !prompt.includes("watoom-prompt-blender-builder") || prompt.includes("```prompt-builder")) throw Error("Built prompt lost supplied dimensions or workflow guidance");
    await page.getByRole("button", { name: "Copy prompt", exact: true }).click();
    const secureClipboard = await page.evaluate(() => window.isSecureContext && !!navigator.clipboard);
    if (secureClipboard) {
      if (await page.evaluate(() => navigator.clipboard.readText()) !== prompt) throw Error("Clipboard differs from reviewed prompt");
    } else {
      if (await output.evaluate((element) => element.selectionEnd - element.selectionStart) !== prompt.length) throw Error("Clipboard fallback did not select the prompt");
    }
    fs.writeFileSync(out + "/bench-prompt.txt", prompt);
    await page.screenshot({ path: out + "/prompt-builder-desktop.png", fullPage: true });
    await page.locator("#prompt-field-budget").fill("Under 1,000 triangles");
    if (await output.inputValue() !== "" || await page.getByRole("button", { name: "Copy prompt", exact: true }).isEnabled()) throw Error("Changed specifications retained a stale copyable prompt");
    await page.locator("#prompt-pipeline").selectOption("research");
    await page.getByRole("button", { name: "Prepare questions", exact: true }).click();
    if (await page.locator("#prompt-field-dimensions").count()) throw Error("Unrelated dimensions asked for research");
    await page.getByRole("button", { name: "Build prompt", exact: true }).click();
    if (!(await output.inputValue()).includes("watoom-prompt-research")) throw Error("Pipeline-specific skill did not change");
    await page.locator("#prompt-request").fill("Create 3 still images of the same wooden bench: front, side and rear.");
    await page.locator("#prompt-pipeline").selectOption("image");
    await page.getByRole("button", { name: "Prepare questions", exact: true }).click();
    if (!(await page.locator("#prompt-field-model").inputValue()).includes("Discover compatible installed image models")) throw Error("Image pipeline requires an unknown model ID instead of a safe discovery default");
    await page.getByRole("button", { name: "Build prompt", exact: true }).click();
    if (!(await output.inputValue()).includes("watoom-prompt-image")) throw Error("Image prompt did not build with safe defaults");
    await page.locator("#prompt-field-description").fill("A wooden bench in a sunny park.");
    await page.locator("#prompt-field-danbooru-tags").fill("scenery, outdoors, scenery");
    await page.locator("#prompt-field-negative-description").fill("watermark, blurry");
    // The image skill leaves Pony quality scores blank until the checkpoint is verified; the user adds them.
    for (const id of ["positive-score-tags", "negative-score-tags"]) if (await page.locator("#prompt-field-" + id).inputValue()) throw Error("Quality scores are no longer blank by default: " + id);
    await page.locator("#prompt-field-positive-score-tags").fill("score_9, score_8_up, score_7_up");
    await page.locator("#prompt-field-negative-score-tags").fill("score_6, score_5, score_4");
    await page.locator("#prompt-field-output-count").fill("3");
    if (!(await page.locator("#prompt-field-positive-fidelity").inputValue()).includes("Light polish")) throw Error("Per-image refinement default is missing");
    await page.getByRole("button", { name: "Build prompt", exact: true }).click();
    const imagePrompt = await output.inputValue();
    if (!imagePrompt.startsWith("Positive prompt:\nA wooden bench in a sunny park. score_9, score_8_up, score_7_up, scenery, outdoors\n\nNegative prompt:\nscore_6, score_5, score_4, watermark, blurry\n")) throw Error("Image prompt did not preserve the prose-plus-tags format and separate negatives");
    if (!imagePrompt.includes("- Number of images: 3") || !imagePrompt.includes("Task: Create 3 still images")) throw Error("Explicit three-image scope was lost");
    if ((await page.locator("#prompt-field-image").inputValue()).includes("one image")) throw Error("Per-image defaults still override requested count");
    if ((await page.locator("#prompt-field-style").inputValue()).includes("stylized game art")) throw Error("Defaults still impose an unrequested style");
    if (imagePrompt.split("Negative prompt:")[0].includes("score_6")) throw Error("Negative quality tags leaked into positive prompt");
    await page.getByRole("button", { name: "Copy prompt", exact: true }).click();
    if (secureClipboard && await page.evaluate(() => navigator.clipboard.readText()) !== imagePrompt) throw Error("Image prompt clipboard differs from reviewed format");
    fs.writeFileSync(out + "/image-format-prompt.txt", imagePrompt);
    await page.screenshot({ path: out + "/image-format-form.png", fullPage: true });

    await page.locator("#prompt-project").fill("/workspace/images");
    await page.getByRole("button", { name: "Build prompt", exact: true }).click();
    if (!(await output.inputValue()).includes("Project: /workspace/images")) throw Error("Mounted workspace image destination was rejected");
    await page.locator("#prompt-project").fill("/data/ai/projects/images");
    await page.getByRole("button", { name: "Build prompt", exact: true }).click();
    if (!(await output.inputValue()).includes("Project: /data/ai/projects/images")) throw Error("Canonical image project destination was rejected");
    await page.waitForFunction(() => document.activeElement?.id === "prompt-output");
    await page.setViewportSize({ width: 412, height: 915 });
    await page.locator("#prompt-project").fill("/etc");
    await page.getByRole("button", { name: "Build prompt", exact: true }).click();
    await page.waitForFunction(() => document.activeElement?.id === "prompt-project");
    if (await page.locator("#prompt-project").getAttribute("aria-invalid") !== "true" || await output.inputValue() !== "") throw Error("Invalid project failed silently or retained stale output");
    await page.locator("#prompt-project").fill("/workspace/images");
    await page.getByRole("button", { name: "Build prompt", exact: true }).click();
    await page.waitForFunction(() => document.activeElement?.id === "prompt-output");
    const previewVisible = await output.evaluate(el => { const r = el.getBoundingClientRect(); return r.top < innerHeight && r.bottom > 0; });
    if (!previewVisible) throw Error("Built prompt remained outside the mobile viewport");
    await page.setViewportSize({ width: 1440, height: 1000 });

    await page.locator("#prompt-pipeline").selectOption("kali");
    await page.getByRole("button", { name: "Prepare questions", exact: true }).click();
    if (await page.locator("#prompt-field-authorization").inputValue() !== "") throw Error("Defaults invented security authorization");
    await page.getByRole("button", { name: "Build prompt", exact: true }).click();
    await page.waitForFunction(() => document.activeElement?.id === "prompt-field-authorization");
    if (await output.inputValue() !== "" || await page.locator("#prompt-field-authorization").getAttribute("aria-invalid") !== "true") throw Error("Missing authorization did not produce actionable validation");
    await page.locator("#prompt-pipeline").selectOption("blender-builder");
    await page.getByRole("button", { name: "Prepare questions", exact: true }).click();
    await page.getByRole("button", { name: "Build prompt", exact: true }).click();
    await page.setViewportSize({ width: 412, height: 915 });
    await page.screenshot({ path: out + "/prompt-builder-mobile.png", fullPage: true });
    const overflow = await page.evaluate(() => { const screen = document.querySelector("[data-testid=prompt-builder-screen]"); return screen.scrollWidth > screen.clientWidth + 2; });
    if (overflow) throw Error("Prompt page overflows its mobile width");
    if (submitted.length) throw Error("Prompt builder submitted session work: " + submitted.join(","));
    const result = { status: "PASS", pipeline_skills: options - 1, skill_driven: true, image_prose_tags: true, explicit_count_preserved: true, neutral_style_default: true, negative_prompt_separate: true, safe_defaults: true, supplied_dimensions_preserved: true, prompt_copy: secureClipboard ? "clipboard verified" : "selection fallback verified", stale_prompt_invalidated: true, pipeline_specific_questions: true, no_fabricated_authorization: true, no_session_or_job_submissions: true, mobile_width: "PASS", base };
    fs.writeFileSync(out + "/prompt-builder-browser.json", JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } catch (error) {
    if (page) { await page.getByText("Error Details", { exact: true }).click({ timeout: 1000 }).catch(() => {}); await page.screenshot({ path: out + "/prompt-builder-failure.png", fullPage: true }).catch(() => {}); fs.writeFileSync(out + "/prompt-builder-failure.json", JSON.stringify({ error: error.message, url: page.url(), body: await page.locator("body").innerText(), details: await page.locator("textarea").evaluateAll(xs => xs.map(x=>x.value)) }, null, 2)); }
    console.log(JSON.stringify({ status: "FAIL", error: error.message })); process.exitCode = 1;
  } finally { if (browser) await browser.close(); }
})();
