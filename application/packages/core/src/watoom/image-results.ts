export * as ImageResults from "./image-results.js"
import { Effect, Schema } from "effect"
import { createHash } from "node:crypto"
import { Mcp } from "../mcp/index.js"
import { Session } from "../session.js"

const Job = Schema.Struct({
  job_id: Schema.String,
  state: Schema.String,
  error: Schema.NullOr(Schema.String),
  updated: Schema.Number,
})
const Jobs = Schema.Struct({ jobs: Schema.Array(Job) })
const Result = Schema.Struct({
  sha256: Schema.String,
  width: Schema.Number,
  height: Schema.Number,
  restoration: Schema.Struct({ verified: Schema.Boolean }),
})
export function verified(result: Mcp.ToolResult) {
  if (result.isError) throw Error("Image result rejected")
  const receipt = Schema.decodeUnknownSync(Result)(result.structured)
  const image = result.content.find((part) => part.type === "media" && part.mimeType === "image/png")
  if (!receipt.restoration.verified || !image || image.type !== "media") throw Error("Unverified image")
  const png = Buffer.from(image.data, "base64")
  if (
    png.length < 24 ||
    png.length > 16 * 1024 * 1024 ||
    png.subarray(0, 8).toString("hex") !== "89504e470d0a1a0a" ||
    png.readUInt32BE(16) !== receipt.width ||
    png.readUInt32BE(20) !== receipt.height ||
    createHash("sha256").update(png).digest("hex") !== receipt.sha256
  )
    throw Error("Invalid image receipt")
  return { png: image.data, sha256: receipt.sha256 }
}
/** Existing worker receipts are the durable record; reads cannot enqueue or resume work. */
export const read = Effect.fn("ImageResults.read")(function* (
  sessions: Session.Interface,
  sessionID: Session.ID,
  jobID?: string,
) {
  const mcp = yield* Mcp.Service
  const server = (yield* mcp.servers()).find((server) => server.name === "watoom-images")
  if (!server) return []
  if (server.status.status !== "connected") return yield* Effect.fail(Error("Image worker disconnected"))
  const ids = [sessionID]
  for (let i = 0; i < ids.length && ids.length < 32; i++) {
    const children = yield* sessions.list({ parentID: ids[i]! })
    for (const child of children.data) {
      if (ids.length >= 32) break
      ids.push(child.id)
    }
  }
  const jobs = []
  for (const origin of ids) {
    const response = yield* mcp.callTool({
      server: "watoom-images",
      name: "list_session_images",
      args: {},
      sessionID: origin,
    })
    if (response.isError) return yield* Effect.fail(Error("Image receipts unavailable"))
    const rows = yield* Schema.decodeUnknownEffect(Jobs)(response.structured)
    for (const job of rows.jobs) {
      if (jobID && job.job_id !== jobID) continue
      if (!jobID || job.state !== "GENERATION_VERIFIED") {
        jobs.push(job)
        continue
      }
      const result = yield* mcp.callTool({
        server: "watoom-images",
        name: "image_result",
        args: { job_id: jobID },
        sessionID: origin,
      })
      const image = yield* Effect.try(() => verified(result))
      jobs.push({ ...job, ...image })
    }
  }
  return jobs
})
