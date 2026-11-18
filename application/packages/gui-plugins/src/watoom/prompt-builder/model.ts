import { Option, Schema } from "effect"
import { SkillRouting } from "@opencode/schema/skill-routing"

export type Field = { id: string; label: string; help: string; required: boolean; default?: string }

export type Recipe = {
  version: 1
  kind: "pipeline"
  id: string
  title: string
  category: string
  availability: string
  keywords: string[]
  fields: Field[]
  format?: {
    kind: "prose-tags"
    descriptionField: string
    positiveFields: string[]
    negativeFields: string[]
    positiveLabel: string
    negativeLabel: string
    settingsLabel: string
  }
  skill: string
  guidance: string
}

export type Creator = { version: 1; kind: "creator"; instructions: string[]; skill: string }

export type SkillInput = { name: string; content: string }

const Id = Schema.String.check(Schema.isPattern(/^[a-z0-9-]+$/))

const Strings = Schema.Array(Schema.String)

// Each prompt-builder block is decoded in stages, so a broken block reports which part of its contract failed.
const Versioned = Schema.Struct({ version: Schema.Literal(1) })

const CreatorDoc = Schema.Struct({
  kind: Schema.Literal("creator"),
  instructions: Strings.check(Schema.isMinLength(1)),
})

const PipelineDoc = Schema.Struct({
  kind: Schema.Literal("pipeline"),
  id: Id,
  title: Schema.String,
  category: Schema.String,
  availability: Schema.String,
  keywords: Strings,
  fields: Schema.Array(Schema.Unknown),
  format: Schema.optional(Schema.Unknown),
})

const FieldDoc = Schema.Struct({
  id: Id,
  label: Schema.String,
  help: Schema.String,
  required: Schema.Boolean,
  default: Schema.optional(Schema.String),
})

const FormatDoc = Schema.Struct({
  kind: Schema.Literal("prose-tags"),
  descriptionField: Schema.String,
  positiveFields: Strings,
  negativeFields: Strings,
  positiveLabel: Schema.String,
  negativeLabel: Schema.String,
  settingsLabel: Schema.String,
})

const decodeVersioned = Schema.decodeUnknownOption(Versioned)

const decodeCreator = Schema.decodeUnknownOption(CreatorDoc)

const decodePipeline = Schema.decodeUnknownOption(PipelineDoc)

const decodeField = Schema.decodeUnknownOption(FieldDoc)

const decodeFormat = Schema.decodeUnknownOption(FormatDoc)

/** The contract error a failed decode stage throws. */
const fail = (code: string) => () => new Error(code)

export async function loadPromptSkills(load: () => Promise<SkillInput[]>) {
  for (let attempt = 0; attempt < 40; attempt++) {
    const skills = await load()

    if (skills.length || attempt === 39) return readPromptSkills(skills)
    await new Promise((resolve) => setTimeout(resolve, 250))
  }

  throw new Error("PROMPT_SKILL_CATALOG")
}

