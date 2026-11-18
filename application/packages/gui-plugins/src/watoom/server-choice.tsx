import { createMemo, createSignal, Show } from "solid-js"
import type { ServerRef } from "@opencode/plugin/gui"
import { usePlugin } from "@opencode/plugin/gui"
import { Select } from "@opencode/ui/select"
import type definition from "./index"

/**
 * The server a WatooM page reads from: the one the user picked, else the first listed. `connected` is the live ref
 * only while its event connection is up; read it where you use it, as a restarted server gets a new client.
 */
export function createServerChoice() {
  const ctx = usePlugin<typeof definition>()
  const [chosen, setChosen] = createSignal<string>()

  // Fall back to the first listed server when none is chosen or the chosen one is no longer listed.
  const id = createMemo(() => {
    const ids = ctx.servers.list()
    const value = chosen()

    return value && ids.includes(value) ? value : ids[0]
  })

  const connected = (): ServerRef | undefined => {
    const value = id()
    const server = value ? ctx.servers.get(value) : undefined

    return server?.connected ? server : undefined
  }

  /** A server picker, shown only when the app lists more than one server. */
  const Picker = () => (
    <Show when={ctx.servers.list().length > 1}>
      <label class="flex gap-2 my-3">
        {ctx.t("server")}
        <Select
          options={[...ctx.servers.list()]}
          current={id()}
          value={(value) => value}
          label={(value) => ctx.servers.get(value)?.name ?? value}
          onSelect={(value) => value && setChosen(value)}
        />
      </label>
    </Show>
  )

  return { id, connected, Picker }
}
