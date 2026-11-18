import { test, expect } from "bun:test"
import { Schema } from "effect"
import { SkillRouting } from "@opencode/schema/skill-routing"
const sources = [
  {
    id: "adaptation",
    name: "Adaptation",
    description: "Write graphic novels, comics, panel scripts and illustration notes.",
    content: "",
  },
  {
    id: "image-creator",
    name: "Image creator",
    description: "Generate illustrations with the installed image pipeline.",
    content: "",
  },
  {
    id: "blender-rig",
    name: "Blender rig",
    description: "Rig Blender characters and export animated meshes to Godot.",
    content: "",
  },
  {
    id: "private-review",
    name: "Private review",
    description: "Review graphic novel scripts.",
    content: "",
    autoinvoke: false,
  },
]
test("catalogue ranks story and illustration work ahead of unrelated mesh work", () => {
  const entries = SkillRouting.catalogue(sources),
    matches = SkillRouting.rank("Write and illustrate a graphic novel with page panel notes", entries)
  expect(matches[0]?.id).toBe("adaptation")
  expect(matches.some((x) => x.id === "image-creator")).toBe(true)
  expect(matches.some((x) => x.id === "blender-rig")).toBe(false)
})
test("new installed skills are immediately searchable without a routing allowlist", () => {
  const entries = SkillRouting.catalogue([
    ...sources,
    { id: "cyanotype", name: "Cyanotype", description: "Prepare cyanotype botanical print layouts.", content: "" },
  ])
  expect(SkillRouting.rank("cyanotype botanical print", entries)[0]?.id).toBe("cyanotype")
})
test("explicit-only skills remain visible but are never selected implicitly", () => {
  const entries = SkillRouting.catalogue(sources),
    matches = SkillRouting.rank("review graphic novel scripts", entries)
  expect(matches.some((x) => x.id === "private-review")).toBe(true)
  expect(SkillRouting.plan(matches, entries).skills.some((x) => x.id === "private-review")).toBe(false)
  expect(SkillRouting.plan(SkillRouting.rank("$private-review", entries), entries).skills[0]?.id).toBe("private-review")
})
test("dependencies are ordered, cycles are rejected and one broken workflow does not disable another", () => {
  const entries = SkillRouting.catalogue(sources).map((x) => ({
    ...x,
    requires: x.id === "adaptation" ? ["missing"] : [],
  }))
  const result = SkillRouting.plan(
    SkillRouting.rank("write graphic novel generate image illustrations", entries),
    entries,
  )
  expect(result.errors).toContain("missing-skill:missing")
  expect(result.skills.some((x) => x.id === "adaptation")).toBe(false)
  expect(result.skills.some((x) => x.id === "image-creator")).toBe(true)
  const cycle = entries.map((x) => ({
    ...x,
    requires: x.id === "adaptation" ? ["image-creator"] : x.id === "image-creator" ? ["adaptation"] : [],
  }))
  expect(
    SkillRouting.plan(SkillRouting.rank("$adaptation", cycle), cycle).errors.some((x) =>
      x.startsWith("dependency-cycle:"),
    ),
  ).toBe(true)
})
test("a negated workflow is not recommended", () => {
  const entries = SkillRouting.catalogue(sources)
  expect(
    SkillRouting.rank("write graphic novel without Blender rig", entries).some((x) => x.id === "blender-rig"),
  ).toBe(false)
})
test("pipeline metadata is indexed as data, never evaluated", () => {
  const content =
    "```prompt-builder\n" +
    JSON.stringify({
      kind: "pipeline",
      id: "comic-book",
      keywords: ["graphic novel", "comic book"],
      requires: ["adaptation"],
      availability: "available",
    }) +
    "\n```"
  const entries = SkillRouting.catalogue([
    ...sources,
    { id: "comic-pipeline", name: "Comic pipeline", description: "Write graphic novel pages.", content },
  ])
  expect(entries.at(-1)?.kind).toBe("pipeline")
  expect(entries.at(-1)?.requires).toEqual(["adaptation"])
  const plan = SkillRouting.plan(SkillRouting.rank("pipeline:comic-book", entries), entries)
  expect(plan.skills.map((x) => x.id)).toEqual(["adaptation", "comic-pipeline"])
})

test("invalid metadata cannot break the installed catalogue", () => {
  const entries = SkillRouting.catalogue([
    ...sources,
    { id: "broken", name: "Broken", content: "```skill-routing\nnull\n```\n```prompt-builder\n[]\n```" },
  ])
  expect(entries.length).toBe(sources.length + 1)
  expect(SkillRouting.rank("graphic novel", entries).some((entry) => entry.id === "adaptation")).toBe(true)
})

test("native skill search normalizes numeric text and rejects invalid limits", () => {
  const decode = Schema.decodeUnknownSync(SkillRouting.SearchInput)
  expect(decode({ query: "EL4CTEO Blender capture", limit: "15" }).limit).toBe(15)
  expect(decode({ query: "Blender", limit: 15 }).limit).toBe(15)
  expect(decode({ query: "Blender" }).limit).toBeUndefined()
  for (const limit of [0, 33, -1, 1.5, "fifteen", "NaN", "Infinity", null])
    expect(() => decode({ query: "Blender", limit })).toThrow()
})
