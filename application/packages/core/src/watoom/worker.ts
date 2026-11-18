export * as IsolatedWorker from "./worker.js"

import { spawn } from "node:child_process"
import { createHash, randomUUID } from "node:crypto"
import { lstat, readFile, realpath } from "node:fs/promises"
import path from "node:path"

export type Request = {
  image: string
  workspace: string
  output: string
  command: readonly string[]
  artifacts: readonly string[]
  timeoutMs: number
  cpu: number
  memoryMiB: number
  uid: number
}
export type Result = {
  status: "PASS" | "FAIL" | "TIMEOUT" | "CANCELLED"
  exitCode: number | null
  output: string
  truncated: boolean
  artifacts: { path: string; sha256: string; bytes: number }[]
}

/** Caller owns native permission admission. This adapter accepts no Pod specs, credentials,
 * environment, devices, network, host root, or daemon options from a model. */
export async function execute(input: Request, signal?: AbortSignal): Promise<Result> {
  if (!/^sha256:[a-f0-9]{64}$/.test(input.image)) throw Error("worker requires an immutable local image")
  if (!Number.isInteger(input.timeoutMs) || input.timeoutMs < 1 || input.timeoutMs > 180000 ||
      !Number.isInteger(input.memoryMiB) || input.memoryMiB < 32 || input.memoryMiB > 2048 ||
      !Number.isFinite(input.cpu) || input.cpu < 0.1 || input.cpu > 2 ||
      !Number.isInteger(input.uid) || input.uid < 10000 || input.uid > 65534)
    throw Error("invalid worker resource or identity contract")
  if (!input.command.length || input.command.length > 64 || input.command.some((x) => !x || x.length > 8192 || x.includes("\0")))
    throw Error("invalid worker command")
  const workspace = await realpath(input.workspace)
  const output = await realpath(input.output)
  if (!path.isAbsolute(input.workspace) || !path.isAbsolute(input.output) ||
      workspace === path.parse(workspace).root || output === path.parse(output).root ||
      workspace === output || workspace.startsWith(output + path.sep) || output.startsWith(workspace + path.sep) ||
      [workspace, output].some((x) => x.includes(",") || x.includes("\n")) ||
      !(await lstat(workspace)).isDirectory() || !(await lstat(output)).isDirectory())
    throw Error("worker needs separate explicit workspace and output directories")
  if (input.artifacts.length > 32 || new Set(input.artifacts).size !== input.artifacts.length ||
      input.artifacts.some((x) => !x || x.length > 400 || x.includes("\\") || x.split("/").some((p) => !p || p === "." || p === "..")))
    throw Error("invalid worker artifact path")
  // Required outputs must be new; a prior successful artifact cannot satisfy a failed producer.
  for (const name of input.artifacts) {
    const existing = await lstat(path.join(output, name)).catch((e: NodeJS.ErrnoException) => {
      if (e.code === "ENOENT") return undefined
      throw e
    })
    if (existing) throw Error("worker artifact already exists")
  }
  if (signal?.aborted) throw Error("worker cancelled before launch")
  const name = "watoom-worker-" + randomUUID()
  const command = ["run", "--rm", "--pull=never", "--name", name, "--network=none", "--read-only",
    "--cap-drop=ALL", "--security-opt=no-new-privileges", "--security-opt=label=disable", "--user", String(input.uid) + ":" + String(input.uid),
    "--cpus", String(input.cpu), "--memory", input.memoryMiB + "m", "--memory-swap", input.memoryMiB + "m",
    "--pids-limit=64", "--ulimit", "nofile=128:128", "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m",
    "--mount", "type=bind,src=" + workspace + ",dst=/workspace,readonly",
    "--mount", "type=bind,src=" + output + ",dst=/output", "--workdir=/workspace",
    "--entrypoint", input.command[0], input.image, ...input.command.slice(1)]
  const child = spawn("docker", command, { env: { PATH: process.env.PATH ?? "/usr/bin:/bin" }, stdio: ["ignore", "pipe", "pipe"] })
  let bytes = Buffer.alloc(0)
  let truncated = false
  let stop: "TIMEOUT" | "CANCELLED" | undefined
  const capture = (part: Buffer) => {
    bytes = Buffer.concat([bytes, part])
    if (bytes.length > 65536) { bytes = bytes.subarray(-65536); truncated = true }
  }
  child.stdout.on("data", capture)
  child.stderr.on("data", capture)
  // Container removal kills all namespace descendants, including setsid processes.
  const remove = () => new Promise<void>((resolve, reject) => {
    const cleanup = spawn("docker", ["rm", "--force", name], { env: { PATH: process.env.PATH ?? "/usr/bin:/bin" }, stdio: "ignore" })
    const timeout = setTimeout(() => { cleanup.kill("SIGKILL"); reject(Error("worker cleanup uncertain")) }, 10000)
    cleanup.on("error", (e) => { clearTimeout(timeout); reject(e) })
    cleanup.on("close", () => { clearTimeout(timeout); resolve() })
  })
  let cleanup: Promise<void> | undefined
  const terminate = (reason: "TIMEOUT" | "CANCELLED") => {
    stop = reason
    child.kill("SIGKILL")
    cleanup = remove()
    // Observed below in finally; prevent an early unhandled rejection.
    void cleanup.catch(() => {})
  }
  const cancel = () => terminate("CANCELLED")
  const timer = setTimeout(() => terminate("TIMEOUT"), input.timeoutMs)
  signal?.addEventListener("abort", cancel, { once: true })
  const exitCode = await new Promise<number | null>((resolve, reject) => {
    child.on("error", reject)
    child.on("close", resolve)
  }).finally(async () => {
    clearTimeout(timer)
    signal?.removeEventListener("abort", cancel)
    await (cleanup ?? remove())
  })
  const status = stop ?? (exitCode === 0 ? "PASS" : "FAIL")
  const artifacts: Result["artifacts"] = []
  if (status === "PASS") for (const name of input.artifacts) {
    const file = path.join(output, name)
    const canonical = await realpath(file)
    const stat = await lstat(file)
    if (!canonical.startsWith(output + path.sep) || canonical !== file || !stat.isFile() || stat.isSymbolicLink() || stat.nlink !== 1 || stat.size < 1 || stat.size > 64 * 1024 * 1024)
      throw Error("worker artifact contract failed")
    const data = await readFile(file)
    artifacts.push({ path: name, sha256: createHash("sha256").update(data).digest("hex"), bytes: data.length })
  }
  return { status, exitCode, output: bytes.toString("utf8"), truncated, artifacts }
}
