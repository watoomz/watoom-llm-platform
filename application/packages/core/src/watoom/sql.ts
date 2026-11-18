import { sql } from "drizzle-orm"
import { sqliteTable, text, integer, primaryKey, unique, index, check } from "drizzle-orm/sqlite-core"

export const WorkflowCheckpointTable = sqliteTable(
  "_watoom_checkpoint",
  {
    scope: text().notNull(),
    job: text().notNull(),
    seq: integer().notNull(),
    body: text().notNull(),
  },
  (table) => [primaryKey({ columns: [table.scope, table.job] })],
)

export const WorkflowOutboxTable = sqliteTable(
  "_watoom_outbox",
  {
    id: text().primaryKey(),
    scope: text().notNull(),
    job: text().notNull(),
    seq: integer().notNull(),
    digest: text().notNull(),
    body: text().notNull(),
    checkpoint_body: text().notNull(),
    state: text().notNull(),
    attempts: integer().notNull().default(0),
    last_error: text(),
    receipt: text(),
    time_created: integer(),
    time_attempted: integer(),
    time_observed: integer(),
  },
  (table) => [
    unique().on(table.scope, table.job, table.seq),
    index("_watoom_outbox_dispatch").on(table.state, table.scope, table.job, table.seq),
    check("_watoom_outbox_state", sql`${table.state} IN ('pending','sending','uncertain','observed')`),
  ],
)

export const SpecialistJobTable = sqliteTable("_watoom_specialist_job", {
  id: text().primaryKey(),
  scope: text().notNull(),
  job: text().notNull(),
  specialist: text().notNull(),
  capability: text().notNull(),
  input_digest: text().notNull(),
  phase: text().notNull(),
  primary_body: text().notNull(),
  specialist_body: text().notNull(),
  generation: integer(),
  body: text(),
  outcome: text(),
  error: text(),
})
