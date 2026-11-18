const fs = require("fs"), { chromium } = require(process.env.PLAYWRIGHT_MODULE);
(async () => {
  const out = process.env.EVIDENCE, base = process.env.CANDIDATE_BASE, id = process.env.IMAGE_SESSION, job = process.env.IMAGE_JOB;
  let browser;
  try {
    browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome", headless: true, args: ["--no-sandbox", "--disable-gpu"] });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, httpCredentials: { username: "opencode", password: process.env.CANDIDATE_PASSWORD } });
    const page = await context.newPage(), errors = [], writes = [];
    page.on("pageerror", error => errors.push(String(error)));
    page.on("request", request => { if (request.method() === "POST" && /\/api\/session(?:\/|$)/.test(new URL(request.url()).pathname)) writes.push(new URL(request.url()).pathname); });
    await page.goto(base + "/new-session", { waitUntil: "domcontentloaded" });
    const password = page.getByLabel("Password", { exact: true });
    await password.or(page.getByRole("button", { name: "Add project", exact: true }).first()).first().waitFor({ timeout: 30000 });
    if (await password.isVisible().catch(() => false)) {
      await page.getByLabel("Server address", { exact: true }).fill(base); await password.fill(process.env.CANDIDATE_PASSWORD);
      await page.getByRole("button", { name: "Connect", exact: true }).click(); await password.waitFor({ state: "hidden" });
    }
    const route = base + "/server/" + Buffer.from(base).toString("base64url") + "/session/" + id;
    let first = 0;
    await page.route("**/api/session/" + id + "/images*", async request => {
      if (first < 2 && !new URL(request.request().url()).searchParams.has("jobID")) {
        first += 1; return request.fulfill({ json: { data: first === 1 ? [] : [{ job_id: job, state: "GENERATING", error: null, updated: 0 }] } });
      }
      return request.continue();
    });
    await page.goto(route, { waitUntil: "domcontentloaded" });
    const panel = page.locator('[data-component="session-images"]');
    await panel.getByText("Image queued or generating.", { exact: false }).waitFor({ timeout: 30000 });
    await panel.locator("img").waitFor({ timeout: 300000 });
    await page.waitForFunction(() => { const image = document.querySelector('[data-component="session-images"] img'); return image && image.complete && image.naturalWidth > 0; });
    const dimensions = await panel.locator("img").evaluate(image => ({ width: image.naturalWidth, height: image.naturalHeight }));
    if (dimensions.width !== 512 || dimensions.height !== 512) throw Error("Unexpected verified image dimensions");
    await panel.scrollIntoViewIfNeeded(); await page.screenshot({ path: out + "/image-result-chat.png", fullPage: true });
    const download = page.waitForEvent("download"); await panel.getByText("Download image", { exact: true }).click();
    await (await download).saveAs(out + "/downloaded-bench.png");
    await page.setViewportSize({ width: 390, height: 844 }); await panel.scrollIntoViewIfNeeded();
    const width = await page.evaluate(() => ({ body: document.documentElement.scrollWidth, viewport: innerWidth }));
    if (width.body > width.viewport + 2) throw Error("Image result overflows mobile viewport");
    await page.screenshot({ path: out + "/image-result-mobile.png", fullPage: true });
    await page.unroute("**/api/session/" + id + "/images*");
    await page.route("**/api/session/" + id + "/images*", request => request.fulfill({ json: { data: [{ job_id: job, state: "FAILED", error: "Owned fixture failure", updated: 0 }] } }));
    await page.reload({ waitUntil: "domcontentloaded" });
    await panel.getByText("Image generation did not complete.", { exact: false }).waitFor({ timeout: 30000 });
    if (await panel.locator("img").count()) throw Error("Failed job displayed an image");
    if (errors.length || writes.length) throw Error(JSON.stringify({ errors, writes }));
    fs.writeFileSync(out + "/image-results-browser.json", JSON.stringify({ status: "PASS", cold_start_discovery: true, pending_to_verified: true, failed_without_replay: true, download: true, mobile: true, dimensions, session_writes: writes, page_errors: errors }, null, 2));
    console.log("PASS automatic image receipt display; no session writes");
  } catch (error) { fs.writeFileSync(out + "/image-results-failure.json", JSON.stringify({ error: String(error.stack || error) })); throw error; }
  finally { if (browser) await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
