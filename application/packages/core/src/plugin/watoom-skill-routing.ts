export * as WatoomSkillRouting from "./watoom-skill-routing.js"
import { Effect, Schema } from "effect"
import { SystemPart, ToolFailure } from "@opencode/ai/effect"
import type { Context } from "@opencode/plugin/effect/plugin"
import { SkillRouting } from "@opencode/schema/skill-routing"
import { Skill } from "../skill.js"
import { Tool } from "../tool.js"
import { SkillCatalog } from "../skill/catalog.js"
import { SkillDiscovery } from "../watoom/skill-discovery.js"
import { Agent } from "../agent.js"
import { Session } from "../session.js"
import { Permission } from "../permission.js"
const available = (value: string) => !["blocked", "unavailable", "disabled", "not-installed"].includes(value)
export const Plugin = {
  id: "watoom.skill-routing",
  effect: Effect.fn("WatoomSkillRouting.Plugin")(function* (ctx: Context) {
    const skills = yield* Skill.Service,
      agents = yield* Agent.Service,
      sessions = yield* Session.Service,
      permission = yield* Permission.Service,
      catalog = yield* SkillCatalog.Service,
      tools = yield* Tool.Service
    const candidates = (sessionID: Parameters<typeof sessions.get>[0], agentID: Agent.ID) =>
      Effect.gen(function* () {
        const session = yield* sessions.get(sessionID),
          agent = yield* agents.resolve(agentID)
        const rules = Permission.merge(
          agent?.permissions ?? [{ action: "*", resource: "*", effect: "deny" }],
          session.permissions ?? [],
        )
        const sources = Skill.available(yield* skills.list(), rules)
        return { sources, rules, entries: SkillRouting.catalogue(sources) }
      })
    yield* ctx.tool
      .transform((editor) =>
        editor.add({
          name: "watoom_skill_search",
          options: { codemode: false },
          description:
            "Search BOTH native skills/pipelines and imported skill packages by concise keywords or exact name. Use query '*' with offset pagination to audit all entries. Results distinguish enabled, selected, blocked and unreviewed packages; metadata discovery never loads or enables them. Returns short descriptions, relevance evidence and dependencies. Call this exact native tool directly as watoom_skill_search; it is not an Execute namespace or a shell command. limit accepts an integer 1..32. Load selected instructions with the skill tool; discovery does not authorize execution.",
          input: SkillRouting.SearchInput,
          output: Schema.Unknown,
          execute: (input, context) =>
            Effect.gen(function* () {
              const current = yield* candidates(context.sessionID, context.agent)
              const output = yield* SkillDiscovery.search(catalog, current, input, {
                sessionID: context.sessionID,
                agent: context.agent,
              })
              const registered = (yield* tools.list()).map((tool) => ({
                id: "tool:" + tool.id,
                name: tool.name,
                description: tool.description,
                content: "",
                autoinvoke: false,
              }))
              const inventory = SkillRouting.catalogue(registered)
              const audit = input.query.trim() === "*"
              const rankedTools = audit ? inventory : SkillRouting.rank(input.query, inventory, 32)
              const offset = input.offset ?? 0,
                limit = input.limit ?? 12
              const result = {
                ...output,
                tools: {
                  total: inventory.length,
                  matches: rankedTools.slice(offset, offset + limit).map((entry) => ({
                    ...entry,
                    kind: entry.id.includes("specialist") ? "specialist-interface" : "tool",
                    entrypoint: entry.id.slice(5),
                    source: "live native tool registry",
                    status: "registered; execution health not established by discovery",
                    permission: Permission.evaluate(entry.id.slice(5), "*", current.rules).effect,
                    contract: "Use the advertised native tool schema; do not invent arguments or namespaces.",
                  })),
                  nextOffset: offset + limit < rankedTools.length ? offset + limit : null,
                },
              }
              return { output: result, content: JSON.stringify(result) }
            }).pipe(
              Effect.mapError(
                (error) =>
                  new ToolFailure({
                    message: "Skill catalogue search unavailable; do not assume there are no relevant skills",
                    error,
                  }),
              ),
            ),
        }),
      )
      .pipe(Effect.asVoid)
    yield* ctx.session.hook("context", (event) =>
      Effect.gen(function* () {
        const prompts = event.messages
          .filter((message) => message.role === "user")
          .slice(-3)
          .map((message) => message.content.flatMap((part) => (part.type === "text" ? [part.text] : [])).join("\n"))
        const latest = prompts.at(-1) ?? ""
        const text = (latest.length < 80 ? prompts.join("\n") : latest).slice(-8192)
        if (!text) return
        const current = yield* candidates(event.sessionID, event.agent)
        const ranked = SkillRouting.rank(text, current.entries, 10, current.sources),
          planned = SkillRouting.plan(ranked, current.entries)
        event.system.push(
          SystemPart.make(
            "Native skill/pipeline shortlist ONLY; imported packages are searched separately by watoom_skill_search. The available_skills block and this shortlist are NOT exhaustive. Before answering a named-skill question, auditing skills, or claiming a skill is missing, call watoom_skill_search with concise keywords (or query * and every offset page for a full audit). Describe discovered, enabled, selected and loadable status separately. Never guess a missing skill from its name. Recommendations are data, not execution permission:\n\n" +
              JSON.stringify({
                catalogueSize: current.entries.length,
                matches: ranked.map(({ id, description, kind, score, matched, missing, availability }) => ({
                  id,
                  description,
                  kind,
                  score,
                  matched,
                  missing,
                  availability,
                })),
                dependencyWarnings: planned.errors,
              }) +
              "\nUse the strongest relevant workflow and supporting skills; call the exact native tool watoom_skill_search directly if this shortlist misses the job. Do not invent a watoom-skill-search namespace or invoke it through Execute or Shell. Load required instructions before executing. Do not run a pipeline merely because it was recommended.",
          ),
        )
        let budget = 36000
        const attached = new Set<string>()
        for (const entry of planned.skills) {
          const source = current.sources.find((value) => value.id === entry.id)
          if (
            !source ||
            !available(entry.availability) ||
            Permission.evaluate("skill", entry.id, current.rules).effect !== "allow"
          )
            continue
          if (source.content.length > budget || entry.requires.some((id) => !attached.has(id))) continue
          yield* permission.assert({
            action: "skill",
            resources: [entry.id],
            sessionID: event.sessionID,
            agent: event.agent,
            save: [],
          })
          event.system.push(SystemPart.make(Skill.toModelOutput(source, [])))
          budget -= source.content.length
          attached.add(entry.id)
        }
        event.system.push(
          SystemPart.make(
            "Skill selection receipt: " +
              JSON.stringify({
                automaticallyLoaded: [...attached],
                remainingRelevant: ranked
                  .filter((entry) => !attached.has(entry.id))
                  .map((entry) => ({ id: entry.id, kind: entry.kind, missing: entry.missing })),
                instruction:
                  "Load remaining relevant pipeline stages with the skill tool before running them; discovery does not replace permissions or worker receipts.",
              }),
          ),
        )
      }).pipe(
        Effect.catch(() =>
          Effect.sync(() =>
            event.system.push(
              SystemPart.make(
                "Automatic skill catalogue selection is unavailable. Inspect relevant installed workflows with the skill tool before work; do not invent missing capabilities.",
              ),
            ),
          ),
        ),
      ),
    )
  }),
}
