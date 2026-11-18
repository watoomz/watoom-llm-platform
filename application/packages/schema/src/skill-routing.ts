import { Schema } from "effect"
export * as SkillRouting from "./skill-routing.js"
export type Source = { id: string; name: string; description?: string; content: string; autoinvoke?: boolean }
export type Entry = {
  id: string
  name: string
  description: string
  kind: "skill" | "pipeline"
  pipelineID?: string
  category?: string
  aliases: string[]
  requires: string[]
  availability: string
  autoinvoke: boolean
}
export type Match = Entry & { score: number; matched: string[]; explicit: boolean; missing: string[] }
const stop = new Set(
  "a an and are as at be by can could do for from have help how i in into is it me my of on or our please that the their then this to use using want we what with would you your watoom".split(
    " ",
  ),
)
const aliases: Record<string, string> = {
  images: "image",
  illustration: "image",
  illustrations: "image",
  illustrate: "image",
  illustrating: "image",
  drawing: "image",
  draw: "image",
  comics: "comic",
  writing: "write",
  written: "write",
  writes: "write",
  stories: "story",
  animations: "animation",
  animate: "animation",
  animated: "animation",
  rendering: "render",
  renders: "render",
  models: "model",
  skills: "skill",
  pipelines: "pipeline",
  rigging: "rig",
  rigged: "rig",
  exports: "export",
  exporting: "export",
  exported: "export",
  meshes: "mesh",
  characters: "character",
  documents: "document",
}
export function tokens(text: string) {
  return (
    text
      .normalize("NFKD")
      .replace(/\p{M}/gu, "")
      .toLowerCase()
      .match(/[\p{L}\p{N}]+/gu) ?? []
  )
    .map((x) => aliases[x] ?? x)
    .filter((x) => x.length > 1 && !stop.has(x))
}
const strings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.length <= 64 && value.every((x) => typeof x === "string" && x.length <= 128)
export function catalogue(sources: readonly Source[]): Entry[] {
  return sources.map((source) => {
    const documents = [...source.content.matchAll(/```(?:prompt-builder|skill-routing)\s*\n([\s\S]*?)\n```/g)].flatMap(
      (match) => {
        try {
          const value: unknown = JSON.parse(match[1]!)
          return value && typeof value === "object" && !Array.isArray(value) ? [value] : []
        } catch {
          return []
        }
      },
    ) as Record<string, unknown>[]
    const pipeline = documents.find((x) => x.kind === "pipeline"),
      metadata = documents.find((x) => x.kind !== "pipeline") ?? pipeline
    const prose =
      source.content
        .replace(/^---[\s\S]*?---\s*/, "")
        .split("\n")
        .filter((line) => line.trim() && !line.startsWith("#") && !line.startsWith("<!--"))[0] ?? ""
    const description = typeof pipeline?.description === "string" ? pipeline.description : (source.description ?? prose)
    return {
      id: source.id,
      name: source.name,
      description: description.replace(/\s+/g, " ").slice(0, 360),
      kind: pipeline ? "pipeline" : "skill",
      ...(typeof pipeline?.id === "string" ? { pipelineID: pipeline.id } : {}),
      ...(typeof pipeline?.category === "string" ? { category: pipeline.category } : {}),
      aliases: strings(metadata?.aliases) ? metadata.aliases : strings(pipeline?.keywords) ? pipeline.keywords : [],
      requires: strings(metadata?.requires) ? metadata.requires : [],
      availability: typeof pipeline?.availability === "string" ? pipeline.availability : "installed",
      autoinvoke: source.autoinvoke !== false,
    }
  })
}
export function rank(query: string, entries: readonly Entry[], limit = 12, sources: readonly Source[] = []): Match[] {
  const terms = [...new Set(tokens(query))].slice(0, 96),
    normalized = " " + tokens(query).join(" ") + " "
  const sourceText = new Map(sources.map((source) => [source.id, new Set(tokens(source.content.slice(0, 12000)))]))
  const documents = entries.map((entry) => ({
    entry,
    terms: new Set(tokens([entry.id, entry.name, entry.description, ...entry.aliases].join(" "))),
  }))
  const frequency = new Map(
      terms.map((term) => [
        term,
        documents.filter((doc) => doc.terms.has(term) || sourceText.get(doc.entry.id)?.has(term)).length,
      ]),
    ),
    ids = new Set(entries.map((entry) => entry.id))
  return documents
    .map(({ entry, terms: words }) => {
      const explicit =
        query.toLowerCase().includes("$" + entry.id.toLowerCase()) ||
        query.toLowerCase().includes("skill:" + entry.id.toLowerCase()) ||
        (!!entry.pipelineID && query.toLowerCase().includes("pipeline:" + entry.pipelineID))
      const nameTerms = new Set(tokens(entry.id + " " + entry.name)),
        matched = terms.filter((term) => words.has(term) || sourceText.get(entry.id)?.has(term))
      const phrase = entry.aliases.some(
        (value) => tokens(value).length > 1 && normalized.includes(" " + tokens(value).join(" ") + " "),
      )
      const negated = entry.aliases
        .concat([entry.id, entry.name])
        .some(
          (name) =>
            query.toLowerCase().includes("without " + name.toLowerCase()) ||
            query.toLowerCase().includes("do not use " + name.toLowerCase()) ||
            query.toLowerCase().includes("don't use " + name.toLowerCase()),
        )
      const excluded = [
        ...query.toLowerCase().matchAll(/(?:without|avoid|do not use|don\x27t use)\s+([a-z0-9-]+)/g),
      ].flatMap((match) => tokens(match[1]!))
      const excludedDomain = excluded.some((term) => nameTerms.has(term))
      const score =
        negated || excludedDomain
          ? -1
          : (explicit ? 100 : 0) +
            (phrase ? 10 : 0) +
            matched.reduce(
              (sum, term) =>
                sum +
                Math.log(1 + (entries.length + 1) / ((frequency.get(term) ?? 0) + 1)) *
                  (nameTerms.has(term) ? 2 : words.has(term) ? 1 : 0.65) *
                  (["fix", "make", "create", "generate", "keep"].includes(term) ? 0.3 : 1),
              0,
            )
      return {
        ...entry,
        score: Math.round(score * 100) / 100,
        matched,
        explicit,
        missing: entry.requires.filter((id) => !ids.has(id)),
      }
    })
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id))
    .slice(0, Math.max(1, Math.min(32, limit)))
}
export function plan(matches: readonly Match[], entries: readonly Entry[], primaryLimit = 3) {
  const index = new Map(entries.map((entry) => [entry.id, entry])),
    ordered: Entry[] = [],
    errors: string[] = []
  const seen = new Set<string>()
  const eligible = matches.filter(
    (item) => (item.autoinvoke || item.explicit) && (item.explicit || item.matched.length >= 2),
  )
  const best = matches[0]?.score ?? 0
  const categories = new Set<string>()
  const pipelines = eligible
    .filter((item) => {
      const category = item.category ?? "pipeline"
      if (item.kind !== "pipeline" || item.score < best * 0.25 || categories.has(category)) return false
      categories.add(category)
      return true
    })
    .slice(0, 2)
  const seeds = [
    ...eligible.filter((item) => item.explicit),
    ...pipelines,
    ...eligible.filter((item) => item.score >= best * 0.4),
  ]
    .filter((item, index, list) => list.findIndex((other) => other.id === item.id) === index)
    .slice(0, primaryLimit)
  for (const match of seeds) {
    const local: Entry[] = [],
      visiting = new Set<string>(),
      done = new Set<string>()
    function visit(id: string): boolean {
      if (seen.has(id) || done.has(id)) return true
      if (visiting.has(id)) {
        errors.push("dependency-cycle:" + id)
        return false
      }
      const entry = index.get(id)
      if (!entry) {
        errors.push("missing-skill:" + id)
        return false
      }
      if (!["installed", "available", "ready"].includes(entry.availability)) {
        errors.push("unavailable-skill:" + id)
        return false
      }
      if (!entry.autoinvoke && id !== match.id) {
        errors.push("explicit-only-dependency:" + id)
        return false
      }
      visiting.add(id)
      const valid = entry.requires.map(visit).every(Boolean)
      visiting.delete(id)
      if (valid) {
        done.add(id)
        local.push(entry)
      }
      return valid
    }
    if (visit(match.id) && ordered.length + local.length <= 8)
      for (const entry of local) {
        seen.add(entry.id)
        ordered.push(entry)
      }
  }
  return { skills: ordered, errors }
}
export const EntrySchema = Schema.Struct({
  id: Schema.String,
  name: Schema.String,
  description: Schema.String,
  kind: Schema.Literals(["skill", "pipeline"]),
  pipelineID: Schema.optional(Schema.String),
  category: Schema.optional(Schema.String),
  aliases: Schema.Array(Schema.String),
  requires: Schema.Array(Schema.String),
  availability: Schema.String,
  autoinvoke: Schema.Boolean,
})
export const SearchSchema = Schema.Struct({
  catalogueSize: Schema.Number,
  entries: Schema.Array(EntrySchema),
  ranked: Schema.Boolean,
})

export const SearchInput = Schema.Struct({
  offset: Schema.optional(Schema.Number.check(Schema.isInt(), Schema.isBetween({ minimum: 0, maximum: 10000 }))),
  query: Schema.String.check(Schema.isMinLength(1), Schema.isMaxLength(4096)),
  limit: Schema.optional(
    Schema.Union([Schema.Number, Schema.NumberFromString]).check(
      Schema.isInt(),
      Schema.isBetween({ minimum: 1, maximum: 32 }),
    ),
  ),
})
