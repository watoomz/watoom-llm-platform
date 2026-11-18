export * as SkillAdministration from "./skill-administration.js"
import { Schema } from "effect"
import { Permission } from "./permission.js"
export const Request = Schema.Struct({
  skillID: Schema.String.check(Schema.isMinLength(1), Schema.isMaxLength(512)),
  action: Schema.Literals([
    "approve",
    "reject",
    "revoke",
    "disable",
    "install",
    "enable",
    "update",
    "stage",
    "review",
    "validate",
    "rollback",
  ]),
  sha256: Schema.String.check(Schema.isPattern(/^[a-f0-9]{64}$/)),
  revision: Schema.String.check(Schema.isPattern(/^[a-f0-9]{40}$/)),
  bundleSha256: Schema.String.check(Schema.isPattern(/^[a-f0-9]{64}$/)),
  permissions: Permission.Ruleset,
  tools: Schema.Array(Schema.String).check(Schema.isMaxLength(32)),
  riskApproved: Schema.optionalKey(Schema.Boolean),
  dryRun: Schema.optionalKey(Schema.Boolean),
}).annotate({ identifier: "SkillAdministration.Request" })
export type Request = typeof Request.Type
export const Receipt = Schema.Struct({
  state: Schema.String,
  reviewer: Schema.String,
  skillID: Schema.String,
  sha256: Schema.String,
  revision: Schema.String,
  bundleSha256: Schema.String,
}).annotate({ identifier: "SkillAdministration.Receipt" })

export type Receipt = typeof Receipt.Type
