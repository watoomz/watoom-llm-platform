import { Effect } from "effect"
import type { DatabaseMigration } from "../migration.js"

const migration: DatabaseMigration.Migration = {
  id: "20261015113533_watoom_operational_state",
  up(tx) {
    return Effect.gen(function* () {
      yield* tx.run(`
        CREATE TABLE \`_watoom_specialist_job\` (
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
        CREATE TABLE \`_watoom_checkpoint\` (
          \`scope\` text NOT NULL,
          \`job\` text NOT NULL,
          \`seq\` integer NOT NULL,
          \`body\` text NOT NULL,
          CONSTRAINT \`_watoom_checkpoint_pk\` PRIMARY KEY(\`scope\`, \`job\`)
        );
      `)
      yield* tx.run(`
        CREATE TABLE \`_watoom_outbox\` (
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
          CONSTRAINT \`_watoom_outbox_scope_job_seq_unique\` UNIQUE(\`scope\`,\`job\`,\`seq\`),
          CONSTRAINT "_watoom_outbox_state" CHECK("state" IN ('pending','sending','uncertain','observed'))
        );
      `)
      yield* tx.run(
        `CREATE INDEX \`_watoom_outbox_dispatch\` ON \`_watoom_outbox\` (\`state\`,\`scope\`,\`job\`,\`seq\`);`,
      )
    })
  },
}

export default migration
