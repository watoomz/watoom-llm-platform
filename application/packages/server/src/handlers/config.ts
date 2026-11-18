import { InvalidRequestError } from "@opencode/protocol/errors"
import { Global } from "@opencode/util/global"
import { Profiles, ProfileInstall, available, spaces } from "../profile-install"
import { Config } from "@opencode/core/config"
import { ShellSelect } from "@opencode/core/shell/select"
import { Effect } from "effect"
import { HttpApiBuilder } from "effect/http-api"
import { Api } from "../api"

export const ConfigHandler = HttpApiBuilder.group(Api, "server.config", (handlers) => Effect.gen(function* () {
  const global = yield* Global.Service
  return handlers
    .handle("config.profiles.list", Effect.fn(function* () {
      return yield* Effect.promise(async () => { const dependencies = await available(global.config); return { ...Profiles.catalog, available: dependencies, ...await ProfileInstall.selection(global.config), statuses: Profiles.availability(dependencies) } })
    }))
    .handle("config.profiles.install", Effect.fn(function* (ctx) {
      return yield* Effect.tryPromise({ try: async () => ProfileInstall.install({ root: global.config, profiles: [...ctx.payload.profiles], available: await available(global.config), dryRun: ctx.payload.dryRun, components: ctx.payload.components ? [...ctx.payload.components] : undefined, disabled: ctx.payload.disabled ? [...ctx.payload.disabled] : undefined }), catch: () => new InvalidRequestError({ message: "Invalid profile change or configuration conflict" }) })
    }))
    .handle("config.spaces", () => Effect.promise(() => spaces(global.config)))
    .handle("config.profiles.export", () => Effect.promise(async () => ({ configuration: JSON.stringify(await ProfileInstall.exportConfiguration(global.config), null, 2) })))
    .handle("config.profiles.rollback", Effect.fn(function* (ctx) {
      return yield* Effect.promise(() => ProfileInstall.rollback(global.config, ctx.payload.transaction))
    }))
    .handle("config.get", () => Config.Service.use((config) => config.entries()))
    .handle(
      "config.update",
      Effect.fn(function* (ctx) {
        const config = yield* Config.Service
        if (!config.update) return yield* Effect.die(new Error("Config updates are unavailable"))
        return yield* config.update(ctx.payload).pipe(Effect.orDie)
      }),
    )
    .handle(
      "config.shells",
      Effect.fn(function* () {
        const shell = yield* ShellSelect.Service
        if (!shell.list) return yield* Effect.die(new Error("Shell discovery is unavailable"))
        return yield* shell.list()
      }),
    )
}))
