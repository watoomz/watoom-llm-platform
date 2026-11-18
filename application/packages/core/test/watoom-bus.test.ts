import { expect } from "bun:test"
import { Effect, Schema } from "effect"
import { sql } from "drizzle-orm"
import { Bus } from "@opencode/core/bus"
import { Database } from "@opencode/core/database/database"
import { AppNodeBuilder } from "@opencode/core/effect/app-node-builder"
import { LayerNode } from "@opencode/util/effect/layer-node"
import { checkpointOnCommit } from "@opencode/core/watoom/workflow"
import { testEffect } from "./lib/effect"
const it = testEffect(
  AppNodeBuilder.build(LayerNode.group([Database.node, Bus.node]), [
    Bus.node.replace(Bus.configured({ persist: true })),
  ]),
)
const Fact = Bus.durable({
  type: "watoom.test.workflow.fact",
  durable: { version: 1, aggregate: "job" },
  schema: { job: Schema.String, status: Schema.String },
})
const event = {
  scope: { project: "p", repository: "r", agent: "a" },
  job: "job",
  seq: 1,
  kind: "checkpoint" as const,
  content: "source verified test result",
}
it.effect("real native durable Bus commit and outbox share owner transaction", () =>
  Effect.gen(function* () {
    const bus = yield* Bus.Service
    const database = yield* Database.Service
    const db = database.db
    yield* bus.publish(
      Fact,
      { job: "job", status: "verified" },
      { commit: checkpointOnCommit(db, event, { status: "verified" }) },
    )
    expect((yield* db.get<{ n: number }>(sql`SELECT count(*) n FROM _watoom_outbox`))?.n).toBe(1)
    expect((yield* db.get<{ n: number }>(sql`SELECT count(*) n FROM event WHERE aggregate_id='job'`))?.n).toBe(1)
  }),
)
it.effect("real durable Bus fails atomically for unsafe checkpoint", () =>
  Effect.gen(function* () {
    const bus = yield* Bus.Service
    const database = yield* Database.Service
    const db = database.db
    const result = yield* bus
      .publish(
        Fact,
        { job: "job", status: "verified" },
        { commit: checkpointOnCommit(db, event, { secret: "forbidden-fixture" }) },
      )
      .pipe(Effect.exit)
    expect(result._tag).toBe("Failure")
    expect((yield* db.get<{ n: number }>(sql`SELECT count(*) n FROM event WHERE aggregate_id='job'`))?.n).toBe(0)
    expect((yield* db.get<{ n: number }>(sql`SELECT count(*) n FROM _watoom_outbox`))?.n).toBe(0)
  }),
)
