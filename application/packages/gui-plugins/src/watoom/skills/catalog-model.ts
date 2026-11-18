import { Option, Schema } from "effect"
import display from "./catalog-display"
import type { SkillCatalog } from "@opencode/schema/skill-catalog"

export function sourceURL(entry: Pick<SkillCatalog.Entry, "repo" | "path" | "commit_sha">) {
  if (
    !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(entry.repo) ||
    !/^[a-f0-9]{40}$/.test(entry.commit_sha) ||
    !/^[A-Za-z0-9_./-]+$/.test(entry.path) ||
    entry.path.split("/").some((x) => !x || x === "." || x === "..")
  )
    return undefined
  const file = entry.path.endsWith("SKILL.md") ? entry.path : entry.path + "/SKILL.md"

  return (
    "https://github.com/" +
    entry.repo +
    "/blob/" +
    entry.commit_sha +
    "/" +
    file.split("/").map(encodeURIComponent).join("/")
  )
}
// At most 32 flags of at most 128 characters each; anything else needs a metadata review.

const RiskFlags = Schema.fromJsonString(
  Schema.Array(Schema.String.check(Schema.isMaxLength(128))).check(Schema.isMaxLength(32)),
)

const decodeRiskFlags = Schema.decodeUnknownOption(RiskFlags)

export function riskFlags(value: string): string[] {
  return Option.match(decodeRiskFlags(value), {
    onNone: () => ["metadata-review-required"],
    onSome: (flags) => [...flags],
  })
}

// Display metadata never changes source instructions, stable IDs or reviewed hashes.
export function skillPresentation(entry: Pick<SkillCatalog.Entry, "id" | "name" | "description" | "sha256">) {
  const curated = Object.entries(display.entries).find(([id]) => id === entry.id)?.[1]

  if (curated?.sha256 === entry.sha256)
    return { title: curated.title, description: curated.summary, english: true, source: display.source }

  return { title: readableSkillName(entry.name), description: entry.description, english: false, source: undefined }
}

export function readableSkillName(name: string) {
  const words = new Map(
    Object.entries({
      ai: "AI",
      api: "API",
      sdk: "SDK",
      ui: "UI",
      ux: "UX",
      qa: "QA",
      ci: "CI",
      seo: "SEO",
      llm: "LLM",
      mcp: "MCP",
      vfx: "VFX",
      pr: "Pull Request",
      tdd: "Test-Driven Development",
      eli5: "Explain Simply",
      genai: "Generative AI",
      previz: "Previsualization",
      loc: "Localization",
      gdd: "Game Design Document",
      agentbay: "AgentBay",
      watoom: "WatooM",
      qwen: "Qwen",
      im: "Chat",
      yc: "YC",
    }),
  )

  return name
    .replace(/^alterlab-(?:cdm|genai|nmc|pra|rma|vcd)-/, "")
    .replace(/[-_]+/g, " ")
    .split(/\s+/)
    .map((word) => words.get(word.toLowerCase()) ?? word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ")
}

export function skillSearchQuery(query: string) {
  const normalized = query.trim().toLowerCase()
  const aliases = Object.entries(display.entries).filter(([, item]) => item.title.toLowerCase() === normalized)

  return aliases.length === 1 ? aliases[0][0].split(":").at(-1)! : query
}

export function skillProjectOptions(
  projects: readonly { worktree: string; name?: string; sandboxes?: string[] }[],
  selected: string | undefined,
  defaultLabel: string,
) {
  const options = new Map<string, { directory: string; label: string }>()

  for (const project of projects) {
    for (const directory of [project.worktree, ...(project.sandboxes ?? [])]) {
      if (!directory || directory === "/" || directory.includes("/.watoom-validation/")) continue

      if (options.has(directory)) continue
      options.set(directory, { directory, label: project.name ? project.name + " · " + directory : directory })
    }
  }

  if (selected && !options.has(selected)) options.set(selected, { directory: selected, label: selected })

  return [
    { directory: "", label: defaultLabel },
    ...[...options.values()].sort((a, b) => a.label.localeCompare(b.label)),
  ]
}

const skillDomains = [
  ["sims", /^(?:watoom-prompt-)?sims(?:4)?(?:-|$)/],
  ["blender", /^(?:(?:watoom-)?(?:prompt-)?)?blender(?:-|$)|^asset-image-clip-capture$/],
  ["godot", /^(?:watoom-prompt-)?godot(?:-|$)|^game-template-(?!unreal)/],
  ["unreal", /^(?:watoom-prompt-)?unreal(?:-|$)|^game-template-unreal/],
  ["kubernetes", /^(?:kubernetes|k8s|k3s)(?:-|$)/],
  ["ansible", /^ansible(?:-|$)/],
  ["redhat", /^(?:red-?hat|rhel)(?:-|$)/],
  ["security", /^(?:cybersecurity|security|redteam|blackhat|ghidra|radare2|r2frida|miasm|botnet|cybernetic)(?:-|$)/],
  [
    "writing",
    /^(?:creative-writing|adaptation|chapter-writing|character-management|discovery-drafting|editorial-review|feedback-triage|genre-craft|interactive-fiction|line-editing|plot-structure|premise-workshop|revision-continuity|series-continuity|story|theme-craft|verse-craft|voice-style|worldbuilding|world-building|scene-craft|submission|publishing|reader-panel)(?:-|$)|^watoom-prompt-writing$/,
  ],
  ["image", /^(?:image-creation|imagegen|watoom-explicit-image-creator|watoom-prompt-image)(?:-|$)/],
  ["models", /^(?:llm-models|watoom-prompt-models|model-manager)(?:-|$)/],
  [
    "assets",
    /^(?:asset-pipelines|watoom-fab|watoom-landscape|watoom-prompt-(?:asset|fab|mesh|character|material))|^human-pose/,
  ],
  [
    "homelab",
    /^(?:homelab|opencode|watoom-core|watoom-developer|watoom-prompt-(?:iac|development|inspect|repair|plugin))(?:-|$)/,
  ],
  ["documents", /^(?:doc|documents|pdf|presentations|spreadsheets)(?:-|$)/],
] as const

export type SkillDomain = (typeof skillDomains)[number][0] | "other"

const parentNames: readonly string[] = [
  "blender",
  "godot",
  "homelab",
  "sims",
  "kubernetes-router",
  "ansible",
  "image-creation",
  "creative-writing",
  "red-hat",
  "cybersecurity",
  "asset-pipelines",
  "llm-models",
]

export function groupSkills<T extends { name: string }>(entries: readonly T[]) {
  const groups = new Map<SkillDomain, T[]>()

  for (const entry of entries) {
    const key = skillDomains.find(([, pattern]) => pattern.test(entry.name.toLowerCase()))?.[0] ?? "other"
    const group = groups.get(key) ?? []
    group.push(entry)
    groups.set(key, group)
  }

  return [...skillDomains.map(([key]) => key), "other" as const].flatMap((key) => {
    const values = groups.get(key)

    return values
      ? [
          {
            key,
            entries: values.toSorted(
              (a, b) => Number(parentNames.includes(b.name)) - Number(parentNames.includes(a.name)),
            ),
          },
        ]
      : []
  })
}
