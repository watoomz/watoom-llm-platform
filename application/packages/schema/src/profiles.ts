export * as ProfileSchema from "./profiles.js"
import { Schema } from "effect"
export const Capability = Schema.Struct({ id: Schema.String, tools: Schema.Array(Schema.String), dependencies: Schema.Array(Schema.String), permission: Schema.Literals(["allow", "ask"]), optional: Schema.Boolean })
export const Manifest = Schema.Struct({ id: Schema.String, version: Schema.String, extends: Schema.Array(Schema.String), capabilities: Schema.Array(Schema.String), skills: Schema.Array(Schema.String) })
export const Availability = Schema.Struct({ id: Schema.String, status: Schema.Literals(["READY", "REQUIRES_CONFIGURATION", "UNAVAILABLE", "EXPERIMENTAL"]), missing: Schema.Array(Schema.String) })
export const Catalog = Schema.Struct({ profiles: Schema.Array(Manifest), capabilities: Schema.Array(Capability), available: Schema.Array(Schema.String), selected: Schema.Array(Schema.String), components: Schema.Array(Schema.String), disabled: Schema.Array(Schema.String), transaction: Schema.String, statuses: Schema.Array(Availability) })
export const Resolution = Schema.Struct({
  version: Schema.Literal(1), selected: Schema.Array(Schema.String), components: Schema.Array(Schema.String), disabled: Schema.Array(Schema.String), statuses: Schema.Array(Availability), profiles: Schema.Array(Schema.Struct({ id: Schema.String, version: Schema.String })),
  capabilities: Schema.Array(Capability), skills: Schema.Array(Schema.String), sha256: Schema.String,
  unavailable: Schema.Array(Schema.Struct({ id: Schema.String, dependencies: Schema.Array(Schema.String), optional: Schema.Boolean })),
  status: Schema.String, transaction: Schema.optionalKey(Schema.String), configPath: Schema.String,
})
export const Install = Schema.Struct({ profiles: Schema.Array(Schema.String).check(Schema.isMinLength(1), Schema.isMaxLength(7)), dryRun: Schema.optionalKey(Schema.Boolean), components: Schema.optionalKey(Schema.Array(Schema.String).check(Schema.isMaxLength(32))), disabled: Schema.optionalKey(Schema.Array(Schema.String).check(Schema.isMaxLength(32))) })
export const Rollback = Schema.Struct({ transaction: Schema.String.check(Schema.isPattern(/^[a-f0-9-]{36}$/)) })
