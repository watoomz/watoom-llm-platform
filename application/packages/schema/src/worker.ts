export * as WorkerConfig from "./worker.js"
import { Schema } from "effect"
import { AbsolutePath } from "./schema.js"
export const Info = Schema.Struct({
  image: Schema.String.check(Schema.isPattern(/^sha256:[a-f0-9]{64}$/)),
  output: AbsolutePath,
  uid: Schema.Int.check(Schema.isBetween({ minimum: 10000, maximum: 65534 })),
  cpu: Schema.Number.check(Schema.isBetween({ minimum: 0.1, maximum: 2 })),
  memoryMiB: Schema.Int.check(Schema.isBetween({ minimum: 32, maximum: 2048 })),
  timeoutMs: Schema.Int.check(Schema.isBetween({ minimum: 1, maximum: 180000 })),
})
