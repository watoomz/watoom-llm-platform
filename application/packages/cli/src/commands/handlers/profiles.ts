import path from "node:path"
import { Effect } from "effect"
import { Global } from "@opencode/util/global"
import { ProfileInstall, Profiles, available } from "@opencode/server/profile-install"
import { Commands } from "../commands"
import { Runtime } from "../../framework/runtime"

export default Runtime.handler(Commands.commands.profiles, Effect.fn("cli.profiles")(function* (input) {
  const global = yield* Global.Service
  const root = input.scope === "user" ? global.config : path.join(process.cwd(), ".opencode")
  if (input.action === "list" || input.action === "export" || input.action === "describe") {
    const state = yield* Effect.promise(() => ProfileInstall.selection(root))
    const dependencies = yield* Effect.promise(() => available(root))
    process.stdout.write(JSON.stringify(input.action === "describe" ? Profiles.resolve(input.select.split(","), dependencies, input.components.split(",").filter(Boolean), input.disable.split(",").filter(Boolean)) : input.action === "export" ? yield* Effect.promise(() => ProfileInstall.exportConfiguration(root)) : { ...Profiles.catalog, available: dependencies, ...state, statuses: Profiles.availability(dependencies) }, null, 2) + "\n")
    return
  }
  const result = input.action === "rollback"
    ? yield* Effect.tryPromise(() => ProfileInstall.rollback(root, input.transaction))
    : yield* Effect.tryPromise(async () => ProfileInstall.install({ root, profiles: input.select.split(","), available: await available(root), dryRun: input.dryRun, components: input.components.split(",").filter(Boolean), disabled: input.disable.split(",").filter(Boolean) }))
  process.stdout.write(JSON.stringify(result, null, 2) + "\n")
}))
