import { test, expect } from "bun:test"
import { Effect, Schema } from "effect"
import { SqliteClient } from "@effect/sql-sqlite-bun"
import { EffectDrizzleSqlite } from "@opencode/core/database/drizzle"
import { createHash, randomUUID } from "node:crypto"
import { readFile, mkdir, mkdtemp, chown, stat } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { Workflow } from "@opencode/core/watoom/workflow"
import { Specialist } from "@opencode/core/watoom/specialist"
// Self-contained fixture: the original wp-am3-sk1 checkout was retired with the 2026-10-29 archive.
const root = path.join(import.meta.dir, "fixtures/cpu-specialist")
const image = "sha256:e195b9f1d3baf86f93dadcb6fccb3f9e861ea6e4b815e6790835a1d5713bfe35"
const hash = (data: Uint8Array | string) => createHash("sha256").update(data).digest("hex")
const Input = Schema.Struct({ asset: Schema.Literal("valid.obj"), operation: Schema.Literal("inspect") })
const primary = {
  model: "fixture-primary-preserved",
  modelSha256: "a".repeat(64),
  configurationSha256: "b".repeat(64),
  deploymentUID: "fixture-primary-uid",
  router: "fixture-no-inference",
}
test("generic native CPU delegation executes existing Blender in an isolated no-GPU worker", async () => {
  const outputRoot = process.env.WATOOM_OWNED_CPU_OUTPUT ?? (await mkdtemp(path.join(tmpdir(), "watoom-cpu-fixture-")))
  await mkdir(outputRoot, { recursive: true })
  // Only the directory created by this test is assigned to the unprivileged worker.
  if (!process.env.WATOOM_OWNED_CPU_OUTPUT && process.getuid?.() === 0) await chown(outputRoot, 1001, 1001)
  const owner = await stat(outputRoot)
  if (owner.uid === 0) throw Error("CPU fixture output must belong to an unprivileged worker")
  const script = await readFile(root + "/inspect_asset.py")
  const registry = new Specialist.Registry()
  registry.register(
    {
      id: "blender-inspection",
      capabilities: ["vision.inspect"],
      backend: "blender.native-python.fixture",
      model: {
        model: "Blender4.2.23-fixture",
        modelSha256: image.slice(7),
        configurationSha256: hash(script),
        deploymentUID: "isolated-container",
        router: "none:cpu",
      },
      execution: "cpu",
      inputSchema: "fixture.blender.inspect.v1",
      outputSchema: "artifact.manifest.v1",
      timeoutMs: 10000,
      maxInputBytes: 1024,
      resources: { cpuCores: 1, ramMiB: 768, gpuMiB: 0, diskMiB: 64 },
      requiredSkills: ["vision-3d-inspector"],
      requiredTools: ["blender"],
      cancellation: "cooperative-abort",
      recovery: "positive-receipt-only",
      restoration: "exact-primary-identity",
      sourceCommit: "cd9a14a6b688d4021bee381dfd39d2cef9c0f862",
      evidence: "fixture",
    },
    {
      validateInput(input) {
        Schema.decodeUnknownSync(Input)(input)
      },
      async execute(operationID, _input, signal) {
        const name = "watoom-cpu-fixture-" + operationID.slice(0, 12)
        const output = "cpu-generic-" + operationID.slice(0, 16)
        const argv = [
          "docker",
          "run",
          "--rm",
          "--name",
          name,
          "--label",
          "watoom.isolated.wp-sk2=true",
          "--runtime=runc",
          "--network=none",
          "--read-only",
          "--cap-drop=ALL",
          "--security-opt=no-new-privileges",
          "--user",
          String(owner.uid) + ":" + String(owner.gid),
          "--memory=768m",
          "--memory-swap=768m",
          "--cpus=1",
          "--pids-limit=64",
          "--ulimit",
          "fsize=16777216:16777216",
          "--tmpfs",
          "/tmp:rw,noexec,nosuid,size=128m",
          "-v",
          root + ":/audit:ro",
          "-v",
          root + "/vision-fixtures:/input:ro",
          "-v",
          outputRoot + ":/output:rw,Z",
          "--entrypoint",
          "/usr/bin/env",
          image,
          "-i",
          "PATH=/usr/local/bin:/usr/bin:/bin",
          "HOME=/tmp",
          "CUDA_VISIBLE_DEVICES=",
          "NVIDIA_VISIBLE_DEVICES=void",
          "LIBGL_ALWAYS_SOFTWARE=1",
          "/opt/blender/blender",
          "--background",
          "--factory-startup",
          "--disable-autoexec",
          "--threads",
          "1",
          "--python-exit-code",
          "2",
          "--python",
          "/audit/inspect_asset.py",
          "--",
          "inspect",
          "valid.obj",
          "--input-root",
          "/input",
          "--output-root",
          "/output",
          "--output",
          output,
        ]
        const process = Bun.spawn(argv, { stdout: "pipe", stderr: "pipe" })
        const stop = () => {
          Bun.spawn(["docker", "stop", "--time", "2", name], { stdout: "ignore", stderr: "ignore" })
        }
        signal.addEventListener("abort", stop, { once: true })
        const [code, stdout, stderr] = await Promise.all([
          process.exited,
          new Response(process.stdout).text(),
          new Response(process.stderr).text(),
        ])
        signal.removeEventListener("abort", stop)
        if (code !== 0) throw Error("bounded Blender worker failed " + code + ": " + stderr.slice(-6000) + stdout.slice(-2000))
        const data = await readFile(outputRoot + "/" + output + "/manifest.json")
        const manifest = JSON.parse(data.toString())
        expect(manifest.blender).toBe("4.2.23 LTS")
        expect(manifest.gpu_device_nodes_present).toBe(false)
        expect(manifest.original_unchanged).toBe(true)
        expect(manifest.before[0].faces).toBe(4)
        return {
          summary: "Deterministic geometry inspection verified on an isolated fixture",
          artifacts: [
            { reference: "artifact:" + output + "/manifest.json", sha256: hash(data), bytes: data.byteLength },
          ],
        }
      },
      async verifyArtifacts(outcome) {
        for (const artifact of outcome.artifacts) {
          const relative = artifact.reference.slice("artifact:".length)
          const data = await readFile(outputRoot + "/" + relative)
          if (hash(data) !== artifact.sha256 || data.byteLength !== artifact.bytes) return false
        }
        return true
      },
    },
  )
  await Effect.runPromise(
    Effect.gen(function* () {
      const db = yield* EffectDrizzleSqlite.makeWithDefaults()
      yield* db.transaction((tx) => Workflow.migration.up(tx))
      yield* db.transaction((tx) => Specialist.migration.up(tx))
      const result = yield* Specialist.dispatch(db, registry, {
        scope: { project: "fixture", repository: "fixture", agent: "codex-fixture" },
        job: "real-cpu-fixture-" + randomUUID(),
        capability: "vision.inspect",
        payload: { asset: "valid.obj", operation: "inspect" },
        primary,
      })
      expect(result.artifacts.length).toBe(1)
    }).pipe(Effect.provide(SqliteClient.layer({ filename: ":memory:", disableWAL: true })), Effect.scoped),
  )
})
