import { createStore } from "solid-js/store"
import { createMemo, createResource, For, Show, onCleanup } from "solid-js"
import { createKeyed, usePlugin, type ServerRef } from "@opencode/plugin/gui"
import { Button } from "@opencode/ui/button"
import { Checkbox } from "@opencode/ui/checkbox"
import { Select } from "@opencode/ui/select"
import type { SkillAdministration } from "@opencode/schema/skill-administration"
import type definition from "../index"
import { sourceURL, skillPresentation, skillSearchQuery, groupSkills } from "./catalog-model"
import { settled } from "../settled"

const views = ["installed", "available", "pending", "disabled"] as const

type CatalogState = {
  query: string
  draft: string
  offset: number
  agent: string
  review: string
  busy: boolean
  error: string
  receipt: string
  view: (typeof views)[number]
  sort: "name" | "source"
  elevated: boolean
}

/** Search, review, administer and assign catalogue skills on one server, optionally scoped to a project directory. */
export function SkillCatalogBrowser(props: { server: () => ServerRef | undefined; directory?: string }) {
  const ctx = usePlugin<typeof definition>()

  const [state, setState] = createStore<CatalogState>({
    query: "",
    draft: "",
    offset: 0,
    agent: "",
    review: "",
    busy: false,
    error: "",
    receipt: "",
    view: "available",
    sort: "name",
    elevated: false,
  })

  const location = () => (props.directory ? { directory: props.directory } : undefined)
  // Read the live ref each time: a restarted server gets a new client under the same id.
  const client = () => props.server()?.client

  const scope = () => {
    const server = props.server()

    return server ? { server, directory: props.directory } : undefined
  }

  const [agents, { refetch: refreshAgents }] = createResource(scope, (input) =>
    input.server.client.agent.list({ location: location() }).then((result) => result.data),
  )

  const [native, { refetch: refreshNative }] = createResource(scope, (input) =>
    input.server.client.skill.list({ location: location() }).then((result) => result.data),
  )

  // Native registries populate asynchronously and publish updates after a cold start.
  // Follow the server's event bus instead of caching an empty bootstrap.
  createKeyed(props.server, (server) => {
    const here = (event: { location?: { directory?: string } }) =>
      !props.directory || !event.location || event.location.directory === props.directory

    const stops = [
      server.data.on("agent.updated", (event) => {
        if (here(event)) void refreshAgents()
      }),
      server.data.on("skill.updated", (event) => {
        if (here(event)) void refreshNative()
      }),
      server.data.on("config.updated", (event) => {
        if (!here(event)) return

        void refreshAgents()
        void refreshNative()
      }),
    ]

    onCleanup(() => stops.forEach((stop) => stop()))
  })

  const [selected, { refetch: refreshSelections }] = createResource(
    () => {
      const server = props.server()

      return server && state.agent
        ? { server, input: { agent: state.agent, target: "agent" as const, location: location() } }
        : undefined
    },
    (input) => input.server.client.skill.catalog.selection.list(input.input).then((result) => result.data),
  )

  const [page, { refetch }] = createResource(
    () => {
      const server = props.server()

      return server
        ? {
            server,
            query: skillSearchQuery(state.query),
            approvedOnly: false,
            validOnly: true,
            offset: state.offset,
            limit: 32,
            location: location(),
            view: state.view,
            sort: state.sort,
          }
        : undefined
    },
    ({ server, ...input }) => server.client.skill.catalog.list(input).then((result) => result.data),
  )

  const [detail, { refetch: refreshDetail }] = createResource(
    () => {
      const server = props.server()

      return server && state.review ? { server, input: { skillID: state.review, location: location() } } : undefined
    },
    (input) => input.server.client.skill.catalog.detail(input.input).then((result) => result.data),
  )

  const run = async (action: () => Promise<void>) => {
    if (state.busy) return
    setState({ busy: true, error: "", receipt: "" })

    try {
      await action()
      await Promise.all([refetch(), refreshSelections(), refreshDetail()])
    } catch (error) {
      setState("error", error instanceof Error ? error.message : String(error))
    } finally {
      setState("busy", false)
    }
  }

  const changeSelection = (skillID: string, remove: boolean) =>
    run(async () => {
      const api = client()

      if (!api) return

      const input = { agent: state.agent, target: "agent" as const, skillID, location: location() }

      if (remove) await api.skill.catalog.selection.remove(input)
      else await api.skill.catalog.selection.select(input)
    })

  const administer = (
    action: SkillAdministration.Request["action"],
    version?: { sha256: string; revision: string; bundleSha256: string; tools?: readonly string[] },
  ) =>
    run(async () => {
      const data = settled(detail)
      const api = client()

      if (!data || !api) return

      const pin =
        version ?? (["enable", "disable", "revoke"].includes(action) ? (data.activeVersion ?? undefined) : undefined)

      const result = await api.skill.catalog.admin({
        skillID: data.entry.id,
        action,
        sha256: pin?.sha256 ?? data.entry.sha256,
        revision: pin?.revision ?? data.entry.commit_sha,
        bundleSha256: pin?.bundleSha256 ?? data.bundleSha256,
        permissions: [{ action: "skill", resource: data.entry.id, effect: "allow" }],
        tools: version?.tools ?? (["enable", "disable", "revoke"].includes(action) ? data.activeTools : data.tools),
        riskApproved: state.elevated,
        location: location(),
      })

      setState("receipt", result.data.state)
    })

  const next = createMemo<SkillAdministration.Request["action"]>(
    () =>
      (
        ({
          DISCOVERED: "stage",
          STAGED: "review",
          REVIEWED: "validate",
          VALIDATED: "approve",
          APPROVED: "install",
          UPDATED: "install",
          INSTALLED: "enable",
          DISABLED: "enable",
          ENABLED: "disable",
          REJECTED: "stage",
          REVOKED: "stage",
        }) as const
      )[settled(detail)?.entry.state ?? "DISCOVERED"] ?? "stage",
  )

  const reviewOnly = createMemo(() => {
    const data = settled(detail)

    return (
      data?.entry.validation === "valid" &&
      !data.valid &&
      data.risks.includes("executable-components-require-separate-integration") &&
      data.risks.every((risk) =>
        ["executable-components-require-separate-integration", "elevated-operations"].includes(risk),
      )
    )
  })

  return (
    <section class="settings-section select-text" aria-label={ctx.t("skills.manager.title")}>
      <div class="flex flex-wrap gap-2" role="tablist" aria-label={ctx.t("skills.manager.views")}>
        <For each={views}>
          {(view) => (
            <Button role="tab" aria-selected={state.view === view} onClick={() => setState({ view, offset: 0 })}>
              {ctx.t("skills.manager." + view)}
            </Button>
          )}
        </For>
      </div>
      <form
        class="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          setState({ query: state.draft, offset: 0 })
        }}
      >
        <input
          class="border rounded p-2 flex-1"
          aria-label={ctx.t("settings.skills.catalog.search")}
          value={state.draft}
          maxLength={256}
          onInput={(event) => setState("draft", event.currentTarget.value)}
        />
        <Button type="submit">{ctx.t("settings.skills.catalog.searchButton")}</Button>
        <Select
          aria-label={ctx.t("skills.manager.sort")}
          options={["name", "source"] as const}
          current={state.sort}
          label={(value) => ctx.t(value === "name" ? "skills.manager.name" : "settings.skills.catalog.source")}
          onSelect={(value) => value && setState({ sort: value, offset: 0 })}
        />
        <Button type="button" onClick={() => refetch()}>
          {ctx.t("settings.skills.catalog.refresh")}
        </Button>
      </form>
      <Show when={page.error || detail.error || selected.error || state.error}>
        <p role="alert">{state.error || ctx.t("settings.skills.catalog.unavailable")}</p>
      </Show>
      <Show when={page.loading || detail.loading}>
        <p role="status">{ctx.t("settings.skills.catalog.loading")}</p>
      </Show>
      <Show when={state.receipt}>
        <p role="status">{state.receipt}</p>
      </Show>
      <Show when={state.view === "installed"}>
        <h2>{ctx.t("skills.manager.native")}</h2>
        <For
          each={groupSkills(
            settled(native)?.filter((item) =>
              (item.name + " " + item.description).toLowerCase().includes(state.query.toLowerCase()),
            ) ?? [],
          )}
        >
          {(group) => (
            <details open class="border rounded p-3">
              <summary>
                {ctx.t("skills.group." + group.key)} ({group.entries.length})
              </summary>
              <For each={group.entries}>
                {(skill) => (
                  <details class="border rounded p-3">
                    <summary>{skill.name}</summary>
                    <p>{skill.description}</p>
                    <p>{ctx.t("skills.manager.nativeNotice")}</p>
                    <pre class="whitespace-pre-wrap break-words">{skill.content}</pre>
                  </details>
                )}
              </For>
            </details>
          )}
        </For>
      </Show>
      <Show when={settled(page)?.enabled} fallback={<p>{ctx.t("settings.skills.catalog.disabled")}</p>}>
        <p data-testid="skill-catalog-counts">
          {ctx.t("settings.skills.catalog.counts", {
            discovered: settled(page)?.validated ?? 0,
            validated: settled(page)?.validated ?? 0,
            approved: settled(page)?.approved ?? 0,
          })}
        </p>
        <label class="flex gap-2">
          {ctx.t("settings.skills.catalog.agent")}
          <Select
            aria-label={ctx.t("settings.skills.catalog.agent")}
            options={settled(agents)?.filter((item) => !item.hidden) ?? []}
            current={settled(agents)?.find((item) => item.id === state.agent)}
            value={(item) => item.id}
            label={(item) => item.name}
            placeholder={ctx.t("settings.skills.catalog.chooseAgent")}
            onSelect={(item) => setState("agent", item?.id ?? "")}
          />
        </label>
        <p>{ctx.t("skills.manager.pinNotice")}</p>
        <For each={settled(selected)}>
          {(entry) => (
            <div class="flex gap-2 items-center">
              <span>
                {entry.name ?? entry.id} · {entry.status}
              </span>
              <Button disabled={state.busy} onClick={() => changeSelection(entry.id, true)}>
                {ctx.t("settings.skills.catalog.remove")}
              </Button>
            </div>
          )}
        </For>
        <div class="flex flex-col gap-3" data-testid="skill-catalog-rows">
          <p class="text-11-regular">{ctx.t("skills.group.pageNotice")}</p>
          <For each={groupSkills(settled(page)?.rows ?? [])}>
            {(group) => (
              <details open class="border rounded p-3">
                <summary>
                  {ctx.t("skills.group." + group.key)} ({group.entries.length})
                </summary>
                <For each={group.entries}>
                  {(entry) => (
                    <article class="border rounded p-3 flex flex-col gap-2" data-skill-id={entry.id}>
                      <div class="flex justify-between gap-2">
                        <strong data-testid="skill-display-name">{skillPresentation(entry).title}</strong>
                        <span>
                          {entry.state} · {entry.classification}
                        </span>
                      </div>
                      <p class="text-11-regular font-mono break-all" data-testid="skill-source-name">
                        {entry.name}
                      </p>
                      <p data-testid="skill-display-description">
                        {skillPresentation(entry).description || ctx.t("skills.manager.missingDescription")}
                      </p>
                      <Show when={skillPresentation(entry).english}>
                        <details data-testid="skill-original-description">
                          <summary>{ctx.t("skills.manager.englishSummary")}</summary>
                          <p>{entry.description}</p>
                          <p class="text-11-regular">{skillPresentation(entry).source}</p>
                        </details>
                      </Show>
                      <p class="text-11-regular">
                        {entry.repo} · {entry.license || "UNKNOWN"} · {entry.validation}
                      </p>
                      <div class="flex gap-2">
                        <Button
                          onClick={() =>
                            setState({
                              review: state.review === entry.id ? "" : entry.id,
                              elevated: false,
                              receipt: "",
                              error: "",
                            })
                          }
                        >
                          {ctx.t("settings.skills.catalog.review")}
                        </Button>
                        <Button
                          disabled={
                            entry.approved !== 1 ||
                            !state.agent ||
                            state.busy ||
                            settled(selected)?.some((item) => item.id === entry.id)
                          }
                          onClick={() => changeSelection(entry.id, false)}
                        >
                          {ctx.t("settings.skills.catalog.select")}
                        </Button>
                      </div>
                      <Show when={state.review === entry.id && settled(detail)}>
                        {(data) => (
                          <>
                            <dl class="text-11-regular break-all">
                              <dt>{ctx.t("settings.skills.catalog.source")}</dt>
                              <dd>
                                {entry.repo}/{entry.path}
                              </dd>
                              <dt>{ctx.t("settings.skills.catalog.version")}</dt>
                              <dd>{data().entry.commit_sha}</dd>
                              <dt>{ctx.t("settings.skills.catalog.contentHash")}</dt>
                              <dd>{data().entry.sha256}</dd>
                              <dt>{ctx.t("settings.skills.catalog.bundleHash")}</dt>
                              <dd>{data().bundleSha256}</dd>
                              <dt>{ctx.t("skills.manager.category")}</dt>
                              <dd>{data().categories}</dd>
                              <dt>{ctx.t("skills.manager.dependencies")}</dt>
                              <dd>{data().tools.join(", ") || ctx.t("skills.manager.noneDeclared")}</dd>
                              <dt>{ctx.t("skills.manager.compatibility")}</dt>
                              <dd>
                                {data().compatibility} ·{" "}
                                {data().valid
                                  ? ctx.t("skills.manager.nativeCompatible")
                                  : data().error || ctx.t("skills.manager.blocked")}
                              </dd>
                              <dt>{ctx.t("settings.skills.catalog.risks")}</dt>
                              <dd>{data().risks.join(", ") || ctx.t("skills.manager.reviewRequired")}</dd>
                            </dl>
                            <Show when={sourceURL(data().entry)}>
                              {(url) => (
                                <a
                                  href={url()}
                                  onClick={(event) => {
                                    event.preventDefault()
                                    ctx.system.openExternal(url())
                                  }}
                                >
                                  {ctx.t("settings.skills.catalog.upstream")}
                                </a>
                              )}
                            </Show>
                            <Show when={data().installedInstructions}>
                              <h3>{ctx.t("skills.manager.installedInstructions")}</h3>
                              <p class="break-all">
                                {data().activeVersion?.sha256} · {data().activeVersion?.bundleSha256}
                              </p>
                              <pre
                                data-testid="skill-installed-instructions"
                                class="whitespace-pre-wrap break-words max-h-96 overflow-y-auto border p-3"
                              >
                                {data().installedInstructions}
                              </pre>
                            </Show>
                            <h3>{ctx.t("skills.manager.candidateInstructions")}</h3>
                            <p>{ctx.t("skills.manager.untrusted")}</p>
                            <pre
                              data-testid="skill-instructions"
                              class="whitespace-pre-wrap break-words max-h-96 overflow-y-auto border p-3"
                            >
                              {data().instructions || data().error}
                            </pre>
                            <p class="break-all">{data().files.join(", ")}</p>
                            <Show when={data().risks.length}>
                              <Checkbox checked={state.elevated} onChange={(checked) => setState("elevated", checked)}>
                                {ctx.t("skills.manager.elevated")}
                              </Checkbox>
                            </Show>
                            <Show when={data().risks.includes("bundled-scripts-require-runtime-permission")}>
                              <p role="status">{ctx.t("skills.manager.scriptCompanions")}</p>
                            </Show>
                            <Show when={reviewOnly()}>
                              <p role="status">{ctx.t("skills.manager.integrationRequired")}</p>
                            </Show>
                            <div class="flex flex-wrap gap-2">
                              <Button
                                disabled={
                                  state.busy ||
                                  (!data().valid &&
                                    next() !== "disable" &&
                                    !(reviewOnly() && ["stage", "review"].includes(next()))) ||
                                  (!!data().risks.length && !state.elevated)
                                }
                                onClick={() => administer(next())}
                              >
                                {ctx.t("skills.manager.action." + next())}
                              </Button>
                              <Show when={["ENABLED", "DISABLED", "INSTALLED"].includes(data().entry.state ?? "")}>
                                <Button disabled={state.busy} onClick={() => administer("stage")}>
                                  {ctx.t("skills.manager.action.update")}
                                </Button>
                              </Show>
                              <Button disabled={state.busy} onClick={() => administer("reject")}>
                                {ctx.t("settings.skills.admin.reject")}
                              </Button>
                            </div>
                            <For each={data().versions}>
                              {(version) => (
                                <div class="flex gap-2 items-center break-all">
                                  <span>
                                    {version.revision} · {version.bundleSha256.slice(0, 12)}
                                  </span>
                                  <Button disabled={state.busy} onClick={() => administer("rollback", version)}>
                                    {ctx.t("skills.manager.action.rollback")}
                                  </Button>
                                </div>
                              )}
                            </For>
                          </>
                        )}
                      </Show>
                    </article>
                  )}
                </For>
              </details>
            )}
          </For>
          <Show when={settled(page)?.matched === 0}>
            <p>{ctx.t("settings.skills.catalog.empty")}</p>
          </Show>
        </div>
        <div class="flex gap-3 items-center">
          <Button
            disabled={!state.offset || page.loading}
            onClick={() => setState("offset", Math.max(0, state.offset - 32))}
          >
            {ctx.t("settings.skills.catalog.previous")}
          </Button>
          <span>
            {settled(page)?.matched} {ctx.t("settings.skills.catalog.results")}
          </span>
          <Button
            disabled={state.offset + 32 >= (settled(page)?.matched ?? 0) || page.loading}
            onClick={() => setState("offset", state.offset + 32)}
          >
            {ctx.t("settings.skills.catalog.next")}
          </Button>
        </div>
      </Show>
    </section>
  )
}
