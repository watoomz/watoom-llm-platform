import { createResource, For, Show } from "solid-js"
import { createStore } from "solid-js/store"
import type { SkillIndexOutput } from "@opencode/client/promise"
import { usePlugin } from "@opencode/plugin/gui"
import { Button } from "@opencode/ui/button"
import type definition from "./index"
import { createServerChoice } from "./server-choice"
import { settled } from "./settled"

type Catalogue = SkillIndexOutput["data"]

/** Search the installed skills and pipelines by task; read-only. */
export default function CataloguePage() {
  const ctx = usePlugin<typeof definition>()
  const server = createServerChoice()
  const [state, setState] = createStore({ draft: "", query: "" })

  const [catalogue, { refetch }] = createResource(
    () => {
      const ref = server.connected()

      return ref ? { ref, query: state.query } : undefined
    },
    async (input): Promise<Catalogue> => (await input.ref.client.skill.index({ query: input.query })).data,
  )

  return (
    <div data-testid="skill-catalogue-screen">
      <h1 class="settings-tab-title">{ctx.t("catalogue.title")}</h1>
      <server.Picker />
      <p>{ctx.t("catalogue.explanation")}</p>
      <form
        class="flex gap-2 my-4"
        onSubmit={(event) => {
          event.preventDefault()
          setState("query", state.draft)
        }}
      >
        <input
          class="w-full border rounded px-3 py-2"
          aria-label={ctx.t("catalogue.search")}
          placeholder={ctx.t("catalogue.placeholder")}
          value={state.draft}
          onInput={(event) => setState("draft", event.currentTarget.value)}
        />
        <Button type="submit">{ctx.t("catalogue.search")}</Button>
        <Button type="button" onClick={() => void refetch()}>
          {ctx.t("refresh")}
        </Button>
      </form>
      <Show when={catalogue.error}>
        <p role="alert">{ctx.t("catalogue.unavailable")}</p>
      </Show>
      <Show when={settled(catalogue)} keyed>
        {(data) => (
          <>
            <p>{ctx.plural("catalogue.total", data.catalogueSize)}</p>
            <Show when={!data.entries.length}>
              <p>{ctx.t("catalogue.empty")}</p>
            </Show>
            <For each={data.entries}>
              {(entry) => (
                <article class="my-3 rounded border p-3" data-skill-id={entry.id}>
                  <h2 class="text-16-medium">{entry.name}</h2>
                  <code>{entry.id}</code>
                  <p class="my-2">{entry.description}</p>
                  <dl class="grid grid-cols-2 gap-2">
                    <dt>{ctx.t("catalogue.kind")}</dt>
                    <dd>{ctx.t(entry.kind === "pipeline" ? "catalogue.pipeline" : "catalogue.skill")}</dd>
                    <dt>{ctx.t("catalogue.availability")}</dt>
                    <dd>{entry.availability}</dd>
                    <dt>{ctx.t("catalogue.requires")}</dt>
                    <dd>{entry.requires.join(", ") || ctx.t("catalogue.noRequirements")}</dd>
                    <Show when={!entry.autoinvoke}>
                      <dt>{ctx.t("catalogue.invocation")}</dt>
                      <dd>{ctx.t("catalogue.explicitOnly")}</dd>
                    </Show>
                  </dl>
                </article>
              )}
            </For>
          </>
        )}
      </Show>
    </div>
  )
}
