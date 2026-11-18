import { lazy, onCleanup, Suspense } from "solid-js"
import { Command, SettingsPage, Style, TitlebarItem, type Plugin } from "@opencode/plugin/gui"
import { onIdle } from "@opencode/plugin/gui/builtin"
import type definition from "./index"
import promptBuilderCss from "./prompt-builder/prompt-builder.css?inline"

/** Settings tab ids of the WatooM pages. The app redirects its old /memory, /catalogue, /skills and /prompt-builder URLs to these tabs. */
const MEMORY_PAGE = "watoom-memory"

const CATALOGUE_PAGE = "watoom-catalogue"

const SKILLS_PAGE = "watoom-skills"

const PROMPT_BUILDER_PAGE = "watoom-prompt-builder"

const setup: Plugin.Setup<typeof definition> = (ctx) => {
  const layout = ctx.layout
  const MemoryPage = lazy(() => import("./memory-page"))
  const CataloguePage = lazy(() => import("./catalogue-page"))
  const SkillsPage = lazy(() => import("./skills-page"))
  const PromptBuilderPage = lazy(() => import("./prompt-builder-page"))
  onCleanup(
    onIdle(() => {
      void MemoryPage.preload()
      void CataloguePage.preload()
      void SkillsPage.preload()
      void PromptBuilderPage.preload()
    }),
  )

  ctx.add(SettingsPage, {
    id: MEMORY_PAGE,
    icon: "brain",
    get title() {
      return ctx.t("memory.tab")
    },
    get entries() {
      return [{ id: MEMORY_PAGE, title: ctx.t("memory.title"), keywords: ctx.t("memory.keywords") }]
    },
    render: () => (
      <Suspense>
        <MemoryPage />
      </Suspense>
    ),
  })

  ctx.add(Command, () => ({
    id: "memory",
    title: ctx.t("memory.command"),
    group: ctx.t("group"),
    run: () => layout.settings(MEMORY_PAGE),
  }))

  ctx.add(SettingsPage, {
    id: CATALOGUE_PAGE,
    icon: "archive",
    get title() {
      return ctx.t("catalogue.tab")
    },
    get entries() {
      return [{ id: CATALOGUE_PAGE, title: ctx.t("catalogue.title"), keywords: ctx.t("catalogue.keywords") }]
    },
    render: () => (
      <Suspense>
        <CataloguePage />
      </Suspense>
    ),
  })

  ctx.add(Command, () => ({
    id: "catalogue",
    title: ctx.t("catalogue.command"),
    group: ctx.t("group"),
    run: () => layout.settings(CATALOGUE_PAGE),
  }))
  ctx.add(SettingsPage, {
    id: SKILLS_PAGE,
    icon: "post-skill",
    get title() {
      return ctx.t("skills.tab")
    },
    get entries() {
      return [{ id: SKILLS_PAGE, title: ctx.t("skills.manager.title"), keywords: ctx.t("skills.keywords") }]
    },
    render: () => (
      <Suspense>
        <SkillsPage />
      </Suspense>
    ),
  })

  ctx.add(Command, () => ({
    id: "skills",
    title: ctx.t("skills.command"),
    group: ctx.t("group"),
    run: () => layout.settings(SKILLS_PAGE),
  }))
  ctx.add(Style, promptBuilderCss)

  ctx.add(SettingsPage, {
    id: PROMPT_BUILDER_PAGE,
    icon: "edit",
    get title() {
      return ctx.t("promptBuilder.tab")
    },
    get entries() {
      return [
        { id: PROMPT_BUILDER_PAGE, title: ctx.t("promptBuilder.title"), keywords: ctx.t("promptBuilder.keywords") },
      ]
    },
    render: () => (
      <Suspense>
        <PromptBuilderPage />
      </Suspense>
    ),
  })

  ctx.add(Command, () => ({
    id: "prompt-builder",
    title: ctx.t("promptBuilder.command"),
    group: ctx.t("group"),
    run: () => layout.settings(PROMPT_BUILDER_PAGE),
  }))
  // Quick access in the titlebar to the two pages used while working; Memory and Catalogue live in Settings and the
  // command palette.
  ctx.add(TitlebarItem, {
    id: "skills",
    get label() {
      return ctx.t("skills.tab")
    },
    icon: "post-skill",
    run: () => layout.settings(SKILLS_PAGE),
  })

  ctx.add(TitlebarItem, {
    id: "prompt-builder",
    get label() {
      return ctx.t("promptBuilder.tab")
    },
    icon: "edit",
    run: () => layout.settings(PROMPT_BUILDER_PAGE),
  })
}

export default setup
