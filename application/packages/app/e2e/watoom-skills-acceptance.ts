import { chromium, expect } from "@playwright/test"
import { mockOpenCodeServer } from "./utils/mock-server"

const base = process.env.PLAYWRIGHT_BASE_URL!

if (!base || !process.env.WATOOM_TEST_EVIDENCE) throw Error("Set isolated fixture URL and evidence directory")

const browser = await chromium.launch({
  executablePath: "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-gpu"],
})

const context = await browser.newContext({ viewport: { width: 1440, height: 700 }, serviceWorkers: "block" })

const page = await context.newPage()

const errors: string[] = []

page.on("pageerror", (e) => errors.push(e.message))

const mock = await mockOpenCodeServer(page, {
  directory: "/tmp/skills-fixture",
  project: {
    id: "proj_skills",
    canonical: "/tmp/skills-fixture",
    name: "Skills fixture",
    time: { created: 1, updated: 1 },
    sandboxes: [],
  },
  provider: { all: [], connected: [], default: {} },
  sessions: [],
  pageMessages: () => ({ items: [] }),
})
// Enough rows that the page scrolls.

const rows = Array.from({ length: 30 }, (_, index) => ({
  id: "github:fixture/skills:blender-fixture-" + index,
  repo: "fixture/skills",
  path: "skills/blender-fixture-" + index,
  name: "blender-fixture-" + index,
  description: "Fixture skill " + index + " for the skills page acceptance.",
  sha256: "a".repeat(64),
  commit_sha: "b".repeat(40),
  license: "MIT",
  risk: "[]",
  validation: "valid",
  approved: 1,
  bundle_sha: null,
  state: "DISCOVERED",
  classification: "SKILL",
}))

const location = { directory: "/tmp/skills-fixture" }

await page.route("**/api/skill/catalog?*", (route) =>
  route.fulfill({
    json: {
      location,
      data: { enabled: true, discovered: 30, validated: 30, approved: 30, matched: 30, offset: 0, rows },
    },
  }),
)

await page.route("**/api/config/profiles", (route) =>
  route.fulfill({
    json: {
      profiles: [{ id: "minimal", version: "1", extends: [], capabilities: ["core"], skills: [] }],
      capabilities: [],
      available: ["minimal"],
      selected: ["minimal"],
      components: [],
      disabled: [],
      transaction: "",
      statuses: [],
    },
  }),
)
// Answer agent and native skill lists with real-network latency, so a refetch that unmounts the page shows.

await page.route(
  (url) => url.pathname === "/api/agent" || url.pathname === "/api/skill",
  async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 400))
    await route.fallback()
  },
)

try {
  await page.goto(base + "/skills")
  await expect(page).toHaveURL(/\/settings\?tab=watoom-skills$/)
  const screen = page.getByTestId("skills-screen")
  await expect(screen.getByRole("heading", { name: "Skills", exact: true })).toBeVisible({ timeout: 30000 })
  await expect(screen.getByTestId("skill-catalog-counts")).toBeVisible()
  await expect(screen.locator("article[data-skill-id]")).toHaveCount(30)
  await expect(screen.getByLabel("Project directory")).toBeVisible()
  await expect(screen.getByLabel("Agent defaults")).toBeVisible()
  await expect(screen.getByRole("checkbox", { name: "minimal" })).toBeChecked()
  await page.screenshot({ path: process.env.WATOOM_TEST_EVIDENCE + "/skills-ui.png" })
  // A server event refetches agents and native skills; the page must stay mounted at the reader's position.

  const scrollTop = () =>
    page.evaluate(() => {
      const scroller =
        document.querySelector<HTMLElement>("[data-scroll-probe]") ??
        [...document.querySelectorAll<HTMLElement>("*")]
          .filter(
            (el) => el.scrollHeight > el.clientHeight + 50 && /(auto|scroll)/.test(getComputedStyle(el).overflowY),
          )
          .toSorted((x, y) => y.scrollHeight - x.scrollHeight)[0]

      if (!scroller) throw Error("skills page does not scroll at this size")
      scroller.dataset.scrollProbe = "true"

      return scroller.scrollTop
    })

  await scrollTop()
  await page.evaluate(() => document.querySelector<HTMLElement>("[data-scroll-probe]")?.scrollTo(0, 800))
  const before = await scrollTop()

  if (before < 400) throw Error("could not scroll the skills page")
  await mock.push([
    { id: "evt_agent", created: Date.now(), type: "agent.updated", location, data: {} },
    { id: "evt_skill", created: Date.now(), type: "skill.updated", location, data: {} },
    { id: "evt_config", created: Date.now(), type: "config.updated", location, data: {} },
  ])
  await page.waitForTimeout(2000)

  if ((await scrollTop()) !== before) throw Error("a skills refresh reset the scroll position")
  await page.getByRole("tab", { name: "Installed", exact: true }).click()
  await expect(screen.getByRole("heading", { name: "Native skills", exact: true })).toBeVisible()

  // A failing server answer shows the page's own alerts; the rest of the page stays up.
  await page.route("**/api/config/profiles", (route) => route.fulfill({ status: 500, json: { message: "fixture" } }))
  await page.route("**/api/skill/catalog?*", (route) => route.fulfill({ status: 500, json: { message: "fixture" } }))
  await page.reload()
  await expect(screen.getByRole("heading", { name: "Skills", exact: true })).toBeVisible({ timeout: 30000 })
  await expect(screen.getByText("Profile management failed.", { exact: false })).toBeVisible()
  await expect(screen.getByText("The skill library could not be read.", { exact: false })).toBeVisible()
  await expect(screen.getByLabel("Project directory")).toBeVisible()

  if (errors.length) throw Error(errors.join("\n"))
  console.log(
    "UI_FIXTURE PASS skills redirect, profiles, catalogue rows, pickers, views, scroll kept on refresh, alerts on failure",
  )
} finally {
  await browser.close()
}
