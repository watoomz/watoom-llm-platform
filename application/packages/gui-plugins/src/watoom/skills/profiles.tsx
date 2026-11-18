import { createMemo, createResource, For, Show } from "solid-js"
import { createStore } from "solid-js/store"
import type { ServerRef } from "@opencode/plugin/gui"
import { usePlugin } from "@opencode/plugin/gui"
import { Button } from "@opencode/ui/button"
import type definition from "../index"
import { settled } from "../settled"

type ProfileState = {
  selected: string[]
  components: string[]
  disabled: string[]
  busy: boolean
  error: boolean
  preview: string
  transaction: string
  loaded: boolean
}

/** Preview, install, export and roll back WatooM capability profiles on one server. */
export function ProfileManager(props: { server: () => ServerRef | undefined }) {
  const ctx = usePlugin<typeof definition>()

  const [state, setState] = createStore<ProfileState>({
    selected: ["minimal"],
    components: [],
    disabled: [],
    busy: false,
    error: false,
    preview: "",
    transaction: "",
    loaded: false,
  })

  const client = () => props.server()?.client

  const [catalog, { refetch }] = createResource(props.server, async (server) => {
    const data = await server.client.config.profiles.list()
    setState({
      selected: data.selected.length ? [...data.selected] : ["minimal"],
      components: [...data.components],
      disabled: [...data.disabled],
      transaction: data.transaction,
      loaded: true,
    })

    return data
  })

  const inherited = createMemo(() => {
    const seen = new Set<string>()
    const capabilities = new Set<string>()

    const visit = (id: string) => {
      if (seen.has(id)) return
      seen.add(id)
      const profile = settled(catalog)?.profiles.find((profile) => profile.id === id)
      profile?.capabilities.forEach((id) => capabilities.add(id))
      profile?.extends.forEach(visit)
    }

    state.selected.forEach(visit)

    return capabilities
  })

  const toggle = (id: string, enabled: boolean) => {
    setState("components", (values) => [
      ...values.filter((value) => value !== id),
      ...(enabled && !inherited().has(id) ? [id] : []),
    ])
    setState("disabled", (values) => [
      ...values.filter((value) => value !== id),
      ...(!enabled && inherited().has(id) ? [id] : []),
    ])
  }

  const apply = async (dryRun: boolean) => {
    setState({ busy: true, error: false })

    try {
      const api = client()

      if (!api) return

      const receipt = await api.config.profiles.install({
        profiles: state.selected,
        components: state.components,
        disabled: state.disabled,
        dryRun,
      })

      setState({ preview: JSON.stringify(receipt, null, 2), transaction: receipt.transaction ?? state.transaction })

      if (!dryRun) await refetch()
    } catch {
      setState("error", true)
    } finally {
      setState("busy", false)
    }
  }

  const rollback = async () => {
    setState({ busy: true, error: false })

    try {
      const api = client()

      if (!api) return
      await api.config.profiles.rollback({ transaction: state.transaction })
      setState({ transaction: "", preview: "" })
      await refetch()
    } catch {
      setState("error", true)
    } finally {
      setState("busy", false)
    }
  }

  const exportSelection = async () => {
    try {
      const api = client()

      if (!api) return
      const data = await api.config.profiles.export()
      setState("preview", data.configuration)
      const url = URL.createObjectURL(new Blob([data.configuration + "\n"], { type: "application/json" }))
      const link = document.createElement("a")
      link.href = url
      link.download = "watoom-profiles.json"
      link.click()
      URL.revokeObjectURL(url)
    } catch {
      setState("error", true)
    }
  }

  return (
    <section class="settings-section" aria-label={ctx.t("settings.profiles.title")}>
      <h3 class="settings-extension-heading text-13-medium">{ctx.t("settings.profiles.title")}</h3>
      <p class="text-13-regular text-v2-text-text-muted">{ctx.t("settings.profiles.description")}</p>
      <Show when={state.loaded}>
        <p role="status">{ctx.t("settings.profiles.loaded")}</p>
      </Show>
      <Show when={state.error || catalog.error}>
        <p role="alert">{ctx.t("settings.profiles.error")}</p>
      </Show>
      <For each={settled(catalog)?.profiles}>
        {(profile) => (
          <label class="flex gap-2 items-start py-2">
            <input
              type="checkbox"
              aria-label={profile.id}
              checked={state.selected.includes(profile.id)}
              disabled={state.busy}
              onChange={(event) =>
                setState("selected", (selected) =>
                  event.currentTarget.checked ? [...selected, profile.id] : selected.filter((id) => id !== profile.id),
                )
              }
            />
            <span class="text-13-regular">
              <strong>{profile.id}</strong> {profile.version}
              <br />
              {profile.capabilities.join(", ")}
              <br />
              {profile.skills.join(", ")}
            </span>
          </label>
        )}
      </For>
      <h4>{ctx.t("settings.profiles.components")}</h4>
      <For each={settled(catalog)?.capabilities.filter((capability) => capability.optional)}>
        {(capability) => (
          <label class="flex gap-2 items-start py-2">
            <input
              type="checkbox"
              aria-label={"component:" + capability.id}
              disabled={state.busy}
              checked={
                !state.disabled.includes(capability.id) &&
                (inherited().has(capability.id) || state.components.includes(capability.id))
              }
              onChange={(event) => toggle(capability.id, event.currentTarget.checked)}
            />
            <span>
              {capability.id}{" "}
              <span data-testid={"availability:" + capability.id}>
                {settled(catalog)?.statuses.find((value) => value.id === capability.id)?.status}
              </span>
              <br />
              {settled(catalog)
                ?.statuses.find((value) => value.id === capability.id)
                ?.missing.join(", ")}
            </span>
          </label>
        )}
      </For>
      <div class="flex gap-2">
        <Button disabled={state.busy || !state.selected.length} onClick={() => apply(true)}>
          {ctx.t("settings.profiles.preview")}
        </Button>
        <Button disabled={state.busy || !state.selected.length} onClick={() => apply(false)}>
          {ctx.t("settings.profiles.install")}
        </Button>
        <Button disabled={state.busy} onClick={exportSelection}>
          {ctx.t("settings.profiles.export")}
        </Button>
        <Show when={state.transaction}>
          <Button disabled={state.busy} onClick={rollback}>
            {ctx.t("settings.profiles.rollback")}
          </Button>
        </Show>
      </div>
      <Show when={state.preview}>
        <pre class="text-13-regular whitespace-pre-wrap overflow-auto" aria-label={ctx.t("settings.profiles.preview")}>
          {state.preview}
        </pre>
      </Show>
    </section>
  )
}
