import { Effect } from "effect"
import type { DatabaseMigration } from "../migration.js"

const migration: DatabaseMigration.Migration = {
  id: "20261104072023_watoom_port",
  up(tx) {
    return Effect.gen(function* () {
      yield* tx.run(`
        CREATE TABLE IF NOT EXISTS \`_watoom_agent_skill_selection\` (
          \`scope\` text NOT NULL,
          \`skill_id\` text NOT NULL,
          \`content_sha\` text NOT NULL,
          \`commit_sha\` text NOT NULL,
          \`bundle_sha\` text NOT NULL,
          CONSTRAINT \`_watoom_agent_skill_selection_pk\` PRIMARY KEY(\`scope\`, \`skill_id\`)
        );
      `)
      yield* tx.run(`
        CREATE TABLE IF NOT EXISTS \`_watoom_skill_selection\` (
          \`session_id\` text NOT NULL,
          \`scope\` text NOT NULL,
          \`skill_id\` text NOT NULL,
          \`content_sha\` text NOT NULL,
          \`commit_sha\` text NOT NULL,
          \`bundle_sha\` text NOT NULL,
          CONSTRAINT \`_watoom_skill_selection_pk\` PRIMARY KEY(\`session_id\`, \`skill_id\`)
        );
      `)
      yield* tx.run(`
        CREATE TABLE IF NOT EXISTS \`_watoom_specialist_job\` (
          \`id\` text PRIMARY KEY,
          \`scope\` text NOT NULL,
          \`job\` text NOT NULL,
          \`specialist\` text NOT NULL,
          \`capability\` text NOT NULL,
          \`input_digest\` text NOT NULL,
          \`phase\` text NOT NULL,
          \`primary_body\` text NOT NULL,
          \`specialist_body\` text NOT NULL,
          \`generation\` integer,
          \`body\` text,
          \`outcome\` text,
          \`error\` text
        );
      `)
      yield* tx.run(`
        CREATE TABLE IF NOT EXISTS \`_watoom_checkpoint\` (
          \`scope\` text NOT NULL,
          \`job\` text NOT NULL,
          \`seq\` integer NOT NULL,
          \`body\` text NOT NULL,
          CONSTRAINT \`_watoom_checkpoint_pk\` PRIMARY KEY(\`scope\`, \`job\`)
        );
      `)
      yield* tx.run(`
        CREATE TABLE IF NOT EXISTS \`_watoom_outbox\` (
          \`id\` text PRIMARY KEY,
          \`scope\` text NOT NULL,
          \`job\` text NOT NULL,
          \`seq\` integer NOT NULL,
          \`digest\` text NOT NULL,
          \`body\` text NOT NULL,
          \`checkpoint_body\` text NOT NULL,
          \`state\` text NOT NULL,
          \`attempts\` integer DEFAULT 0 NOT NULL,
          \`last_error\` text,
          \`receipt\` text,
          \`time_created\` integer,
          \`time_attempted\` integer,
          \`time_observed\` integer,
          CONSTRAINT \`_watoom_outbox_scope_job_seq_unique\` UNIQUE(\`scope\`,\`job\`,\`seq\`),
          CONSTRAINT "_watoom_outbox_state" CHECK("state" IN ('pending','sending','uncertain','observed'))
        );
      `)
      yield* tx.run(
        `CREATE INDEX IF NOT EXISTS \`_watoom_outbox_dispatch\` ON \`_watoom_outbox\` (\`state\`,\`scope\`,\`job\`,\`seq\`);`,
      )
    })
  },
}

export default migration
