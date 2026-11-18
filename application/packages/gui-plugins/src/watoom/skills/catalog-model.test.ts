import display from "./catalog-display"
import { test, expect } from "bun:test"
import {
  groupSkills,
  sourceURL,
  riskFlags,
  skillPresentation,
  readableSkillName,
  skillSearchQuery,
  skillProjectOptions,
} from "./catalog-model"

const entry = { repo: "owner/repo", path: "skills/owned", commit_sha: "a".repeat(40) }

test("source links are immutable and reject traversal or URL injection", () => {
  expect(sourceURL(entry)).toBe("https://github.com/owner/repo/blob/" + "a".repeat(40) + "/skills/owned/SKILL.md")

  for (const bad of [
    { ...entry, repo: "javascript:evil" },
    { ...entry, path: "../escape" },
    { ...entry, commit_sha: "main" },
    { ...entry, path: "/absolute" },
  ])
    expect(sourceURL(bad)).toBeUndefined()
})

test("risk flags accept structured metadata only and remain bounded", () => {
  expect(riskFlags('["network","subprocess"]')).toEqual(["network", "subprocess"])

  for (const value of ["not-json", "{}", "[1]", JSON.stringify(Array(33).fill("flag"))])
    expect(riskFlags(value)).toEqual(["metadata-review-required"])
})

test("display summaries are pinned to reviewed source bytes and leave original metadata intact", () => {
  const [id, summary] = Object.entries(display.entries)[0]
  const entry = { id, sha256: summary.sha256, name: "agentbay-aio-skills", description: "原始说明" }
  expect(skillPresentation(entry)).toMatchObject({ title: "AgentBay Code Execution", english: true })
  expect(entry.description).toBe("原始说明")
  expect(skillPresentation({ ...entry, sha256: "changed-source" })).toMatchObject({
    description: "原始说明",
    english: false,
  })
})

test("names are readable while canonical identifiers and search remain available", () => {
  expect(readableSkillName("alterlab-cdm-animation-previz")).toBe("Animation Previsualization")
  expect(readableSkillName("game-ci-pipeline")).toBe("Game CI Pipeline")
  expect(readableSkillName("tdd")).toBe("Test-Driven Development")
  expect(skillSearchQuery("AgentBay Code Execution")).toBe("agentbay-aio-skills")
  expect(skillSearchQuery("retro")).toBe("retro")
})

test("project picker reuses known project roots and worktrees without duplicate or internal fixture entries", () => {
  const choices = skillProjectOptions(
    [
      { worktree: "/workspace/game", name: "Game", sandboxes: ["/workspace/game-feature"] },
      { worktree: "/workspace/game" },
      { worktree: "/workspace/.watoom-validation/release-old" },
      { worktree: "/" },
    ],
    "/workspace/bookmarked",
    "Default project",
  )

  expect(choices.map((item) => item.directory)).toEqual([
    "",
    "/workspace/bookmarked",
    "/workspace/game",
    "/workspace/game-feature",
  ])
  expect(choices.find((item) => item.directory === "/workspace/game")?.label).toContain("Game")
})

test("domain groups preserve all entries and promote existing parent routers", () => {
  const entries = [
    { name: "blender-animation", id: "a" },
    { name: "sims4-cas", id: "b" },
    { name: "unrecognised", id: "c" },
    { name: "blender", id: "d" },
    { name: "sims", id: "e" },
    { name: "kubernetes-router", id: "f" },
    { name: "kubernetes", id: "g" },
  ]

  const grouped = groupSkills(entries)
  expect(grouped.find((x) => x.key === "blender")?.entries.map((x) => x.id)).toEqual(["d", "a"])
  expect(grouped.find((x) => x.key === "sims")?.entries.map((x) => x.id)).toEqual(["e", "b"])
  expect(grouped.find((x) => x.key === "kubernetes")?.entries.map((x) => x.id)).toEqual(["f", "g"])
  expect(grouped.at(-1)?.key).toBe("other")
  expect(
    grouped
      .flatMap((x) => x.entries)
      .map((x) => x.id)
      .sort(),
  ).toEqual(entries.map((x) => x.id).sort())
  expect(entries[0]?.id).toBe("a")
})