export function readPromptSkills(skills: SkillInput[]) {
  const recipes: Recipe[] = []
  const creators: Creator[] = []

  for (const skill of skills.filter((x) => x.name.startsWith("watoom-prompt-"))) {
    const match = /```prompt-builder\s*\n([\s\S]*?)\n```/.exec(skill.content)

    if (!match) throw new Error("PROMPT_SKILL_CONTRACT")
    const doc: unknown = JSON.parse(match[1])

    Option.getOrThrowWith(decodeVersioned(doc), fail("PROMPT_SKILL_VERSION"))
    const creator = decodeCreator(doc)

    if (Option.isSome(creator)) {
      creators.push({ version: 1, kind: "creator", instructions: [...creator.value.instructions], skill: skill.name })
      continue
    }

    const pipeline = Option.getOrThrowWith(decodePipeline(doc), fail("PROMPT_SKILL_CONTRACT"))

    const fields = pipeline.fields.map((value): Field => {
      const field = Option.getOrThrowWith(decodeField(value), fail("PROMPT_SKILL_FIELD"))

      return { id: field.id, label: field.label, help: field.help, required: field.required, default: field.default }
    })

    if (new Set(fields.map((x) => x.id)).size !== fields.length) throw new Error("PROMPT_SKILL_DUPLICATE")

    const format =
      pipeline.format === undefined
        ? undefined
        : Option.getOrThrowWith(decodeFormat(pipeline.format), fail("PROMPT_SKILL_FORMAT"))

    if (
      format &&
      ![format.descriptionField, ...format.positiveFields, ...format.negativeFields].every((id) =>
        fields.some((field) => field.id === id),
      )
    )
      throw new Error("PROMPT_SKILL_FORMAT")

    recipes.push({
      version: 1,
      kind: "pipeline",
      id: pipeline.id,
      title: pipeline.title,
      category: pipeline.category,
      availability: pipeline.availability,
      keywords: [...pipeline.keywords],
      fields,
      format: format && {
        ...format,
        positiveFields: [...format.positiveFields],
        negativeFields: [...format.negativeFields],
      },
      skill: skill.name,
      guidance: skill.content
        .slice(0, match.index)
        .replace(/^---\n[\s\S]*?\n---\n/, "")
        .replace(/^# .*\n/, "")
        .trim(),
    })
  }

  if (creators.length !== 1 || !recipes.length || new Set(recipes.map((x) => x.id)).size !== recipes.length)
    throw new Error("PROMPT_SKILL_CATALOG")

  return {
    creator: creators[0],
    recipes: recipes.sort((a, b) => a.category.localeCompare(b.category) || a.title.localeCompare(b.title)),
  }
}

export function suggestPipeline(request: string, recipes: Recipe[]) {
  const entries = recipes.map((recipe) => ({
    id: recipe.id,
    name: recipe.title,
    description: [recipe.category, ...recipe.keywords, recipe.guidance.slice(0, 1800)].join(" "),
    kind: "pipeline" as const,
    aliases: recipe.keywords,
    requires: [],
    availability: "available",
    autoinvoke: true,
  }))

  return SkillRouting.rank(request, entries, 1)[0]?.id ?? ""
}

export function suppliedAnswers(request: string) {
  const result: Record<string, string> = {}

  const dimensions =
    /\b\d+(?:\.\d+)?\s*(?:mm|cm|m|metres?|meters?|feet|ft|inches|in)?\s*[×x]\s*\d+(?:\.\d+)?\s*(?:mm|cm|m|metres?|meters?|feet|ft|inches|in)?\s*[×x]\s*\d+(?:\.\d+)?\s*(?:mm|cm|m|metres?|meters?|feet|ft|inches|in)\b/i.exec(
      request,
    )

  if (dimensions) result.dimensions = dimensions[0]
  const budget = /\b(?:under|max(?:imum)?|at most|budget(?: of)?)\s*[\d,]+\s*(?:triangles|tris)\b/i.exec(request)

  if (budget) result.budget = budget[0]

  const engines = [...request.matchAll(/\b(?:Godot|Unreal)(?:\s*(?:Engine)?\s*\d+(?:\.\d+){0,2})?\b/gi)].map(
    (x) => x[0],
  )

  if (engines.length) result.target = [...new Set(engines)].join(" and ")

  return result
}

export function defaultAnswers(recipe: Recipe, request: string) {
  return {
    ...Object.fromEntries(recipe.fields.filter((field) => field.default).map((field) => [field.id, field.default!])),
    ...suppliedAnswers(request),
  }
}

export function missingFields(recipe: Recipe, answers: Record<string, string>) {
  return recipe.fields.filter((field) => field.required && !answers[field.id]?.trim())
}

export function composePrompt(
  creator: Creator,
  recipe: Recipe,
  request: string,
  answers: Record<string, string>,
  project: string,
) {
  if (!request.trim() || missingFields(recipe, answers).length) throw new Error("PROMPT_INCOMPLETE")
  const canonical = /^\/data\/ai\/projects\/[\w./ -]+$/.test(project)
  const workspace = project === "/workspace" || /^\/workspace\/[\w./ -]+$/.test(project)

  if (project && !canonical && !workspace) throw new Error("PROMPT_PROJECT")

  if (project.split("/").some((part) => part === "..")) throw new Error("PROMPT_PROJECT")
  const formatted: string[] = []
  const consumed = new Set<string>()

  if (recipe.format) {
    const format = recipe.format

    const tags = (ids: string[]) =>
      [
        ...new Set(
          ids.flatMap((id) =>
            (answers[id] ?? "")
              .split(",")
              .map((tag) => tag.trim())
              .filter(Boolean),
          ),
        ),
      ].join(", ")

    const description = (answers[format.descriptionField]?.trim() || request.trim()).replace(/\s+/g, " ")
    const positive = [description, tags(format.positiveFields)].filter(Boolean).join(" ")
    const negative = tags(format.negativeFields)
    formatted.push(`${format.positiveLabel}:`, positive, "")

    if (negative) formatted.push(`${format.negativeLabel}:`, negative, "")
    formatted.push(`${format.settingsLabel}:`)

    for (const id of [format.descriptionField, ...format.positiveFields, ...format.negativeFields]) consumed.add(id)
  }

  return [
    ...formatted,
    `Task: ${request.trim()}`,
    "",
    project
      ? `Project: ${project}`
      : "Choose a new descriptive revision under /data/ai/projects/games, /data/ai/projects/development or /data/ai/projects/pipelines as appropriate; preserve existing projects.",
    "",
    "Specification:",
    ...recipe.fields
      .filter((field) => !consumed.has(field.id) && answers[field.id]?.trim())
      .map((field) => `- ${field.label}: ${answers[field.id].trim()}`),
    "",
    `Pipeline: ${recipe.title}. Load ${recipe.skill} and relevant execution skills on demand.`,
    `Route status: ${recipe.availability}; verify the actual installed capability before execution.`,
    recipe.guidance,
    "",
    ...creator.instructions.map((text) => `- ${text}`),
  ].join("\n")
}
