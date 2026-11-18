export * as SpecialistConfig from "./specialists.js"
import { Schema } from "effect"
export const Entry = Schema.Struct({ descriptor: Schema.Json, backend: Schema.Literals(["toolkit-3d", "local-http"]), url: Schema.String, artifactRoot: Schema.String, tokenEnv: Schema.optionalKey(Schema.String) })
export const Info = Schema.Struct({ entries: Schema.Array(Entry).check(Schema.isMaxLength(32)) }).annotate({ identifier: "SpecialistConfig.Info" })
export type Entry = typeof Entry.Type
