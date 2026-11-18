import { Database as Sqlite } from "bun:sqlite"
import { expect } from "bun:test"
import fs from "node:fs/promises"
import path from "node:path"
import { createHash } from "node:crypto"
import { Effect } from "effect"
import { Global } from "@opencode/util/global"
import { ServerFetch } from "../src/fetch"
import { tmpdirScoped } from "../../core/test/fixture/tmpdir"
import { it } from "../../core/test/lib/effect"

const fixture = Effect.gen(function* () {
  const tmp = yield* tmpdirScoped()
  const roots = Object.fromEntries(
    ["home", "data", "cache", "config", "state", "tmp", "bin", "log", "repos"].map((key) => [
      key,
      path.join(tmp.path, key),
    ]),
  )
  return { tmp, override: Global.node.replace(Global.layerWith(roots)) }
})
const options = {
  app: { version: "catalog-review" },
  database: { path: ":memory:" },
  models: { fetch: false },
  fs: { filewatcher: false },
  config: { project: false },
} as const
it.live("native catalog route reports disabled explicitly and rejects invalid bounds", () =>
  Effect.gen(function* () {
    const { override } = yield* fixture
    const handler = yield* ServerFetch.make(options, { overrides: [override] })
    const response = yield* Effect.promise(() => handler(new Request("http://opencode.local/api/skill/catalog")))
    expect(response.status).toBe(200)
    const result = yield* Effect.promise(() => response.json())
    expect(result.data).toMatchObject({ enabled: false, rows: [] })
    const bad = yield* Effect.promise(() => handler(new Request("http://opencode.local/api/skill/catalog?limit=33")))
    expect(bad.status).toBe(400)
  }),
)
it.live("configured inaccessible catalog is unavailable and never becomes an empty success", () =>
  Effect.gen(function* () {
    const { tmp, override } = yield* fixture
    const handler = yield* ServerFetch.make(
      {
        ...options,
        config: {
          ...options.config,
          content: JSON.stringify({ skill_catalog: { database: path.join(tmp.path, "missing.sqlite") } }),
        },
      },
      { overrides: [override] },
    )
    const response = yield* Effect.promise(() => handler(new Request("http://opencode.local/api/skill/catalog")))
    expect(response.status).toBe(503)
    expect(yield* Effect.promise(() => response.json())).toMatchObject({
      _tag: "ServiceUnavailableError",
      service: "skill-catalog",
    })
  }),
)
it.live(
  "native authenticated catalog reads actual metadata without exporting raw instructions or changing the database",
  () =>
    Effect.gen(function* () {
      const source = process.env.WATOOM_TEST_CATALOG
      if (!source) return yield* Effect.die(Error("WATOOM_TEST_CATALOG fixture required"))
      const before = createHash("sha256")
        .update(yield* Effect.promise(() => fs.readFile(source)))
        .digest("hex")
      const { override } = yield* fixture
      const handler = yield* ServerFetch.make(
        {
          ...options,
          password: "OWNED_TEST_ONLY",
          config: { ...options.config, content: JSON.stringify({ skill_catalog: { database: source } }) },
        },
        { overrides: [override] },
      )
      const url = "http://opencode.local/api/skill/catalog?approvedOnly=false&limit=16"
      expect((yield* Effect.promise(() => handler(new Request(url)))).status).toBe(401)
      const response = yield* Effect.promise(() =>
        handler(new Request(url, { headers: { authorization: "Basic " + btoa("opencode:OWNED_TEST_ONLY") } })),
      )
      expect(response.status).toBe(200)
      const result = yield* Effect.promise(() => response.json())
      expect(result.data).toMatchObject({ enabled: true, discovered: 197, validated: 88, approved: 0, matched: 197 })
      expect(result.data.rows.length).toBe(16)
      for (const row of result.data.rows) {
        expect(row.approved).toBe(0)
        expect(Object.keys(row)).not.toContain("raw")
        expect(Object.keys(row)).not.toContain("content")
      }
      const after = createHash("sha256")
        .update(yield* Effect.promise(() => fs.readFile(source)))
        .digest("hex")
      expect(after).toBe(before)
    }),
)

