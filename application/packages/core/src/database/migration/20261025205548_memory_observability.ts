import { Effect } from "effect"
import type { DatabaseMigration } from "../migration.js"

const migration: DatabaseMigration.Migration = {
  id: "20261025205548_memory_observability",
  up(tx) {
    return Effect.gen(function* () {
      yield* tx.run(`ALTER TABLE \`_watoom_outbox\` ADD \`time_created\` integer;`)
      yield* tx.run(`ALTER TABLE \`_watoom_outbox\` ADD \`time_attempted\` integer;`)
      yield* tx.run(`ALTER TABLE \`_watoom_outbox\` ADD \`time_observed\` integer;`)
    })
  },
}

export default migration
