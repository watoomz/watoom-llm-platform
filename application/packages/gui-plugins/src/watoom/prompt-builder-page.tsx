import { createMemo, createResource, createSignal, Show, Suspense } from "solid-js"
import { usePlugin } from "@opencode/plugin/gui"
import { Select } from "@opencode/ui/select"
import type definition from "./index"
import { PromptBuilder } from "./prompt-builder/builder"
import { createServerChoice } from "./server-choice"
import { skillProjectOptions } from "./skills/catalog-model"
import { settled } from "./settled"

/** Prompt builder for a chosen server and optional project directory. */
export default function PromptBuilderPage() {
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
    <div data-testid="prompt-builder-screen">
      <h1 class="settings-tab-title">{ctx.t("promptBuilder.title")}</h1>
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
      <p class="text-13-regular mb-4">{ctx.t("promptBuilder.scopeNotice")}</p>
      {/* A new server or project starts a fresh builder; a background refresh of the skills does not. */}
      <Show when={(server.id() ?? "") + "\n" + (project() ?? "")} keyed>
        {/* Its own boundary: the title and pickers stay up while the prompting skills load. */}
        <Suspense fallback={<p role="status">{ctx.t("loading")}</p>}>
          <PromptBuilder server={server.connected} directory={project()} />
        </Suspense>
      </Show>
    </div>
  )
}