it.live(
  "native selection isolates agent ownership, rejects unapproved pins and reports revocation without execution",
  () =>
    Effect.gen(function* () {
      const { tmp, override } = yield* fixture
      const artifacts = path.join(tmp.path, "approved-artifacts")
      const folder = path.join(artifacts, "github__owned__fixture", "harmless")
      yield* Effect.promise(() => fs.mkdir(folder, { recursive: true }))
      const text =
        "---\nname: harmless\ndescription: Owned native loader control\n---\nReturn an inert read-only summary.\n"
      const manifest = JSON.stringify({ version: 1, native_tools: [] })
      const digest = (value: string) => createHash("sha256").update(value).digest("hex")
      yield* Effect.promise(() => fs.writeFile(path.join(folder, "SKILL.md"), text))
      yield* Effect.promise(() => fs.writeFile(path.join(folder, "watoom-skill.json"), manifest))
      const database = path.join(tmp.path, "owned-catalog.sqlite")
      const db = new Sqlite(database)
      yield* Effect.addFinalizer(() => Effect.sync(() => db.close()))
      for (const statement of [
        "CREATE TABLE skills(id TEXT PRIMARY KEY,repo TEXT,path TEXT,name TEXT,description TEXT,sha256 TEXT,license TEXT,risk TEXT,validation TEXT)",
        "CREATE TABLE sources(repo TEXT,commit_sha TEXT)",
        "CREATE TABLE approvals(skill_id TEXT,approved_sha TEXT)",
        "CREATE TABLE approval_context(skill_id TEXT,commit_sha TEXT,bundle_sha TEXT)",
        "CREATE VIRTUAL TABLE skills_fts USING fts5(id UNINDEXED,name,description)",
      ])
        db.run(statement)
      const id = "github:owned/fixture:harmless",
        hash = digest(text),
        commit = "b".repeat(40),
        bundle = digest(
          JSON.stringify([
            ["SKILL.md", digest(text)],
            ["watoom-skill.json", digest(manifest)],
          ]),
        )
      db.run("INSERT INTO skills VALUES(?,?,?,?,?,?,?,?,?)", [
        id,
        "owned/fixture",
        "harmless",
        "harmless",
        "Owned inert control",
        hash,
        "MIT",
        "[]",
        "valid",
      ])
      db.run("INSERT INTO sources VALUES(?,?)", ["owned/fixture", commit])
      const handler = yield* ServerFetch.make(
        {
          ...options,
          config: { ...options.config, content: JSON.stringify({ skill_catalog: { database, artifacts } }) },
        },
        { overrides: [override] },
      )
      const request = (method: string, input: object) =>
        Effect.promise(() =>
          handler(
            new Request("http://opencode.local/api/skill/catalog/selection", {
              method,
              headers: { "content-type": "application/json" },
              body: JSON.stringify(input),
            }),
          ),
        )
      let agents: { id: string }[] = []
      for (let attempt = 0; attempt < 20 && agents.length < 2; attempt++) {
        const response = yield* Effect.promise(() => handler(new Request("http://opencode.local/api/agent")))
        expect(response.status).toBe(200)
        agents = (yield* Effect.promise(() => response.json())).data
        if (agents.length < 2) yield* Effect.sleep("100 millis")
      }
      expect(agents.length).toBeGreaterThan(1)
      const agent = agents[0]!.id,
        other = agents[1]!.id
      const input = { agent, target: "agent", skillID: id }
      expect((yield* request("POST", input)).status).toBe(400)
      db.run("INSERT INTO approvals VALUES(?,?)", [id, hash])
      db.run("INSERT INTO approval_context VALUES(?,?,?)", [id, commit, bundle])
      expect((yield* request("POST", { ...input, agent: "unknown-owned-agent" })).status).toBe(400)
      expect((yield* request("POST", { ...input, sessionID: "foreign-session" })).status).toBe(400)
      expect((yield* request("POST", { ...input, target: "session", sessionID: "foreign-session" })).status).toBe(400)
      const selected = yield* request("POST", input)
      expect(selected.status).toBe(200)
      expect((yield* Effect.promise(() => selected.json())).data).toMatchObject({
        id,
        sha256: hash,
        commit,
        bundleSha256: bundle,
        status: "SELECTED_NOT_EXECUTED",
      })
      const list = (owner: string) =>
        Effect.promise(() =>
          handler(
            new Request(
              "http://opencode.local/api/skill/catalog/selection?target=agent&agent=" + encodeURIComponent(owner),
            ),
          ),
        )
      const own = yield* list(agent)
      expect(own.status).toBe(200)
      expect((yield* Effect.promise(() => own.json())).data[0]).toMatchObject({
        name: "harmless",
        status: "SELECTED_NOT_EXECUTED",
      })
      const foreign = yield* list(other)
      expect((yield* Effect.promise(() => foreign.json())).data).toEqual([])
      const created = yield* Effect.promise(() =>
        handler(
          new Request("http://opencode.local/api/session", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ agent, title: "Owned inert skill loader acceptance" }),
          }),
        ),
      )
      expect(created.status).toBe(200)
      const sessionID = (yield* Effect.promise(() => created.json())).data.id
      const load = () =>
        Effect.promise(() =>
          handler(
            new Request("http://opencode.local/api/experimental/session/" + sessionID + "/skill", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ id, resume: false }),
            }),
          ),
        )
      expect((yield* load()).status).toBe(204)
      yield* Effect.promise(() => fs.appendFile(path.join(folder, "SKILL.md"), "Changed without approval"))
      expect((yield* load()).status).toBe(404)
      yield* Effect.promise(() => fs.writeFile(path.join(folder, "SKILL.md"), text))
      db.run("DELETE FROM approvals")
      expect((yield* load()).status).toBe(404)
      const revoked = yield* list(agent)
      expect((yield* Effect.promise(() => revoked.json())).data[0].status).toBe("REVOKED")
      expect((yield* request("POST", input)).status).toBe(400)
      expect((yield* request("DELETE", input)).status).toBe(200)
      const empty = yield* list(agent)
      expect((yield* Effect.promise(() => empty.json())).data).toEqual([])
    }),
)

