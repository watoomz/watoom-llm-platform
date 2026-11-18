import { test, expect } from "bun:test"
import type { ShellCreateBefore } from "@opencode/plugin/promise/shell"
import guard from "./fixture/toolkit-secret-guard"

test("native hook removes owned credential marker and preserves ordinary environment", async () => {
  let callback: ((input: ShellCreateBefore) => void | Promise<void>) | undefined
  let disposed=false
  const cleanup=await guard.setup({shell:{hook:async(name,fn)=>{expect(String(name)).toBe("create.before");callback=fn;return {dispose:async()=>{disposed=true}}}}})
  const env={PATH:"/usr/bin",HOME:"/owned",WATOOM_TOOLKIT_TOKEN:"OWNED_NONSECRET_FIXTURE"}
  await callback!({command:"owned",cwd:"/owned",timeout:1,shell:"/bin/bash",env})
  expect(Object.hasOwn(env,"WATOOM_TOOLKIT_TOKEN")).toBe(false)
  expect(env.PATH).toBe("/usr/bin")
  expect(env.HOME).toBe("/owned")
  await cleanup();expect(disposed).toBe(true)
})
test("native hook accepts already scrubbed environments",async()=>{
 let callback: ((input: ShellCreateBefore) => void | Promise<void>) | undefined
 await guard.setup({shell:{hook:async(_name,fn)=>{callback=fn;return {dispose:async()=>{}}}}})
 const env={PATH:"/usr/bin"};await callback!({command:"owned",cwd:"/owned",timeout:1,shell:"/bin/bash",env});expect(env).toEqual({PATH:"/usr/bin"})
})
test("unavailable native hook fails instead of claiming protection",async()=>{
 await expect(guard.setup({shell:{hook:async()=>{throw Error("hook unavailable")}}})).rejects.toThrow("hook unavailable")
})
