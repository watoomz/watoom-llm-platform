import { createEffect, For, onCleanup, Show } from "solid-js"
import { createStore } from "solid-js/store"
import { useServerSDK } from "@/runtime/server/client"
import { useLanguage } from "@/runtime/i18n/language"
import type { SessionImagesOutput } from "@opencode/client/promise"

type Job = SessionImagesOutput[number]
const terminal = new Set(["GENERATION_VERIFIED", "FAILED", "CANCELLED"])
export function SessionImages(props: { sessionID?: string; revision: string; active: boolean }) {
  const sdk = useServerSDK()
  const language = useLanguage()
  const [state, setState] = createStore({ jobs: [] as Job[], error: false })
  createEffect(() => {
    const sessionID = props.sessionID
    props.revision
    const active = props.active
    setState({ jobs: [], error: false })
    if (!sessionID || !active) return
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const images = new Map<string, Job>()
    onCleanup(() => {
      stopped = true
      clearTimeout(timer)
    })
    const refresh = async () => {
      try {
        const response = await sdk.api.session.images({ sessionID })
        if (stopped) return
        const jobs: Job[] = []
        for (const job of response) {
          if (stopped) return
          if (job.state !== "GENERATION_VERIFIED") {
            jobs.push(job)
            continue
          }
          let image = images.get(job.job_id)
          if (!image) {
            const result = await sdk.api.session.images({ sessionID, jobID: job.job_id })
            if (stopped) return
            image = result.find((item) => item.job_id === job.job_id && item.png)
            if (!image) throw Error("Image receipt missing")
            images.set(job.job_id, image)
          }
          jobs.push(image)
        }
        setState({ jobs, error: false })
        if (jobs.some((job) => !terminal.has(job.state))) timer = setTimeout(refresh, 5000)
        else if (!jobs.length) timer = setTimeout(refresh, 15000)
      } catch {
        if (stopped) return
        setState("error", true)
        timer = setTimeout(refresh, 15000)
      }
    }
    void refresh()
  })
  return (
    <div data-component="session-images" class="px-4 md:px-5 max-w-[1000px] mx-auto w-full">
      <Show when={state.error}>
        <p role="status">{language.t("session.images.unavailable")}</p>
      </Show>
      <For each={state.jobs}>
        {(job) => (
          <section class="my-4 rounded-lg border border-border-base p-3" data-image-job={job.job_id}>
            <p role="status">
              {language.t(
                job.png
                  ? "session.images.complete"
                  : job.state === "FAILED" || job.state === "CANCELLED"
                    ? "session.images.failed"
                    : "session.images.pending",
              )}
            </p>
            <Show when={job.png}>
              {(png) => (
                <>
                  <a
                    href={`data:image/png;base64,${png()}`}
                    download={`${job.job_id}.png`}
                    aria-label={language.t("session.images.download")}
                  >
                    <img
                      src={`data:image/png;base64,${png()}`}
                      alt={language.t("session.images.alt")}
                      class="max-w-full max-h-[70vh] object-contain rounded my-2"
                    />
                  </a>
                  <a href={`data:image/png;base64,${png()}`} download={`${job.job_id}.png`}>
                    {language.t("session.images.download")}
                  </a>
                  <p class="text-xs break-all">SHA-256: {job.sha256}</p>
                </>
              )}
            </Show>
            <Show when={!job.png}>
              <p class="text-xs break-all">
                {job.state} · {job.job_id}
              </p>
            </Show>
          </section>
        )}
      </For>
    </div>
  )
}
