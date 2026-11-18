import agentMigration from "../database/migration/20261014030000_watoom_agent_skill_selection.js"
import migration from "../database/migration/20261014020000_watoom_skill_selection.js"
export * as Catalog from "./catalog.js"

/** Native package catalog queries and session selection. Reuses the existing SQLite abstraction. */
import { Effect, Schema } from "effect"
import { sql } from "drizzle-orm"
import type { EffectDrizzleSqlite } from "../database/drizzle.js"
import { scopeKey, type Scope } from "./contract.js"
type DB = Effect.Success<ReturnType<typeof EffectDrizzleSqlite.makeWithDefaults>>
export class Rejected extends Schema.TaggedError<Rejected>()("SkillCatalog.Rejected", { message: Schema.String }) {}
export type Summary = {
  id: string
  repo: string
  path: string
  name: string
  description: string
  sha256: string
  commit_sha: string
  license: string
  risk: string
  approved: number
  bundle_sha: string | null
}

export function search(catalog: DB, query: string, limit = 16, approvedOnly = true) {
  if (typeof query !== "string" || query.length > 256 || !Number.isInteger(limit) || limit < 1 || limit > 32)
    return Effect.die(Error("catalog search bounds"))
  const terms = query.match(/[\w-]+/g)?.slice(0, 8) ?? []
  const match = terms.map((x) => '"' + x + '"*').join(" AND ")
  const where = terms.length ? sql`AND s.id IN(SELECT id FROM skills_fts WHERE skills_fts MATCH ${match})` : sql``
  const approved = approvedOnly
    ? sql`AND a.approved_sha=s.sha256 AND ac.commit_sha=src.commit_sha AND s.validation='valid'`
    : sql``
  return catalog.all<Summary>(
    sql`SELECT s.id,s.repo,s.path,s.name,s.description,s.sha256,src.commit_sha,s.license,s.risk,ac.bundle_sha,CASE WHEN a.approved_sha=s.sha256 AND ac.commit_sha=src.commit_sha THEN 1 ELSE 0 END approved FROM skills s JOIN sources src ON src.repo=s.repo LEFT JOIN approvals a ON a.skill_id=s.id LEFT JOIN approval_context ac ON ac.skill_id=s.id WHERE 1=1 ${where} ${approved} ORDER BY s.name,s.id LIMIT ${limit}`,
  )
}
function session(value: string) {
  if (!/^[A-Za-z0-9_.:-]{1,256}$/.test(value)) throw Error("invalid session identity")
}
export function select(db: DB, catalog: DB, input: { sessionID: string; scope: Scope; skillID: string }) {
  return Effect.gen(function* () {
    session(input.sessionID)
    const scope = scopeKey(input.scope)
    const row = yield* approvedReference(catalog, input.skillID)
    yield* db.run(
      sql`INSERT INTO _watoom_skill_selection VALUES(${input.sessionID},${scope},${row.id},${row.sha256},${row.commit_sha},${row.bundle_sha}) ON CONFLICT(session_id,skill_id) DO UPDATE SET scope=excluded.scope,content_sha=excluded.content_sha,commit_sha=excluded.commit_sha,bundle_sha=excluded.bundle_sha`,
    )
    return {
      id: row.id,
      sha256: row.sha256,
      commit: row.commit_sha,
      bundleSha256: row.bundle_sha,
      status: "SELECTED_NOT_EXECUTED" as const,
    }
  })
}
/** Called by the existing native loader only after session ownership and permissions are established.
 * This returns a version reference, not instructions or executable content. Bundle/file hashes must
 * still be checked by the artifact owner before the existing SkillFile.parse/Skill.prepare path.
 */
