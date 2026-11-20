import type { Context, Plugin } from "@opencode/plugin/promise/plugin"

// Native shell hook: reduce accidental credential inheritance without changing other variables.
// This is not an OS isolation boundary against same-UID access to the server process.
export default {
  id: "watoom.toolkit.secret-guard",
  async setup(ctx: Pick<Context, "shell">) {
    const registration = await ctx.shell.hook("create.before", (event) => {
      delete event.env.WATOOM_TOOLKIT_TOKEN
    })
    return () => registration.dispose()
  },
} satisfies Plugin
