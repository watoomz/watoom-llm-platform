export * as SkillDetail from "./skill-detail.js"
import { Effect } from "effect"
import { sql } from "drizzle-orm"
import { sqliteLayer } from "#sqlite"
import { EffectDrizzleSqlite } from "../database/drizzle.js"
import { SkillReview } from "./skill-review.js"
import { Catalog } from "./catalog.js"
export function inspect(settings: { database: string; artifacts?: string; collection?: string }, skillID: string) {
  return Effect.gen(function* () {
    const db = yield* EffectDrizzleSqlite.makeWithDefaults()
    const row = yield* db.get<SkillReview.Row & { name: string; description: string; license: string; risk: string }>(
      sql`SELECT s.id,s.repo,s.path,s.name,s.description,s.sha256,s.validation,s.license,s.risk,src.commit_sha FROM skills s JOIN sources src ON src.repo=s.repo WHERE s.id=${skillID}`,
    )
    if (!row) return yield* new Catalog.Rejected({ message: "Unknown skill" })
    const table = yield* db.get(sql`SELECT name FROM sqlite_master WHERE name='_watoom_skill_review'`)
    const prior = table
      ? yield* db.get<{ state: string; bundle_sha: string; content_sha: string; revision: string }>(
          sql`SELECT state,bundle_sha,content_sha,revision FROM _watoom_skill_review WHERE skill_id=${skillID}`,
        )
      : undefined
    const history = table
      ? yield* db.all<{ record: string }>(
          sql`SELECT record FROM _watoom_skill_review_history WHERE skill_id=${skillID} ORDER BY id DESC LIMIT 128`,
        )
      : []
    const seen = new Set<string>()
    const versions = history
      .map(
        (item) =>
          JSON.parse(item.record) as {
            sha256: string
            revision: string
            bundleSha256: string
            state: string
            tools?: string[]
          },
      )
      .filter(
        (item) =>
          ["INSTALLED", "ENABLED"].includes(item.state) &&
          !seen.has(item.bundleSha256) &&
          !!seen.add(item.bundleSha256),
      )
      .map(({ sha256, revision, bundleSha256, state, tools }) => ({
        sha256,
        revision,
        bundleSha256,
        state,
        tools: tools ?? [],
      }))
    const attributes = yield* db.get(sql`SELECT name FROM sqlite_master WHERE name='skill_attributes'`)
    const metadata = attributes
      ? yield* db.get<{ categories: string; frameworks: string; classification: string }>(
          sql`SELECT categories,frameworks,classification FROM skill_attributes WHERE skill_id=${skillID}`,
        )
      : undefined
    const source = settings.collection ?? settings.artifacts
    const result = source
      ? yield* Effect.tryPromise(() => SkillReview.inspect(source, row)).pipe(
          Effect.map((value) => ({ value, error: "" })),
          Effect.catch((error) => Effect.succeed({ value: undefined, error: String(error.cause) })),
        )
      : { value: undefined, error: "Source collection unavailable" }
    const activeRecord = prior
      ? history
          .map((item) => JSON.parse(item.record) as { bundleSha256: string; tools?: string[] })
          .find((item) => item.bundleSha256 === prior.bundle_sha)
      : undefined
    const activeTools = activeRecord?.tools ?? []
    const installed =
      prior && settings.artifacts && ["INSTALLED", "ENABLED", "DISABLED"].includes(prior.state)
        ? yield* SkillReview.verify(
            settings.artifacts,
            { ...row, sha256: prior.content_sha, commit_sha: prior.revision },
            prior.bundle_sha,
            activeTools,
          ).pipe(
            Effect.map((skill) => ({ instructions: skill.content, error: "" })),
            Effect.catch(() =>
              Effect.succeed({ instructions: "", error: "Installed version failed artifact verification" }),
            ),
          )
        : { instructions: "", error: "" }
    const columns = yield* db.all<{ name: string }>(sql`PRAGMA table_info(skills)`)
    const raw = columns.some((column) => column.name === "raw")
      ? yield* db.get<{ raw: string }>(sql`SELECT substr(raw,1,65536) raw FROM skills WHERE id=${skillID}`)
      : undefined
    return {
      entry: {
        ...row,
        approved: prior?.state === "ENABLED" ? 1 : 0,
        bundle_sha: prior?.bundle_sha ?? null,
        state: prior?.state ?? "DISCOVERED",
        classification: result.value?.executable.length
          ? "EXECUTABLE_TOOL"
          : row.validation === "valid"
            ? "SKILL"
            : "KNOWLEDGE_REFERENCE",
      },
      instructions: result.value?.instructions ?? raw?.raw ?? "",
      bundleSha256: result.value?.bundleSha256 ?? "",
      tools: result.value?.tools ?? [],
      risks: result.value?.risks ?? [],
      files: [...(result.value?.files.keys() ?? [])],
      categories: metadata?.categories ?? "UNKNOWN",
      compatibility: metadata ? metadata.classification + " · " + metadata.frameworks : "UNKNOWN",
      valid: result.value?.valid ?? false,
      error: [result.error, installed.error].filter(Boolean).join("; "),
      installedInstructions: installed.instructions,
      activeTools,
      activeVersion: prior
        ? { sha256: prior.content_sha, revision: prior.revision, bundleSha256: prior.bundle_sha }
        : null,
      versions,
    }
  }).pipe(
    Effect.provide(
      sqliteLayer({ filename: settings.database, readonly: true, readwrite: false, create: false, disableWAL: true }),
    ),
    Effect.scoped,
    Effect.mapError((error) =>
      error instanceof Catalog.Rejected ? error : new Catalog.Rejected({ message: "Skill details unavailable" }),
    ),
  )
}