export function selected(db: DB, catalog: DB, input: { sessionID: string; scope: Scope; skillID: string }) {
  return Effect.gen(function* () {
    session(input.sessionID)
    const scope = scopeKey(input.scope)
    const selection = yield* db.get<{ content_sha: string; commit_sha: string; bundle_sha: string }>(
      sql`SELECT content_sha,commit_sha,bundle_sha FROM _watoom_skill_selection WHERE session_id=${input.sessionID} AND scope=${scope} AND skill_id=${input.skillID}`,
    )
    if (!selection) return yield* new Rejected({ message: "skill not selected for this session/scope" })
    const row = yield* approvedReference(catalog, input.skillID)
    if (
      !row ||
      row.sha256 !== selection.content_sha ||
      row.commit_sha !== selection.commit_sha ||
      row.bundle_sha !== selection.bundle_sha
    )
      return yield* new Rejected({ message: "selected skill version changed or approval revoked" })
    return {
      id: row.id,
      name: row.name,
      description: row.description,
      repo: row.repo,
      path: row.path,
      sha256: row.sha256,
      commit: row.commit_sha,
      bundleSha256: row.bundle_sha,
    }
  })
}
export function remove(db: DB, sessionID: string, scope: Scope, skillID: string) {
  session(sessionID)
  return db
    .run(
      sql`DELETE FROM _watoom_skill_selection WHERE session_id=${sessionID} AND scope=${scopeKey(scope)} AND skill_id=${skillID}`,
    )
    .pipe(Effect.asVoid)
}

/** Durable agent preferences are separate from session attachments and never execute instructions. */

export function approvedReference(catalog: DB, skillID: string) {
  return Effect.gen(function* () {
    const managed = yield* catalog.get(sql`SELECT name FROM sqlite_master WHERE name='_watoom_skill_review'`)
    const row = yield* catalog.get<Summary & { bundle_sha: string }>(
      managed
        ? sql`SELECT s.id,s.repo,s.path,s.name,s.description,COALESCE(r.content_sha,s.sha256) sha256,s.license,s.risk,s.validation,COALESCE(r.revision,src.commit_sha) commit_sha,ac.bundle_sha FROM skills s JOIN sources src ON src.repo=s.repo LEFT JOIN _watoom_skill_review r ON r.skill_id=s.id JOIN approvals a ON a.skill_id=s.id AND a.approved_sha=COALESCE(r.content_sha,s.sha256) JOIN approval_context ac ON ac.skill_id=s.id AND ac.commit_sha=COALESCE(r.revision,src.commit_sha) WHERE s.id=${skillID} AND s.validation='valid' AND (r.state IS NULL OR r.state='ENABLED')`
        : sql`SELECT s.id,s.repo,s.path,s.name,s.description,s.sha256,s.license,s.risk,s.validation,src.commit_sha,ac.bundle_sha FROM skills s JOIN sources src ON src.repo=s.repo JOIN approvals a ON a.skill_id=s.id AND a.approved_sha=s.sha256 JOIN approval_context ac ON ac.skill_id=s.id AND ac.commit_sha=src.commit_sha WHERE s.id=${skillID} AND s.validation='valid'`,
    )
    if (
      !row ||
      !/^[a-f0-9]{64}$/.test(row.sha256) ||
      !/^[a-f0-9]{40}$/.test(row.commit_sha) ||
      !/^[a-f0-9]{64}$/.test(row.bundle_sha)
    )
      return yield* new Rejected({ message: "unapproved or invalid pinned skill selection" })
    return row
  })
}
export function selectForAgent(db: DB, catalog: DB, input: { scope: Scope; skillID: string }) {
  return Effect.gen(function* () {
    const scope = scopeKey(input.scope)
    const row = yield* approvedReference(catalog, input.skillID)
    yield* db.run(
      sql`INSERT INTO _watoom_agent_skill_selection VALUES(${scope},${row.id},${row.sha256},${row.commit_sha},${row.bundle_sha}) ON CONFLICT(scope,skill_id) DO UPDATE SET content_sha=excluded.content_sha,commit_sha=excluded.commit_sha,bundle_sha=excluded.bundle_sha`,
    )
    return {
      id: row.id,
      sha256: row.sha256,
      commit: row.commit_sha,
      bundleSha256: row.bundle_sha,
      status: "SELECTED_NOT_EXECUTED" as const,
    }
  })
}
export function selectedForAgent(db: DB, catalog: DB, input: { scope: Scope; skillID: string }) {
  return Effect.gen(function* () {
    const scope = scopeKey(input.scope)
    const selection = yield* db.get<{ content_sha: string; commit_sha: string; bundle_sha: string }>(
      sql`SELECT content_sha,commit_sha,bundle_sha FROM _watoom_agent_skill_selection WHERE scope=${scope} AND skill_id=${input.skillID}`,
    )
    if (!selection) return yield* new Rejected({ message: "skill not selected for this agent/scope" })
    const row = yield* approvedReference(catalog, input.skillID)
    if (
      row.sha256 !== selection.content_sha ||
      row.commit_sha !== selection.commit_sha ||
      row.bundle_sha !== selection.bundle_sha
    )
      return yield* new Rejected({ message: "selected skill version changed or approval revoked" })
    return {
      id: row.id,
      name: row.name,
      description: row.description,
      repo: row.repo,
      path: row.path,
      sha256: row.sha256,
      commit: row.commit_sha,
      bundleSha256: row.bundle_sha,
    }
  })
}
export function removeForAgent(db: DB, scope: Scope, skillID: string) {
  return db
    .run(sql`DELETE FROM _watoom_agent_skill_selection WHERE scope=${scopeKey(scope)} AND skill_id=${skillID}`)
    .pipe(Effect.asVoid)
}

