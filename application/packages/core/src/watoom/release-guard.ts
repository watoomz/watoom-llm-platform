export * as ReleaseGuard from "./release-guard.js"
import fs from "node:fs"
import path from "node:path"
import { Effect } from "effect"
/** Process-local admissions and executions share one synchronous lease boundary.
 * The durable file fences every replacement process until explicit owner release.
 * Missing or invalid configuration never grants release capability.
 */
export class Gate {
  private leases = 0
  constructor(readonly file?: string) {}
  status() { return { version: 1, supported: Boolean(this.file), held: Boolean(this.file && fs.existsSync(this.file)), leases: this.leases } }
  enter() {
    if (this.file && fs.existsSync(this.file)) throw Error("Deployment guard held; retry when promotion finishes")
    this.leases++
    let released = false
    return () => { if (!released) { released = true; this.leases-- } }
  }
  acquire(owner: string) {
    if (!this.file || !path.isAbsolute(this.file) || !/^[a-f0-9]{64}$/.test(owner)) throw Error("Persistent deployment guard unavailable")
    if (this.leases !== 0) throw Error("Active admission or execution; deployment refused")
    const fd = fs.openSync(this.file, "wx", 0o600)
    try { fs.writeFileSync(fd, JSON.stringify({ version: 1, owner })); fs.fsyncSync(fd) } finally { fs.closeSync(fd) }
    const dir = fs.openSync(path.dirname(this.file), "r")
    try { fs.fsyncSync(dir) } finally { fs.closeSync(dir) }
    return this.status()
  }
  release(owner: string) {
    if (!this.file || !/^[a-f0-9]{64}$/.test(owner)) throw Error("Invalid deployment guard owner")
    const value = JSON.parse(fs.readFileSync(this.file, "utf8"))
    if (value.version !== 1 || value.owner !== owner) throw Error("Deployment guard ownership mismatch")
    fs.unlinkSync(this.file)
    const dir = fs.openSync(path.dirname(this.file), "r")
    try { fs.fsyncSync(dir) } finally { fs.closeSync(dir) }
    return this.status()
  }
}
export const gate = new Gate(process.env.WATOOM_DEPLOYMENT_GATE_FILE)
export const admitted = <A, E, R>(effect: Effect.Effect<A, E, R>) =>
  Effect.acquireUseRelease(Effect.sync(() => gate.enter()), () => effect, (release) => Effect.sync(release))
