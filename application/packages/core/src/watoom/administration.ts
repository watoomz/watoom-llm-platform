export * as SkillAdministration from "./administration.js"
import { Effect } from "effect"
import { sql } from "drizzle-orm"
import { sqliteLayer } from "#sqlite"
import { EffectDrizzleSqlite } from "../database/drizzle.js"
import { SkillReview } from "./skill-review.js"
import { Catalog } from "./catalog.js"
import { SkillAdministration } from "@opencode/schema/skill-administration"
type Settings = { database: string; artifacts: string; collection?: string }
export function execute(settings: Settings, reviewer: string, input: SkillAdministration.Request) {
  return Effect.gen(function* () {
    const db = yield* EffectDrizzleSqlite.makeWithDefaults()
    return yield* db.transaction(
      () =>
        Effect.gen(function* () {
          yield* db.run(
            sql`CREATE TABLE IF NOT EXISTS _watoom_skill_review(skill_id TEXT PRIMARY KEY,revision TEXT NOT NULL,content_sha TEXT NOT NULL,bundle_sha TEXT NOT NULL,permissions TEXT NOT NULL,reviewer TEXT NOT NULL,state TEXT NOT NULL,at TEXT NOT NULL)`,
          )
          yield* db.run(
            sql`CREATE TABLE IF NOT EXISTS _watoom_skill_review_history(id INTEGER PRIMARY KEY,skill_id TEXT NOT NULL,record TEXT NOT NULL)`,
          )
          const row = yield* db.get<SkillReview.Row>(
            sql`SELECT s.id,s.repo,s.path,s.sha256,s.validation,s.risk,src.commit_sha FROM skills s JOIN sources src ON src.repo=s.repo WHERE s.id=${input.skillID}`,
          )
          if (!row) return yield* new Catalog.Rejected({ message: "Unknown skill" })
          const prior = yield* db.get<{
            permissions: string
            bundle_sha: string
            content_sha: string
            revision: string
            state: string
          }>(
            sql`SELECT permissions,bundle_sha,content_sha,revision,state FROM _watoom_skill_review WHERE skill_id=${row.id}`,
          )
          const historical =
            input.action === "rollback"
              ? yield* db.all<{ record: string }>(
                  sql`SELECT record FROM _watoom_skill_review_history WHERE skill_id=${row.id} ORDER BY id DESC LIMIT 128`,
                )
              : []
          const restored = historical
            .map(
              (item) =>
                JSON.parse(item.record) as SkillAdministration.Receipt & { permissions?: string; tools?: string[] },
            )
            .find(
              (item) =>
                item.sha256 === input.sha256 &&
                item.revision === input.revision &&
                item.bundleSha256 === input.bundleSha256 &&
                ["ENABLED", "INSTALLED"].includes(item.state),
            )
          const pin =
            input.action === "rollback" && restored
              ? { ...row, sha256: restored.sha256, commit_sha: restored.revision }
              : ["enable", "disable", "revoke", "install"].includes(input.action) && prior
                ? { ...row, sha256: prior.content_sha, commit_sha: prior.revision }
                : row
          if (pin.sha256 !== input.sha256 || pin.commit_sha !== input.revision)
            return yield* new Catalog.Rejected({ message: "Stale or unknown skill revision" })
          const permissions = JSON.stringify(input.permissions)
          const preview = ["stage", "review", "validate", "approve", "update"].includes(input.action)
            ? yield* Effect.tryPromise(() => SkillReview.inspect(settings.collection ?? settings.artifacts, row))
            : undefined
          // Quarantine/review is not execution eligibility. Only this known,
          // structurally valid integration gap may enter the review lifecycle.
          const reviewOnly =
            preview &&
            ["stage", "review"].includes(input.action) &&
            row.validation === "valid" &&
            preview.executable.length > 0 &&
            preview.risks.every((risk) =>
              ["executable-components-require-separate-integration", "elevated-operations"].includes(risk),
            )
          if (
            preview &&
            ((!preview.valid && !reviewOnly) ||
              preview.bundleSha256 !== input.bundleSha256 ||
              JSON.stringify(preview.tools) !== JSON.stringify(input.tools))
          )
            return yield* new Catalog.Rejected({
              message: "Source validation, security, dependencies or bundle pin failed",
            })
          if (preview?.risks.length && !input.riskApproved)
            return yield* new Catalog.Rejected({ message: "Explicit elevated-risk review approval required" })
          const required: Record<string, string[]> = {
            review: ["STAGED"],
            validate: ["REVIEWED"],
            approve: ["VALIDATED"],
            update: ["VALIDATED"],
            install: ["APPROVED", "UPDATED"],
            enable: ["INSTALLED", "DISABLED"],
          }
          if (
            required[input.action] &&
            (!prior ||
              !required[input.action]!.includes(prior.state) ||
              prior.permissions !== permissions ||
              prior.bundle_sha !== input.bundleSha256 ||
              prior.content_sha !== input.sha256 ||
              prior.revision !== input.revision)
          )
            return yield* new Catalog.Rejected({
              message: "Complete staged review, validation, approval and installation in order",
            })
          if (
            input.action === "rollback" &&
            (!restored ||
              restored.permissions !== permissions ||
              JSON.stringify(restored.tools ?? []) !== JSON.stringify(input.tools))
          )
            return yield* new Catalog.Rejected({
              message: "Previous verified installation with matching reviewed dependencies required",
            })
          if (["disable", "revoke"].includes(input.action) && !prior)
            return yield* new Catalog.Rejected({ message: "No managed installation" })
          if (preview && !input.dryRun)
            yield* Effect.tryPromise(() => SkillReview.stage(settings.artifacts, row, preview))
          if (
            !["reject", "revoke", "disable"].includes(input.action) &&
            (!preview || input.action !== "stage" || !input.dryRun)
          )
            yield* SkillReview.verify(settings.artifacts, pin, input.bundleSha256, input.tools)
          const state = (
            {
              stage: "STAGED",
              review: "REVIEWED",
              validate: "VALIDATED",
              approve: "APPROVED",
              update: "UPDATED",
              reject: "REJECTED",
              revoke: "REVOKED",
              disable: "DISABLED",
              install: "INSTALLED",
              enable: "ENABLED",
              rollback: "ENABLED",
            } as const
          )[input.action]
          const record = {
            state,
            reviewer,
            skillID: row.id,
            sha256: pin.sha256,
            revision: pin.commit_sha,
            bundleSha256: input.bundleSha256,
            permissions,
            tools: input.tools,
            riskApproved: input.riskApproved === true,
            risks: preview?.risks ?? [],
          }
          if (input.dryRun) return { ...record, state: "PREVIEW" }
          if (state === "ENABLED") {
            yield* db.run(
              sql`INSERT INTO approvals(skill_id,approved_sha,note,at) VALUES(${row.id},${pin.sha256},${"reviewer=" + reviewer},${new Date().toISOString()}) ON CONFLICT(skill_id) DO UPDATE SET approved_sha=excluded.approved_sha,note=excluded.note,at=excluded.at`,
            )
            yield* db.run(
              sql`INSERT INTO approval_context(skill_id,commit_sha,bundle_sha) VALUES(${row.id},${pin.commit_sha},${input.bundleSha256}) ON CONFLICT(skill_id) DO UPDATE SET commit_sha=excluded.commit_sha,bundle_sha=excluded.bundle_sha`,
            )
          } else {
            yield* db.run(sql`DELETE FROM approvals WHERE skill_id=${row.id}`)
            yield* db.run(sql`DELETE FROM approval_context WHERE skill_id=${row.id}`)
          }
          yield* db.run(
            sql`INSERT INTO _watoom_skill_review VALUES(${row.id},${pin.commit_sha},${pin.sha256},${input.bundleSha256},${permissions},${reviewer},${state},${new Date().toISOString()}) ON CONFLICT(skill_id) DO UPDATE SET revision=excluded.revision,content_sha=excluded.content_sha,bundle_sha=excluded.bundle_sha,permissions=excluded.permissions,reviewer=excluded.reviewer,state=excluded.state,at=excluded.at`,
          )
          yield* db.run(
            sql`INSERT INTO _watoom_skill_review_history(skill_id,record) VALUES(${row.id},${JSON.stringify(record)})`,
          )
          return record
        }),
      { behavior: "immediate" },
    )
  }).pipe(
    Effect.provide(sqliteLayer({ filename: settings.database, create: false, disableWAL: true })),
    Effect.scoped,
    Effect.mapError((error) =>
      error instanceof Catalog.Rejected
        ? error
        : new Catalog.Rejected({
            message: "Skill source, validation or storage unavailable; no lifecycle state committed",
          }),
    ),
    Effect.catchDefect(() =>
      Effect.fail(new Catalog.Rejected({ message: "Skill administration failed; transaction rolled back" })),
    ),
  )
}
