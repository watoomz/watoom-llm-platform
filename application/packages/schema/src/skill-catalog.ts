export * as SkillCatalog from "./skill-catalog.js"

import { Schema } from "effect"
export const Entry = Schema.Struct({
  id: Schema.String,
  repo: Schema.String,
  path: Schema.String,
  name: Schema.String,
  description: Schema.String,
  sha256: Schema.String,
  commit_sha: Schema.String,
  license: Schema.String,
  risk: Schema.String,
  validation: Schema.String,
  approved: Schema.Number,
  bundle_sha: Schema.NullOr(Schema.String),
  state: Schema.optionalKey(Schema.String),
  classification: Schema.optionalKey(Schema.String),
}).annotate({ identifier: "SkillCatalog.Entry" })
export type Entry = typeof Entry.Type
export const Page = Schema.Struct({
  enabled: Schema.Boolean,
  discovered: Schema.Number,
  validated: Schema.Number,
  approved: Schema.Number,
  matched: Schema.Number,
  offset: Schema.Number,
  referenceMatched: Schema.optionalKey(Schema.Number),
  references: Schema.optionalKey(
    Schema.Array(Schema.Struct({ url: Schema.String, discovered_in: Schema.String, state: Schema.String })),
  ),
  rows: Schema.Array(Entry),
}).annotate({ identifier: "SkillCatalog.Page" })
export type Page = typeof Page.Type
export const Config = Schema.Struct({
  database: Schema.String,
  artifacts: Schema.optional(Schema.String),
  administration: Schema.optionalKey(Schema.Boolean),
  collection: Schema.optionalKey(Schema.String),
}).annotate({
  identifier: "SkillCatalog.Config",
})

export const Selection = Schema.Struct({
  id: Schema.String,
  sha256: Schema.String,
  commit: Schema.String,
  bundleSha256: Schema.String,
  status: Schema.Literals(["SELECTED_NOT_EXECUTED", "REVOKED", "BLOCKED"]),
  name: Schema.optional(Schema.String),
  description: Schema.optional(Schema.String),
}).annotate({ identifier: "SkillCatalog.Selection" })
export type Selection = typeof Selection.Type

export const Detail = Schema.Struct({
  entry: Entry,
  instructions: Schema.String,
  installedInstructions: Schema.String,
  activeTools: Schema.Array(Schema.String),
  bundleSha256: Schema.String,
  tools: Schema.Array(Schema.String),
  risks: Schema.Array(Schema.String),
  files: Schema.Array(Schema.String),
  categories: Schema.String,
  compatibility: Schema.String,
  valid: Schema.Boolean,
  error: Schema.String,
  activeVersion: Schema.NullOr(
    Schema.Struct({ sha256: Schema.String, revision: Schema.String, bundleSha256: Schema.String }),
  ),
  versions: Schema.Array(
    Schema.Struct({
      sha256: Schema.String,
      revision: Schema.String,
      bundleSha256: Schema.String,
      state: Schema.String,
      tools: Schema.Array(Schema.String),
    }),
  ),
}).annotate({ identifier: "SkillCatalog.Detail" })

export type Detail = typeof Detail.Type
