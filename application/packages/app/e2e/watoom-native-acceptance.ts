import { chromium, expect } from "@playwright/test"
import fs from "node:fs/promises"
import path from "node:path"
const base = process.env.WATOOM_TEST_URL!
const evidence = process.env.WATOOM_TEST_EVIDENCE!
const authorization = "Basic " + Buffer.from("opencode:" + process.env.WATOOM_TEST_PASSWORD!).toString("base64")
const browser = await chromium.launch({ executablePath: "/usr/bin/google-chrome", headless: true, args: ["--disable-gpu", ...(process.getuid?.() === 0 ? ["--no-sandbox"] : [])] })
const context = await browser.newContext({ viewport: { width: 1440, height: 1400 }, acceptDownloads: true, serviceWorkers: "block" })
await context.route("**/*", (route) => new URL(route.request().url()).origin === base ? route.continue({ headers: { ...route.request().headers(), authorization } }) : route.abort())
const page = await context.newPage()
const errors: string[] = []
page.on("pageerror", (error) => errors.push(error.message))
const api = async () => (await context.request.get(base + "/api/config/profiles", { headers: { authorization } })).json()
try {
  await page.goto(base + "/settings?tab=extensions")
  const settings = page.getByTestId("settings-screen")
  await expect(settings).toBeVisible()
  await settings.getByRole("tab", { name: "Extensions", exact: true }).click()
  await settings.getByRole("tab", { name: "Skills", exact: true }).click()
  const profile = page.getByRole("region", { name: "WatooM profiles", exact: true })
  await expect(profile.getByRole("checkbox", { name: "minimal", exact: true })).toBeChecked()
  await profile.getByRole("checkbox", { name: "developer", exact: true }).check()
  await profile.getByRole("checkbox", { name: "component:blender", exact: true }).check()
  await profile.getByRole("button", { name: "Preview changes", exact: true }).click()
  await expect(profile.getByLabel("Preview changes", { exact: true })).toContainText("DRY_RUN")
  expect((await api()).selected).toEqual([])
  const applied = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/config/profiles" && response.request().method() === "POST" && response.status() === 200)
  await profile.getByRole("button", { name: "Install selected profiles", exact: true }).click()
  await applied
  await expect(profile.getByLabel("Preview changes", { exact: true })).toContainText("INSTALLED")
  await page.reload()
  await expect(profile.getByRole("checkbox", { name: "developer", exact: true })).toBeChecked()
  await expect(profile.getByRole("checkbox", { name: "component:blender", exact: true })).toBeChecked()
  expect((await api()).components).toEqual(["blender"])
  await expect(profile.getByTestId("availability:procedural-generators")).toHaveText("REQUIRES_CONFIGURATION")
  await profile.getByRole("checkbox", { name: "component:blender", exact: true }).uncheck()
  const removed = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/config/profiles" && response.request().method() === "POST" && response.status() === 200)
  await profile.getByRole("button", { name: "Install selected profiles", exact: true }).click()
  await removed
  await page.reload()
  await expect(profile.getByRole("checkbox", { name: "component:blender", exact: true })).not.toBeChecked()
  expect((await api()).components).toEqual([])
  const download = page.waitForEvent("download")
  await profile.getByRole("button", { name: "Export configuration", exact: true }).click()
  await (await download).saveAs(path.join(evidence, "m3-browser-export.json"))
  const exported = JSON.parse(await fs.readFile(path.join(evidence, "m3-browser-export.json"), "utf8"))
  expect(exported.selected).toEqual(["developer", "minimal"])
  expect(exported.components).toEqual([])
  const rollback = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/profiles/rollback") && response.status() === 200)
  await profile.getByRole("button", { name: "Roll back profile change", exact: true }).click()
  await rollback
  await expect(profile.getByRole("checkbox", { name: "component:blender", exact: true })).toBeChecked()
  const invalid = await context.request.post(base + "/api/config/profiles", { headers: { authorization }, data: { profiles: ["minimal"], disabled: ["native-core"] } })
  expect(invalid.status()).toBe(400)
  const signedOut = await browser.newContext()
  expect((await signedOut.request.get(base + "/api/config/profiles")).status()).toBe(401)
  await signedOut.close()
  await fs.writeFile(process.env.WATOOM_PROFILE_CONFIG! + "/opencode.jsonc.watoom-lock", "owned browser fixture lock")
  try {
    const failed = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/config/profiles" && response.request().method() === "POST" && response.status() === 400)
    await profile.getByRole("button", { name: "Install selected profiles", exact: true }).click()
    await failed
    await expect(profile.getByRole("alert")).toBeVisible()
  } finally { await fs.unlink(process.env.WATOOM_PROFILE_CONFIG! + "/opencode.jsonc.watoom-lock") }
  await expect(settings.getByRole("heading", { name: "Skill library", exact: true })).toBeVisible()
  await profile.getByRole("heading", { name: "WatooM profiles", exact: true }).scrollIntoViewIfNeeded()
  await page.screenshot({ path: path.join(evidence, "m3-profile-browser.png") })
  await profile.getByRole("button", { name: "Export configuration", exact: true }).scrollIntoViewIfNeeded()
  await page.screenshot({ path: path.join(evidence, "m3-profile-controls.png") })
  if (errors.length) throw Error(errors.join("\n"))
  await fs.writeFile(path.join(evidence, "m3-browser-results.json"), JSON.stringify({ status: "PASS", checks: ["real settings navigation", "preview", "apply", "reload persistence", "optional add/remove", "API consistency", "export", "rollback", "invalid denial", "authentication denial", "failure feedback", "skills navigation"] }, null, 2))
  console.log("M3_BROWSER=PASS")
} catch (error) {
  await fs.writeFile(path.join(evidence, "m3-browser-failure.txt"), String(error) + "\n" + errors.join("\n") + "\n" + (await page.locator("body").innerText()).slice(-5000))
  throw error
} finally { await browser.close() }
