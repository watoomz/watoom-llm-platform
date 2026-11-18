import { chromium, expect } from "@playwright/test"
import { mockOpenCodeServer } from "./utils/mock-server"
import fs from "node:fs/promises"
const base = process.env.PLAYWRIGHT_BASE_URL!
if (!base || !process.env.WATOOM_TEST_EVIDENCE) throw Error("Set isolated fixture URL and evidence directory")
const browser = await chromium.launch({
  executablePath: "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-gpu"],
})
const context = await browser.newContext({ viewport: { width: 1440, height: 1200 }, serviceWorkers: "block" })
const page = await context.newPage()
const errors: string[] = []
page.on("pageerror", (e) => errors.push(e.message))
await mockOpenCodeServer(page, {
  directory: "/tmp/catalogue-fixture",
  project: {
    id: "proj_catalogue",
    canonical: "/tmp/catalogue-fixture",
    name: "Catalogue fixture",
    time: { created: 1, updated: 1 },
    sandboxes: [],
  },
  provider: { all: [], connected: [], default: {} },
  sessions: [],
  pageMessages: () => ({ items: [] }),
})
const entries = [
  {
    id: "comic-pipeline",
    name: "Graphic novel pipeline",
    description: "Write page scripts and persistent illustration notes, then create matching artwork.",
    kind: "pipeline",
    pipelineID: "comic",
    category: "writing",
    aliases: ["graphic novel"],
    requires: ["illustration-notes"],
    availability: "installed",
    autoinvoke: true,
  },
  {
    id: "illustration-notes",
    name: "Illustration notes",
    description: "Track composition, continuity and artwork requirements for each page.",
    kind: "skill",
    aliases: [],
    requires: [],
    availability: "installed",
    autoinvoke: true,
  },
]
await page.route("**/api/skill/index*", (route) =>
  route.fulfill({
    json: {
      data: {
        catalogueSize: 2,
        entries: route.request().url().includes("graphic") ? [entries[0]] : entries,
        ranked: route.request().url().includes("graphic"),
      },
    },
  }),
)
const now = Date.now()
let stale = false
await page.route("**/api/memory/status*", (route) =>
  route.fulfill({
    json: {
      data: {
        memory: {
          enabled: true,
          required: true,
          sampledAt: now,
          outbox: {
            pending: 1,
            sending: 0,
            uncertain: 1,
            observed: 12,
            attempts: 14,
            lastCheckpoint: now,
            lastObserved: now,
            oldestPending: now,
          },
          retrieval: {
            attempts: 2,
            failures: 1,
            lastAttempt: now,
            lastSuccess: now,
            latencyMs: 15,
            unavailable: false,
          },
          warnings: ["delivery-uncertain"],
          recent: [
            { id: "fixture", job: "knowledge:fixture", state: "uncertain", attempts: 2, created: now, observed: null },
          ],
        },
        ownership: {
          available: true,
          stale,
          sampledAt: now,
          phase: "qwen-ready",
          owner: null,
          generation: 167,
          uncertain: false,
          activeRequests: 0,
          primary: "qwen",
        },
      },
    },
  }),
)
try {
  await page.goto(base + "/catalogue")
  const catalogue = page.getByTestId("skill-catalogue-screen")
  await expect(catalogue.locator("article")).toHaveCount(2)
  await catalogue.getByRole("textbox").fill("graphic novel")
  await catalogue.getByRole("button", { name: "Search", exact: true }).click()
  await expect(catalogue.locator("article")).toHaveCount(1)
  await expect(catalogue.locator("article")).toContainText("persistent illustration notes")
  await page.screenshot({ path: process.env.WATOOM_TEST_EVIDENCE + "/catalogue-ui.png" })
  await page.goto(base + "/memory")
  const memory = page.getByTestId("memory-health-panel")
  await expect(memory).toContainText("knowledge:fixture")
  await expect(memory).toContainText("qwen-ready")
  await page.screenshot({ path: process.env.WATOOM_TEST_EVIDENCE + "/memory-ui.png" })
  // A background refresh must not remount the page and reset the reader's scroll position.
  await page.setViewportSize({ width: 1440, height: 500 })
  const scrollTop = () =>
    page.evaluate(() => {
      const scroller = [...document.querySelectorAll<HTMLElement>("*")].find(
        (el) => el.scrollHeight > el.clientHeight + 50 && /(auto|scroll)/.test(getComputedStyle(el).overflowY),
      )
      if (!scroller) throw Error("memory page does not scroll at this size")
      scroller.dataset.scrollProbe = "true"
      return scroller.scrollTop
    })
  await scrollTop()
  await page.evaluate(() => document.querySelector<HTMLElement>("[data-scroll-probe]")?.scrollTo(0, 400))
  const before = await scrollTop()
  await page.waitForTimeout(6000)
  if ((await scrollTop()) !== before) throw Error("memory refresh reset the scroll position")
  await page.setViewportSize({ width: 1440, height: 1200 })
  stale = true
  await memory.getByRole("button", { name: "Refresh", exact: true }).click()
  await expect(memory).not.toContainText("qwen-ready")
  await expect(memory).toContainText("stale")
  if (errors.length) throw Error(errors.join("\n"))
  console.log("UI_FIXTURE PASS catalogue search, descriptions, dependencies, memory receipt, ownership freshness, scroll kept on refresh")
} catch (e) {
  if (await page.getByRole("textbox", { name: "Error Details" }).count())
    errors.push(await page.getByRole("textbox", { name: "Error Details" }).inputValue())
  await fs.writeFile(
    process.env.WATOOM_TEST_EVIDENCE + "/ui-failure.txt",
    String(e) + "\n" + errors.join("\n") + "\n" + (await page.locator("body").innerText()),
  )
  throw e
} finally {
  await browser.close()
}
