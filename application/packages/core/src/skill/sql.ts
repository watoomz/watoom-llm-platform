import { sqliteTable, text, primaryKey } from "drizzle-orm/sqlite-core"

export const SkillSessionSelectionTable = sqliteTable(
  "_watoom_skill_selection",
  {
    session_id: text().notNull(),
    scope: text().notNull(),
    skill_id: text().notNull(),
    content_sha: text().notNull(),
    commit_sha: text().notNull(),
    bundle_sha: text().notNull(),
  },
  (table) => [primaryKey({ columns: [table.session_id, table.skill_id] })],
)

export const SkillAgentSelectionTable = sqliteTable(
  "_watoom_agent_skill_selection",
  {
    scope: text().notNull(),
    skill_id: text().notNull(),
    content_sha: text().notNull(),
    commit_sha: text().notNull(),
    bundle_sha: text().notNull(),
  },
  (table) => [primaryKey({ columns: [table.scope, table.skill_id] })],
)