it.live("skills manager requires authenticated reviewer and full lifecycle; exposes inert bounded preview", () =>
  Effect.gen(function* () {
    const { tmp, override } = yield* fixture
    const artifacts = path.join(tmp.path, "artifacts")
    const collection = path.join(tmp.path, "collection")
    const folder = path.join(collection, "github__owned__manager", "control")
    yield* Effect.promise(() => fs.mkdir(folder, { recursive: true }))
    yield* Effect.promise(() => fs.mkdir(artifacts))
    const text =
      "---\nname: manager-control\ndescription: Owned read-only manager acceptance\n---\nReturn MANAGER_CONTROL only.\n"
    const digest = (value: string) => createHash("sha256").update(value).digest("hex")
    yield* Effect.promise(() => fs.writeFile(path.join(folder, "SKILL.md"), text))
    const database = path.join(tmp.path, "catalog.sqlite")
    const db = new Sqlite(database)
    yield* Effect.addFinalizer(() => Effect.sync(() => db.close()))
    for (const statement of [
      "CREATE TABLE skills(id TEXT PRIMARY KEY,repo TEXT,path TEXT,name TEXT,description TEXT,sha256 TEXT,license TEXT,risk TEXT,validation TEXT)",
      "CREATE TABLE sources(repo TEXT PRIMARY KEY,commit_sha TEXT)",
      "CREATE TABLE approvals(skill_id TEXT PRIMARY KEY,approved_sha TEXT,note TEXT,at TEXT)",
      "CREATE TABLE approval_context(skill_id TEXT PRIMARY KEY,commit_sha TEXT,bundle_sha TEXT)",
      "CREATE VIRTUAL TABLE skills_fts USING fts5(id UNINDEXED,name,description)",
    ])
      db.run(statement)
    const id = "github:owned/manager:control"
    db.run("INSERT INTO skills VALUES(?,?,?,?,?,?,?,?,?)", [
      id,
      "owned/manager",
      "control",
      "manager-control",
      "Owned control",
      digest(text),
      "MIT",
      "[]",
      "valid",
    ])
    db.run("INSERT INTO sources VALUES(?,?)", ["owned/manager", "c".repeat(40)])
    yield* Effect.promise(() => fs.mkdir(path.join(tmp.path, "config"), { recursive: true }))
    yield* Effect.promise(() =>
      fs.writeFile(
        path.join(tmp.path, "config", "opencode.json"),
        JSON.stringify({
          default_agent: "build",
          skill_catalog: { database, artifacts, collection, administration: true },
        }),
      ),
    )
    const handler = yield* ServerFetch.make({ ...options, password: "OWNED_MANAGER_ONLY" }, { overrides: [override] })
    const headers = {
      authorization: "Basic " + btoa("opencode:OWNED_MANAGER_ONLY"),
      "content-type": "application/json",
    }
    const detail = yield* Effect.promise(() =>
      handler(
        new Request("http://opencode.local/api/skill/catalog/detail?skillID=" + encodeURIComponent(id), { headers }),
      ),
    )
    expect(detail.status).toBe(200)
    const preview = (yield* Effect.promise(() => detail.json())).data
    expect(preview.instructions).toContain("MANAGER_CONTROL")
    expect(preview.valid).toBe(true)
    const input = {
      skillID: id,
      sha256: digest(text),
      revision: "c".repeat(40),
      bundleSha256: preview.bundleSha256,
      permissions: [{ action: "skill", resource: id, effect: "allow" }],
      tools: [],
    }
    const post = (action: string, authenticated = true) =>
      Effect.promise(() =>
        handler(
          new Request("http://opencode.local/api/skill/catalog/admin", {
            method: "POST",
            headers: authenticated ? headers : { "content-type": "application/json" },
            body: JSON.stringify({ ...input, action }),
          }),
        ),
      )
    expect((yield* post("stage", false)).status).toBe(401)
    expect((yield* post("enable")).status).toBe(400)
    for (const action of ["stage", "review", "validate", "approve", "install", "enable"])
      expect((yield* post(action)).status).toBe(200)
    const assign = yield* Effect.promise(() =>
      handler(
        new Request("http://opencode.local/api/skill/catalog/selection", {
          method: "POST",
          headers,
          body: JSON.stringify({ agent: "build", target: "agent", skillID: id }),
        }),
      ),
    )
    expect(assign.status).toBe(200)
    const created = yield* Effect.promise(() =>
      handler(new Request("http://opencode.local/api/session", { method: "POST", headers, body: "{}" })),
    )
    expect(created.status).toBe(200)
    const sessionID = (yield* Effect.promise(() => created.json())).data.id
    const loadDefault = () =>
      Effect.promise(() =>
        handler(
          new Request("http://opencode.local/api/experimental/session/" + sessionID + "/skill", {
            method: "POST",
            headers,
            body: JSON.stringify({ id, resume: false }),
          }),
        ),
      )
    expect((yield* loadDefault()).status).toBe(204)
    expect((yield* post("disable")).status).toBe(200)
    expect((yield* loadDefault()).status).toBe(404)
    const disabled = yield* Effect.promise(() =>
      handler(new Request("http://opencode.local/api/skill/catalog?approvedOnly=false&view=disabled", { headers })),
    )
    expect(disabled.status).toBe(200)
    expect((yield* Effect.promise(() => disabled.json())).data.rows[0].state).toBe("DISABLED")
  }),
)
