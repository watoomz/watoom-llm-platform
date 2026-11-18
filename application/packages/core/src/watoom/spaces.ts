export * as Spaces from "./spaces.js"

import { readFile } from "node:fs/promises"
import path from "node:path"

/** A project space published by the deployment: a group of projects under one absolute root. */
export type Space = { id: string; label: string; description: string; root: string }

const SPACE_ID = /^[a-z0-9][a-z0-9-]{0,31}$/

/** Project spaces the deployment declares in <root>/watoom-spaces.json as {"spaces": [{id,label,description,root}]}.
 * Read-only guidance for the new-session picker (grouping existing projects and guiding new ones); the server never
 * writes it. A missing, unreadable or malformed file, and any invalid entry, yields no space rather than an error, so
 * the picker falls back to its flat list. Only entries with a safe id, a label and an absolute root are returned. */
export async function spaces(root?: string): Promise<Space[]> {
  if (!root) return []
  const text = await readFile(path.join(root, "watoom-spaces.json"), "utf8").catch(() => undefined)
  if (text === undefined) return []
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return []
  }
  const list = (parsed as { spaces?: unknown } | null)?.spaces
  if (!Array.isArray(list)) return []
  const seen = new Set<string>()
  const result: Space[] = []
  for (const entry of list) {
    const { id, label, description, root: spaceRoot } = (entry ?? {}) as Record<string, unknown>
    if (typeof id !== "string" || !SPACE_ID.test(id) || seen.has(id)) continue
    if (typeof label !== "string" || label.length === 0) continue
    if (typeof spaceRoot !== "string" || !path.isAbsolute(spaceRoot)) continue
    seen.add(id)
    result.push({
      id,
      label,
      description: typeof description === "string" ? description : "",
      root: path.normalize(spaceRoot),
    })
  }
  return result
}
