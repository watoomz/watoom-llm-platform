import { expect, test } from "bun:test"
import { chmod, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { execute } from "@opencode/core/watoom/worker"

const image = process.env.WATOOM_WORKER_TEST_IMAGE
test("worker rejects mutable images before execution", async () => {
  await expect(execute({ image: "node:latest", workspace: "/", output: "/", command: ["node"], artifacts: [], timeoutMs: 1000, cpu: 1, memoryMiB: 64, uid: 10001 })).rejects.toThrow("immutable")
})
test.skipIf(!image)("real disposable worker denies synthetic secrets, host writes and detached descendants", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "watoom-worker-"))
  const workspace = path.join(root, "input")
  const output = path.join(root, "output")
  const { mkdir } = await import("node:fs/promises")
  await mkdir(workspace)
  await mkdir(output)
  await chmod(root, 0o755)
  await chmod(output, 0o777)
  const secret = path.join(root, "synthetic-secret")
  await writeFile(secret, "DISPOSABLE_TEST_MARKER", { mode: 0o600 })
  await writeFile(path.join(workspace, "input.txt"), "original")
  const request = { image: image!, workspace, output, command: ["node"], artifacts: ["receipt.json"], timeoutMs: 15000, cpu: 0.5, memoryMiB: 128, uid: 10001 }
  try {
    const result = await execute({ ...request, command: ["node", "-e", `const fs=require('fs');let denied=0;for(const p of [${JSON.stringify(secret)},'/workspace/input.txt','/etc/worker-test']){try{fs.writeFileSync(p,'changed')}catch{denied++}}let credential=false;try{fs.readFileSync(${JSON.stringify(secret)});credential=true}catch{};fs.writeFileSync('/output/receipt.json',JSON.stringify({denied,credential,uid:process.getuid(),env:process.env.WATOOM_TOOLKIT_TOKEN??null}));const c=require('child_process').spawn('node',['-e',"setTimeout(()=>require('fs').writeFileSync('/output/escaped','bad'),1000)"],{detached:true,stdio:'ignore'});c.unref();` ] })
    if (result.status !== "PASS") throw Error(JSON.stringify(result))
    expect(result.artifacts).toHaveLength(1)
    expect(JSON.parse(await readFile(path.join(output, "receipt.json"), "utf8"))).toEqual({ denied: 3, credential: false, uid: 10001, env: null })
    await Bun.sleep(1300)
    expect(await Bun.file(path.join(output, "escaped")).exists()).toBe(false)
    expect(await readFile(path.join(workspace, "input.txt"), "utf8")).toBe("original")
    await expect(execute(request)).rejects.toThrow("already exists")
    const timeout = await execute({ ...request, artifacts: [], timeoutMs: 500, command: ["node", "-e", "setInterval(()=>{},1000)"] })
    expect(timeout.status).toBe("TIMEOUT")
    const controller = new AbortController()
    const cancellation = setTimeout(() => controller.abort(), 500)
    try {
      const cancelled = await execute({ ...request, artifacts: [], command: ["node", "-e", "setInterval(()=>{},1000)"] }, controller.signal)
      expect(cancelled.status).toBe("CANCELLED")
    } finally { clearTimeout(cancellation) }

    await expect(execute({ ...request, artifacts: ["missing"], command: ["node", "-e", "process.exit(0)"] })).rejects.toThrow()
    await expect(execute({ ...request, artifacts: ["link"], command: ["node", "-e", "require('fs').symlinkSync('/etc/passwd','/output/link')"] })).rejects.toThrow()
  } finally {
    await rm(root, { recursive: true, force: true })
  }
}, 45000)
