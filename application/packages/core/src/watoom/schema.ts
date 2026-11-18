/** Owned by OpenCode's native migration journal; no separate database or pragma changes. */
export const migrationID = "20261014000000_watoom_workflow"
export const statements = [
  `CREATE TABLE _watoom_checkpoint(scope TEXT NOT NULL,job TEXT NOT NULL,seq INTEGER NOT NULL,body TEXT NOT NULL,PRIMARY KEY(scope,job))`,
  `CREATE TABLE _watoom_outbox(id TEXT PRIMARY KEY,scope TEXT NOT NULL,job TEXT NOT NULL,seq INTEGER NOT NULL,digest TEXT NOT NULL,body TEXT NOT NULL,checkpoint_body TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('pending','sending','uncertain','observed')),attempts INTEGER NOT NULL DEFAULT 0,last_error TEXT,receipt TEXT,time_created INTEGER,time_attempted INTEGER,time_observed INTEGER,UNIQUE(scope,job,seq))`,
  `CREATE INDEX _watoom_outbox_dispatch ON _watoom_outbox(state,scope,job,seq)`,
] as const
