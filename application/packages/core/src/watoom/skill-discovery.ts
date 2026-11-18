export * as SkillDiscovery from "./skill-discovery.js"
import { Effect } from "effect"
import { SkillRouting } from "@opencode/schema/skill-routing"
import { SkillCatalog } from "../skill/catalog.js"
import { Session } from "../session.js"
import { Agent } from "../agent.js"

export function search(
  catalog: Pick<SkillCatalog.Interface, "browse" | "selections">,
  current: { entries: SkillRouting.Entry[]; sources: SkillRouting.Source[] },
  input: { query: string; limit?: number; offset?: number },
  context: { sessionID: Session.ID; agent: Agent.ID },
) {
  return Effect.gen(function* () {
    const limit = input.limit ?? 12
    const offset = input.offset ?? 0
    const audit = input.query.trim() === "*"
    const page = yield* catalog.browse({
      view: "available",
      approvedOnly: false,
      validOnly: false,
      query: audit ? "" : input.query.slice(0, 256),
      limit,
      offset,
    })
    const selected = yield* Effect.all([
      catalog.selections({ agent: context.agent, target: "agent" }),
      catalog.selections({ agent: context.agent, target: "session", sessionID: context.sessionID }),
    ])
    const native = audit ? current.entries : SkillRouting.rank(input.query, current.entries, 32, current.sources)
    return {
      catalogueSize: current.entries.length + page.discovered,
      matches: native.slice(offset, offset + limit),
      native: { total: native.length, nextOffset: offset + limit < native.length ? offset + limit : null },
      imported: {
        enabled: page.enabled,
        total: page.discovered,
        matched: page.matched,
        nextOffset: offset + limit < page.matched ? offset + limit : null,
        entries: page.rows.map((row) => ({
          id: row.id,
          name: row.name,
          description: row.description,
          state: row.state,
          validation: row.validation,
          enabled: row.approved === 1,
          permission: "discovery-only; runtime permissions still apply",
          selected: selected.flat().some((item) => item.id === row.id && item.status === "SELECTED_NOT_EXECUTED"),
          nextAction:
            row.approved === 1
              ? "Load the exact id with skill; explicit loading pins an enabled owner-approved package to this session. Existing permissions and dependency verification still apply."
              : "Complete owner review/validation/approval/install/enable in Skills settings; do not execute this package.",
        })),
      },
      instruction:
        "Metadata only. This result does not select, load, enable or execute skills. Follow BOTH nextOffset values for an exhaustive audit. A shortlist or available_skills block is not the full catalogue. Use concise search keywords; zero matches is not proof a differently named skill does not exist.",
    }
  })
}
