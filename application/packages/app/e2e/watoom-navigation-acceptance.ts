import { chromium, expect } from "@playwright/test"
import { openPaletteWorkspace } from "./utils/command-palette"

const base = process.env.PLAYWRIGHT_BASE_URL!

if (!base || !process.env.WATOOM_TEST_EVIDENCE) throw Error("Set isolated fixture URL and evidence directory")

const browser = await chromium.launch({
  executablePath: "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-gpu"],
})

const context = await browser.newContext({
  baseURL: base,
  viewport: { width: 1440, height: 900 },
  serviceWorkers: "block",
})

const page = await context.newPage()

const errors: string[] = []

page.on("pageerror", (e) => errors.push(e.message))

const home = async () => {
  await page.goto("/")
  await expect(page.getByRole("button", { name: "Skills", exact: true })).toBeVisible({ timeout: 30000 })
}

try {
  await openPaletteWorkspace(page, true)
  // The pages' own data is covered by their acceptance tests; answer it here so navigation is what this checks.
  await page.route("**/api/config/profiles", (route) =>
    route.fulfill({
      json: {
        profiles: [],
        capabilities: [],
        available: [],
        selected: [],
        components: [],
        disabled: [],
        transaction: "",
        statuses: [],
      },
    }),
  )

  await page.route("**/api/skill/catalog?*", (route) =>
    route.fulfill({
      json: {
        location: { directory: "/" },
        data: { enabled: true, discovered: 0, validated: 0, approved: 0, matched: 0, offset: 0, rows: [] },
      },
    }),
  )
  await home()
  // The WatooM pages are no longer sidebar or titlebar links of the app itself.
  await expect(page.locator('[data-action$="sidebar-navigation"], [data-action="skills-navigation"]')).toHaveCount(0)
  await page.screenshot({ path: process.env.WATOOM_TEST_EVIDENCE + "/titlebar-ui.png" })

  // Titlebar pills from the watoom plugin open their settings pages.
  await page.getByRole("button", { name: "Skills", exact: true }).click()
  await expect(page).toHaveURL(/\/settings\?tab=watoom-skills$/)
  await expect(page.getByTestId("skills-screen")).toBeVisible()
  await home()
  await page.getByRole("button", { name: "Prompt builder", exact: true }).click()
  await expect(page).toHaveURL(/\/settings\?tab=watoom-prompt-builder$/)
  await expect(page.getByTestId("prompt-builder-screen")).toBeVisible()

  // Palette commands open every page, Memory and Catalogue included.
  for (const [command, tab, id] of [
    ["Open memory health", "watoom-memory", "memory-health-panel"],
    ["Open skills and pipelines catalogue", "watoom-catalogue", "skill-catalogue-screen"],
    ["Open skills manager", "watoom-skills", "skills-screen"],
    ["Open prompt builder", "watoom-prompt-builder", "prompt-builder-screen"],
  ] as const) {
    await home()
    await page.keyboard.press("ControlOrMeta+K")
    const dialog = page.getByRole("dialog")
    await dialog.getByRole("combobox").fill(command)
    await dialog.getByRole("option", { name: new RegExp("^" + command) }).click()
    await expect(page).toHaveURL(new RegExp("/settings\\?tab=" + tab + "$"))
    await expect(page.getByTestId(id)).toBeVisible()
  }

  // Old URLs keep working.
  for (const [path, tab] of [
    ["/skills", "watoom-skills"],
    ["/prompt-builder", "watoom-prompt-builder"],
    ["/catalogue", "watoom-catalogue"],
    ["/memory", "watoom-memory"],
  ] as const) {
    await page.goto(path)
    await expect(page).toHaveURL(new RegExp("/settings\\?tab=" + tab + "$"))
  }

  if (errors.length) throw Error(errors.join("\n"))

  console.log("UI_FIXTURE PASS titlebar pills, palette commands, no app links, old URLs redirect")
} finally {
  await browser.close()
}
