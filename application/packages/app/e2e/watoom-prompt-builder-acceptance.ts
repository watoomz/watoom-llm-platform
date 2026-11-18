import { chromium, expect } from "@playwright/test"
import { mockOpenCodeServer } from "./utils/mock-server"

const base = process.env.PLAYWRIGHT_BASE_URL!

if (!base || !process.env.WATOOM_TEST_EVIDENCE) throw Error("Set isolated fixture URL and evidence directory")

const browser = await chromium.launch({
  executablePath: "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-gpu"],
})

const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: "block" })

const page = await context.newPage()

const errors: string[] = []

page.on("pageerror", (e) => errors.push(e.message))

const location = { directory: "/tmp/prompt-fixture" }

await mockOpenCodeServer(page, {
  directory: location.directory,
  project: {
    id: "proj_prompt",
    canonical: location.directory,
    name: "Prompt fixture",
    time: { created: 1, updated: 1 },
    sandboxes: [],
  },
  provider: { all: [], connected: [], default: {} },
  sessions: [],
  pageMessages: () => ({ items: [] }),
})

const block = (value: { version: number; kind: string }, guidance = "") =>
  "---\nname: fixture\n---\n# Fixture\n" + guidance + "\n```prompt-builder\n" + JSON.stringify(value) + "\n```\n"

const skills = [
  {
    name: "watoom-prompt-creator",
    description: "Prompt creator",
    location: "/skills/watoom-prompt-creator/SKILL.md",
    content: block({ version: 1, kind: "creator", instructions: ["Preserve the user's dimensions."] }),
  },
  {
    name: "watoom-prompt-blender-builder",
    description: "Blender prompting",
    location: "/skills/watoom-prompt-blender-builder/SKILL.md",
    content: block(
      {
        version: 1,
        kind: "pipeline",
        id: "blender-builder",
        title: "Blender asset",
        category: "3D",
        availability: "available",
        keywords: ["bench", "blender"],
        fields: [{ id: "dimensions", label: "Dimensions", help: "Width × depth × height", required: true }],
      },
      "Keep preview floors out of runtime source.",
    ),
  },
]

// Skill lists answer with real-network latency.
await page.route(
  (url) => url.pathname === "/api/skill",
  async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 400))
    await route.fulfill({ json: { location, data: skills } })
  },
)

try {
  await page.goto(base + "/prompt-builder")
  await expect(page).toHaveURL(/\/settings\?tab=watoom-prompt-builder$/)
  const builder = page.getByTestId("prompt-builder")
  await expect(builder.getByText("Prompt creation skill: watoom-prompt-creator", { exact: true })).toBeVisible({
    timeout: 30000,
  })
  // The plugin contributes the builder's CSS through Style: the two cards sit side by side.
  const columns = await builder.locator(".prompt-builder-grid").evaluate((el) => getComputedStyle(el).display)

  if (columns !== "grid") throw Error("prompt builder CSS not applied: display " + columns)

  await page.locator("#prompt-request").fill("A wooden park bench for Blender")
  await page.locator("#prompt-pipeline").selectOption("blender-builder")
  await page.getByRole("button", { name: "Prepare questions", exact: true }).click()
  await page.locator("#prompt-field-dimensions").fill("1.8 m × 0.6 m × 0.9 m")
  await page.getByRole("button", { name: "Build prompt", exact: true }).click()
  const output = page.getByTestId("prompt-output")
  await expect(output).toHaveValue(/1\.8 m × 0\.6 m × 0\.9 m/)
  await page.screenshot({ path: process.env.WATOOM_TEST_EVIDENCE + "/prompt-builder-ui.png" })

  if (errors.length) throw Error(errors.join("\n"))

  console.log("UI_FIXTURE PASS prompt builder redirect, CSS, build flow")
} finally {
  await browser.close()
}
