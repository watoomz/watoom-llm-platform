import { createMemo, createResource, For, Show } from "solid-js"
import { createStore } from "solid-js/store"
import { usePlugin, type ServerRef } from "@opencode/plugin/gui"
import { Button } from "@opencode/ui/button"
import type definition from "../index"
import { composePrompt, missingFields, loadPromptSkills, suggestPipeline, defaultAnswers } from "./model"
import { settled } from "../settled"

type BuilderState = {
  request: string
  selected: string
  prepared: boolean
  /** Field answers by field id. */
  answers: { [field: string]: string }
  project: string
  output: string
  /** An i18n key of the error to show, or empty. */
  error: string
  copied: boolean
}

/**
 * Builds a job prompt from the server's prompting skills. The page mounts one builder per server and project, so a
 * background refresh of the skills keeps the request, answers and finished prompt.
 */
export function PromptBuilder(props: { server: () => ServerRef | undefined; directory?: string }) {
  const ctx = usePlugin<typeof definition>()

  const [state, setState] = createStore<BuilderState>({
    request: "",
    selected: "",
    prepared: false,
    answers: {},
    project: props.directory ?? "",
    output: "",
    error: "",
    copied: false,
  })

  const [catalog, { refetch }] = createResource(props.server, async (server) =>
    loadPromptSkills(async () => (await server.client.skill.list({ location: { directory: props.directory } })).data),
  )

  const available = createMemo(() => settled(catalog))
  const suggested = createMemo(() => suggestPipeline(state.request, available()?.recipes ?? []))
  const recipe = createMemo(() => available()?.recipes.find((x) => x.id === (state.selected || suggested())))
  const missing = createMemo(() => (recipe() ? missingFields(recipe()!, state.answers) : []))
  const invalidate = () => setState({ output: "", error: "", copied: false })

  const prepare = () => {
    invalidate()

    if (!state.request.trim() || !recipe()) {
      setState("error", "promptBuilder.choose")

      return
    }

    setState({ selected: recipe()!.id, prepared: true, answers: defaultAnswers(recipe()!, state.request) })
  }

  const reveal = (id: string) =>
    queueMicrotask(() => {
      const field = document.getElementById(id)
      field?.scrollIntoView({ block: "center" })
      field?.focus({ preventScroll: true })
    })

  const build = () => {
    invalidate()

    if (!recipe() || !settled(catalog)) {
      setState("error", "promptBuilder.choose")

      return
    }

    if (missing().length) {
      setState("error", "promptBuilder.missing")
      reveal("prompt-field-" + missing()[0].id)

      return
    }

    try {
      setState(
        "output",
        composePrompt(settled(catalog)!.creator, recipe()!, state.request, state.answers, state.project.trim()),
      )
      reveal("prompt-output")
    } catch {
      setState("error", "promptBuilder.invalidProject")
      reveal("prompt-project")
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(state.output)
      setState("copied", true)
    } catch {
      document.querySelector<HTMLTextAreaElement>("[data-testid=prompt-output]")?.select()
      setState("error", "promptBuilder.copyFallback")
    }
  }

  return (
    <div class="prompt-builder" data-testid="prompt-builder">
      <p class="text-13-regular text-v2-text-text-muted">{ctx.t("promptBuilder.description")}</p>
      <Show when={catalog.error}>
        <div role="alert">
          <p>{ctx.t("promptBuilder.loadError")}</p>
          <Button onClick={() => void refetch()}>{ctx.t("promptBuilder.retry")}</Button>
        </div>
      </Show>
      <Show when={catalog.loading}>
        <p role="status">{ctx.t("loading")}</p>
      </Show>
      <Show when={available()}>
        {(data) => (
          <>
            <div class="prompt-builder-source text-12-regular">
              {ctx.t("promptBuilder.source", { skill: data().creator.skill })}
            </div>
            <div class="prompt-builder-grid">
              <div class="prompt-builder-card">
                <h2 class="text-16-medium">{ctx.t("promptBuilder.describe")}</h2>
                <label for="prompt-request">{ctx.t("promptBuilder.request")}</label>
                <textarea
                  id="prompt-request"
                  rows={4}
                  maxLength={12000}
                  value={state.request}
                  placeholder={ctx.t("promptBuilder.requestPlaceholder")}
                  onInput={(event) => {
                    setState({ request: event.currentTarget.value, prepared: false })
                    invalidate()
                  }}
                />
                <label for="prompt-pipeline">{ctx.t("promptBuilder.pipeline")}</label>
                <select
                  id="prompt-pipeline"
                  value={state.selected || suggested()}
                  onChange={(event) => {
                    setState({ selected: event.currentTarget.value, prepared: false, answers: {} })
                    invalidate()
                  }}
                >
                  <option value="">{ctx.t("promptBuilder.selectPipeline")}</option>
                  <For each={data().recipes}>
                    {(item) => (
                      <option value={item.id}>
                        {item.category} · {item.title}
                      </option>
                    )}
                  </For>
                </select>
                <Show when={recipe()}>
                  {(item) => (
                    <p class="text-12-regular text-v2-text-text-muted" data-testid="pipeline-availability">
                      {item().availability}
                    </p>
                  )}
                </Show>
                <Button disabled={!state.request.trim() || !recipe()} onClick={prepare}>
                  {ctx.t("promptBuilder.questions")}
                </Button>
                <Show when={state.prepared && recipe()}>
                  {(item) => (
                    <div class="prompt-builder-questions">
                      <h2 class="text-16-medium">{ctx.t("promptBuilder.details")}</h2>
                      <p class="text-12-regular text-v2-text-text-muted">{ctx.t("promptBuilder.detailsHelp")}</p>
                      <For each={item().fields}>
                        {(field) => (
                          <div>
                            <label for={"prompt-field-" + field.id}>
                              {field.label}{" "}
                              <span class="text-12-regular text-v2-text-text-muted">
                                {ctx.t(field.required ? "promptBuilder.required" : "promptBuilder.optional")}
                              </span>
                            </label>
                            <textarea
                              id={"prompt-field-" + field.id}
                              rows={2}
                              maxLength={4000}
                              required={field.required}
                              aria-invalid={
                                state.error === "promptBuilder.missing" &&
                                missing().some((item) => item.id === field.id)
                              }
                              value={state.answers[field.id] ?? ""}
                              aria-describedby={"prompt-help-" + field.id}
                              onInput={(event) => {
                                setState("answers", field.id, event.currentTarget.value)
                                invalidate()
                              }}
                            />
                            <p id={"prompt-help-" + field.id} class="text-12-regular text-v2-text-text-muted">
                              {field.help}
                            </p>
                          </div>
                        )}
                      </For>
                      <label for="prompt-project">{ctx.t("promptBuilder.project")}</label>
                      <input
                        id="prompt-project"
                        aria-invalid={state.error === "promptBuilder.invalidProject"}
                        value={state.project}
                        placeholder={ctx.t("promptBuilder.projectPlaceholder")}
                        onInput={(event) => {
                          setState("project", event.currentTarget.value)
                          invalidate()
                        }}
                      />
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setState("answers", defaultAnswers(item(), state.request))
                          invalidate()
                        }}
                      >
                        {ctx.t("promptBuilder.resetDefaults")}
                      </Button>
                      <Button onClick={build}>{ctx.t("promptBuilder.build")}</Button>
                      <Show when={missing().length}>
                        <p class="text-12-regular" role="status">
                          {ctx.t("promptBuilder.complete")}{" "}
                          {missing()
                            .map((x) => x.label)
                            .join("; ")}
                        </p>
                      </Show>
                    </div>
                  )}
                </Show>
                <Show when={state.error && state.error !== "promptBuilder.copyFallback"}>
                  <p role="alert">{ctx.t(state.error)}</p>
                </Show>
              </div>
              <div class="prompt-builder-card prompt-builder-preview">
                <h2 class="text-16-medium">{ctx.t("promptBuilder.preview")}</h2>
                <p class="text-12-regular text-v2-text-text-muted">{ctx.t("promptBuilder.previewHelp")}</p>
                <textarea
                  id="prompt-output"
                  data-testid="prompt-output"
                  aria-label={ctx.t("promptBuilder.preview")}
                  rows={20}
                  value={state.output}
                  placeholder={ctx.t("promptBuilder.empty")}
                  onInput={(event) => setState({ output: event.currentTarget.value, copied: false })}
                />
                <Show when={state.output.trim()}>
                  <p role="status">{ctx.t("promptBuilder.ready")}</p>
                </Show>
                <Button disabled={!state.output.trim()} onClick={copy}>
                  {ctx.t(state.copied ? "promptBuilder.copied" : "promptBuilder.copy")}
                </Button>
                <Show when={state.copied}>
                  <p role="status">{ctx.t("promptBuilder.paste")}</p>
                </Show>
                <Show when={recipe()}>
                  {(item) => (
                    <details>
                      <summary>{ctx.t("promptBuilder.skill")}</summary>
                      <p class="text-12-regular">{item().skill}</p>
                      <p class="text-13-regular whitespace-pre-wrap">{item().guidance}</p>
                    </details>
                  )}
                </Show>
              </div>
            </div>
          </>
        )}
      </Show>
      <Show when={state.error === "promptBuilder.copyFallback"}>
        <p role="alert">{ctx.t("promptBuilder.copyFallback")}</p>
      </Show>
    </div>
  )
}
