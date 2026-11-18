import { createMemo, createResource, createSignal, Show, Suspense } from "solid-js"
import { usePlugin } from "@opencode/plugin/gui"
import { Select } from "@opencode/ui/select"
import type definition from "./index"
import { createServerChoice } from "./server-choice"
import { SkillCatalogBrowser } from "./skills/catalog"
import { skillProjectOptions } from "./skills/catalog-model"
import { ProfileManager } from "./skills/profiles"
import { settled } from "./settled"

/** Skills manager: capability profiles, then the skill catalogue for a server and optional project directory. */
export default function SkillsPage() {
  const ctx = usePlugin<typeof definition>()
  const server = createServerChoice()
  const [project, setProject] = createSignal<string>()

  const [known] = createResource(server.connected, (ref) => ref.client.project.list())

  const projects = createMemo(() =>
    skillProjectOptions(
      (settled(known) ?? []).map((item) => ({ worktree: item.canonical, name: item.name, sandboxes: item.sandboxes })),
      project(),
      ctx.t("skills.manager.defaultProject"),
    ),
  )

  return (
    <div data-testid="skills-screen">
      <h1 class="settings-tab-title">{ctx.t("skills.manager.title")}</h1>
      <server.Picker />
      <label class="flex gap-2 my-3">
        {ctx.t("skills.manager.project")}
        <Select
          aria-label={ctx.t("skills.manager.project")}
          placeholder={ctx.t("skills.manager.defaultProject")}
          options={projects()}
          current={projects().find((item) => item.directory === (project() ?? ""))}
          value={(item) => item.directory || "__server_default__"}
          label={(item) => item.label}
          onSelect={(item) => item && setProject(item.directory || undefined)}
          valueClass="max-w-xl truncate"
        />
      </label>
      <p class="text-13-regular mb-4">{ctx.t("skills.manager.scopeNotice")}</p>
      {/* A new server starts a fresh browser: its agents, selections and review state belong to that server. */}
      <Show when={server.id()} keyed>
        <div class="flex flex-col gap-8">
          {/* One boundary per section: each shows while the other loads. */}
          <Suspense fallback={<p role="status">{ctx.t("loading")}</p>}>
            <ProfileManager server={server.connected} />
          </Suspense>
          <Suspense fallback={<p role="status">{ctx.t("loading")}</p>}>
            <SkillCatalogBrowser server={server.connected} directory={project()} />
          </Suspense>
        </div>
      </Show>
    </div>
  )
}
