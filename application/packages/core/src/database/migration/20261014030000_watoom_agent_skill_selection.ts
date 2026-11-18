import { Effect } from "effect"
import { sql } from "drizzle-orm"
import type { DatabaseMigration } from "../migration.js"

const migration = {
  id: "20261014030000_watoom_agent_skill_selection",
  up: (tx) =>
    tx
      .run(
        sql`CREATE TABLE IF NOT EXISTS _watoom_agent_skill_selection(scope TEXT NOT NULL,skill_id TEXT NOT NULL,content_sha TEXT NOT NULL,commit_sha TEXT NOT NULL,bundle_sha TEXT NOT NULL,PRIMARY KEY(scope,skill_id))`,
      )
      .pipe(Effect.asVoid),
} satisfies DatabaseMigration.Migration

export default migration
