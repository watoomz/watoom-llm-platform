import { createResource, For, onCleanup, Show } from "solid-js"
import type { MemoryStatusOutput } from "@opencode/client/promise"
import { usePlugin } from "@opencode/plugin/gui"
import { Button } from "@opencode/ui/button"
import type definition from "./index"
import { createServerChoice } from "./server-choice"
import { settled } from "./settled"

/** How often the page re-reads memory and GPU ownership status while it is open. */
const REFRESH_MS = 5000

type MemoryStatus = MemoryStatusOutput["data"]

/** Read-only AgentMemory delivery and GPU ownership health for one listed server. */
export default function MemoryPage() {
  const ctx = usePlugin<typeof definition>()
  const server = createServerChoice()

  const [status, { refetch }] = createResource(
    server.connected,
    async (ref): Promise<MemoryStatus> => (await ref.client.memory.status()).data,
  )

  const timer = setInterval(() => void refetch(), REFRESH_MS)
  onCleanup(() => clearInterval(timer))

  const time = (value: number | null | undefined) => (value ? new Date(value).toISOString() : ctx.t("memory.unknown"))
  const yes = (value: boolean | null) => ctx.t(value ? "memory.yes" : "memory.no")

  return (
    <div data-testid="memory-health-panel">
      <h1 class="settings-tab-title">{ctx.t("memory.title")}</h1>
      <server.Picker />
      <Button onClick={() => void refetch()}>{ctx.t("refresh")}</Button>
      <Show when={status.error}>
        <p role="alert">{ctx.t("memory.unavailable")}</p>
      </Show>
      <Show when={settled(status)} keyed>
        {(data) => (
          <>
            <h2 class="text-16-medium mt-5">{ctx.t("memory.memory")}</h2>
            <dl class="grid grid-cols-2 gap-2 my-3">
              <dt>{ctx.t("memory.enabled")}</dt>
              <dd>{yes(data.memory.enabled)}</dd>
              <dt>{ctx.t("memory.required")}</dt>
              <dd>{yes(data.memory.required)}</dd>
              <dt>{ctx.t("memory.pending")}</dt>
              <dd>{data.memory.outbox.pending}</dd>
              <dt>{ctx.t("memory.sending")}</dt>
              <dd>{data.memory.outbox.sending}</dd>
              <dt>{ctx.t("memory.uncertain")}</dt>
              <dd>{data.memory.outbox.uncertain}</dd>
              <dt>{ctx.t("memory.observed")}</dt>
              <dd>{data.memory.outbox.observed}</dd>
              <dt>{ctx.t("memory.lastCheckpoint")}</dt>
              <dd>{time(data.memory.outbox.lastCheckpoint)}</dd>
              <dt>{ctx.t("memory.lastObserved")}</dt>
              <dd>{time(data.memory.outbox.lastObserved)}</dd>
              <dt>{ctx.t("memory.oldestPending")}</dt>
              <dd>{time(data.memory.outbox.oldestPending)}</dd>
              <dt>{ctx.t("memory.lastRecall")}</dt>
              <dd>{time(data.memory.retrieval.lastSuccess)}</dd>
              <dt>{ctx.t("memory.latency")}</dt>
              <dd>{data.memory.retrieval.latencyMs ?? ctx.t("memory.unknown")}</dd>
              <dt>{ctx.t("memory.failures")}</dt>
              <dd>{data.memory.retrieval.failures}</dd>
            </dl>
            <p>{ctx.t("memory.observedCaveat")}</p>
            <Show when={data.memory.warnings.length}>
              <div role="status">
                <p>{ctx.t("memory.warnings")}</p>
                <For each={data.memory.warnings}>{(warning) => <code class="block">{warning}</code>}</For>
              </div>
            </Show>
            <h2 class="text-16-medium mt-5">{ctx.t("memory.recent")}</h2>
            <div class="overflow-x-auto">
              <table class="w-full my-3">
                <thead>
                  <tr>
                    <th>{ctx.t("memory.job")}</th>
                    <th>{ctx.t("memory.state")}</th>
                    <th>{ctx.t("memory.attempts")}</th>
                    <th>{ctx.t("memory.lastObserved")}</th>
                  </tr>
                </thead>
                <tbody>
                  <For each={data.memory.recent}>
                    {(record) => (
                      <tr>
                        <td class="max-w-sm break-all">
                          <code>{record.job}</code>
                        </td>
                        <td>{record.state}</td>
                        <td>{record.attempts}</td>
                        <td>{time(record.observed)}</td>
                      </tr>
                    )}
                  </For>
                </tbody>
              </table>
            </div>
            <h2 class="text-16-medium mt-5">{ctx.t("memory.ownership")}</h2>
            <Show
              when={data.ownership.available && !data.ownership.stale}
              fallback={<p role="status">{ctx.t("memory.ownershipUnavailable")}</p>}
            >
              <dl class="grid grid-cols-2 gap-2 my-3">
                <dt>{ctx.t("memory.phase")}</dt>
                <dd>{data.ownership.phase}</dd>
                <dt>{ctx.t("memory.owner")}</dt>
                <dd>{data.ownership.owner ?? ctx.t("memory.unowned")}</dd>
                <dt>{ctx.t("memory.generation")}</dt>
                <dd>{data.ownership.generation}</dd>
                <dt>{ctx.t("memory.uncertain")}</dt>
                <dd>{yes(data.ownership.uncertain)}</dd>
                <dt>{ctx.t("memory.activeRequests")}</dt>
                <dd>{data.ownership.activeRequests}</dd>
                <dt>{ctx.t("memory.primary")}</dt>
                <dd>{data.ownership.primary}</dd>
                <dt>{ctx.t("memory.sampled")}</dt>
                <dd>{time(data.ownership.sampledAt)}</dd>
              </dl>
            </Show>
            <p>{ctx.t("memory.readOnly")}</p>
          </>
        )}
      </Show>
    </div>
  )
}
