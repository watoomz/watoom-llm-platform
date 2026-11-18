import { expect, test } from "bun:test"
import { mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { Spaces } from "@opencode/core/watoom/spaces"

async function withRoot(contents: string | undefined, run: (root: string) => Promise<void>) {
  const root = await mkdtemp(path.join(tmpdir(), "watoom-spaces-"))
  try {
    if (contents !== undefined) await writeFile(path.join(root, "watoom-spaces.json"), contents)
    await run(root)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
}

test("no root and a missing file yield no spaces", async () => {
  expect(await Spaces.spaces(undefined)).toEqual([])
  await withRoot(undefined, async (root) => {
    expect(await Spaces.spaces(root)).toEqual([])
  })
})

test("valid spaces are read with a defaulted description", async () => {
  await withRoot(
    JSON.stringify({
      spaces: [
        { id: "games", label: "Games", description: "Game builds", root: "/data/ai/projects/games" },
        { id: "homelab", label: "Homelab", root: "/data/ai/projects/homelab" },
      ],
    }),
    async (root) => {
      expect(await Spaces.spaces(root)).toEqual([
        { id: "games", label: "Games", description: "Game builds", root: "/data/ai/projects/games" },
        { id: "homelab", label: "Homelab", description: "", root: "/data/ai/projects/homelab" },
      ])
    },
  )
})

test("malformed JSON, a non-array and invalid entries are dropped, not thrown", async () => {
  await withRoot("{ not json", async (root) => expect(await Spaces.spaces(root)).toEqual([]))
  await withRoot(JSON.stringify({ spaces: {} }), async (root) => expect(await Spaces.spaces(root)).toEqual([]))
  await withRoot(
    JSON.stringify({
      spaces: [
        { id: "ok", label: "Ok", root: "/data/ai/projects/ok" },
        { id: "bad id", label: "Bad", root: "/data/ai/projects/bad" }, // space in id
        { id: "relative", label: "Relative", root: "projects/relative" }, // not absolute
        { id: "nolabel", root: "/data/ai/projects/nolabel" }, // missing label
        { id: "ok", label: "Duplicate", root: "/data/ai/projects/dup" }, // duplicate id
      ],
    }),
    async (root) => {
      const spaces = await Spaces.spaces(root)
      expect(spaces.map((space) => space.id)).toEqual(["ok"])
      expect(spaces[0]!.root).toBe("/data/ai/projects/ok")
    },
  )
})