export type Browse = {
  view?: "installed" | "available" | "pending" | "disabled"
  sort?: "name" | "source"
  query?: string
  limit?: number
  offset?: number
  approvedOnly?: boolean
  license?: string
  repo?: string
  validOnly?: boolean
}
/** Human-facing metadata query. No raw instructions, companion content or executable source is returned. */
export function browse(db: DB, input: Browse = {}) {
  const query = input.query ?? "",
    limit = input.limit ?? 16,
    offset = input.offset ?? 0
  if (
    query.length > 256 ||
    !Number.isInteger(limit) ||
    limit < 1 ||
    limit > 32 ||
    !Number.isInteger(offset) ||
    offset < 0 ||
    offset > 10000 ||
    (input.license?.length ?? 0) > 128 ||
    (input.repo?.length ?? 0) > 256
  )
    return Effect.die(Error("catalog browse bounds"))
  const terms = query.match(/[\w-]+/g)?.slice(0, 8) ?? []
  const match = terms.map((x) => '"' + x + '"*').join(" AND ")

  return Effect.gen(function* () {
    const reviewTable = yield* db.get(sql`SELECT name FROM sqlite_master WHERE name='_watoom_skill_review'`)
    const reviewJoin = reviewTable
      ? sql`LEFT JOIN _watoom_skill_review r ON r.skill_id=s.id`
      : sql`LEFT JOIN (SELECT NULL skill_id, NULL state, NULL content_sha, NULL revision) r ON 1=0`
    const joins = sql`FROM skills s JOIN sources src ON src.repo=s.repo LEFT JOIN approvals a ON a.skill_id=s.id LEFT JOIN approval_context ac ON ac.skill_id=s.id ${reviewJoin}`
    const eligible = sql`a.approved_sha=COALESCE(r.content_sha,s.sha256) AND ac.commit_sha=COALESCE(r.revision,src.commit_sha) AND (r.state IS NULL OR r.state='ENABLED') AND s.validation='valid' AND length(s.sha256)=64 AND s.sha256 NOT GLOB '*[^0-9a-f]*' AND length(src.commit_sha)=40 AND src.commit_sha NOT GLOB '*[^0-9a-f]*' AND length(ac.bundle_sha)=64 AND ac.bundle_sha NOT GLOB '*[^0-9a-f]*'`
    const where = sql`${terms.length ? sql`AND s.id IN(SELECT id FROM skills_fts WHERE skills_fts MATCH ${match})` : sql``} ${input.approvedOnly !== false ? sql`AND ${eligible}` : sql``} ${input.validOnly ? sql`AND s.validation='valid'` : sql``} ${input.license ? sql`AND s.license=${input.license}` : sql``} ${input.repo ? sql`AND s.repo=${input.repo}` : sql``} ${input.view === "installed" ? sql`AND r.state IN ('INSTALLED','ENABLED','DISABLED')` : input.view === "disabled" ? sql`AND r.state='DISABLED'` : input.view === "pending" ? sql`AND COALESCE(r.state,'DISCOVERED') IN ('DISCOVERED','STAGED','REVIEWED','VALIDATED','APPROVED','UPDATED')` : sql``}`
    const counts = yield* db.get<{ discovered: number; validated: number; approved: number }>(
      sql`SELECT COUNT(*) discovered,COALESCE(SUM(s.validation='valid'),0) validated,COALESCE(SUM(CASE WHEN ${eligible} THEN 1 ELSE 0 END),0) approved ${joins}`,
    )
    const matched = yield* db.get<{ matched: number }>(sql`SELECT COUNT(*) matched ${joins} WHERE 1=1 ${where}`)
    const rows = yield* db.all<Summary & { validation: string }>(
      sql`SELECT s.id,s.repo,s.path,s.name,substr(s.description,1,2048) description,COALESCE(r.content_sha,s.sha256) sha256,COALESCE(r.revision,src.commit_sha) commit_sha,s.license,substr(s.risk,1,4096) risk,s.validation,CASE WHEN ${eligible} THEN 1 ELSE 0 END approved,ac.bundle_sha ${joins} WHERE 1=1 ${where} ORDER BY ${input.sort === "source" ? sql`s.repo,s.name` : sql`s.name,s.id`} LIMIT ${limit} OFFSET ${offset}`,
    )
    const states = reviewTable
      ? yield* db.all<{ skill_id: string; state: string }>(
          sql`SELECT skill_id,state FROM _watoom_skill_review WHERE skill_id IN (${sql.join(
            rows.map((row) => sql`${row.id}`),
            sql`,`,
          )})`,
        )
      : []
    const stateMap = new Map(states.map((row) => [row.skill_id, row.state]))
    const referenceTable = yield* db.get(sql`SELECT name FROM sqlite_master WHERE name='external_links'`)
    const references =
      referenceTable && input.view !== "installed" && input.view !== "disabled"
        ? yield* db.all<{ url: string; discovered_in: string; state: string }>(
            sql`SELECT url,discovered_in,state FROM external_links WHERE instr(lower(url || ' ' || discovered_in),lower(${query}))>0 ORDER BY url LIMIT ${limit} OFFSET ${offset}`,
          )
        : []
    const referenceMatched =
      referenceTable && input.view !== "installed" && input.view !== "disabled"
        ? yield* db.get<{ matched: number }>(
            sql`SELECT count(*) matched FROM external_links WHERE instr(lower(url || ' ' || discovered_in),lower(${query}))>0`,
          )
        : undefined
    return {
      enabled: true,
      discovered: counts?.discovered ?? 0,
      validated: counts?.validated ?? 0,
      approved: counts?.approved ?? 0,
      matched: matched?.matched ?? 0,
      offset,
      references,
      referenceMatched: referenceMatched?.matched ?? 0,
      rows: rows.map((row) => ({
        ...row,
        state: stateMap.get(row.id) ?? (row.approved ? "ENABLED" : "DISCOVERED"),
        classification: row.validation === "valid" ? "SKILL" : "KNOWLEDGE_REFERENCE",
      })),
    }
  })
}

export function selectionReferences(db: DB, scope: Scope, sessionID?: string) {
  if (sessionID !== undefined) session(sessionID)
  const key = scopeKey(scope)
  return sessionID === undefined
    ? db.all<{ skill_id: string; content_sha: string; commit_sha: string; bundle_sha: string }>(
        sql`SELECT skill_id,content_sha,commit_sha,bundle_sha FROM _watoom_agent_skill_selection WHERE scope=${key} ORDER BY skill_id LIMIT 32`,
      )
    : db.all<{ skill_id: string; content_sha: string; commit_sha: string; bundle_sha: string }>(
        sql`SELECT skill_id,content_sha,commit_sha,bundle_sha FROM _watoom_skill_selection WHERE scope=${key} AND session_id=${sessionID} ORDER BY skill_id LIMIT 32`,
      )
}

// Legacy library exports refer to the registered native migrations; no runtime-local migration owner.
export { migration, agentMigration }
