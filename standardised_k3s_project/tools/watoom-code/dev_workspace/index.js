import { spawn } from "node:child_process";
const agent = "watoom-dev";
const root = "/data/github/watoom-homelab-dev";
const allowed = new Set(["watoom_dev_workspace", "watoom_memory_recall"]);
export function assertTool(role, name) {
  if (role === agent && !allowed.has(name)) throw new Error("DEV_ISOLATION: this agent may use only its constrained workspace tool and project-scoped memory recall");
}
export async function saveRecipe(ctx, input, context, result) {
        if (input.op === "report" && result.task?.phase === "PUSHED") {
          const task = result.task;
          const recipe = JSON.stringify({ verified_development_recipe: task.job, repository: root,
            commit: task.commit, files: task.files, baseline: task.baseline,
            validation: task.validated_command?.slice(0, 3000),
            workflow: "status -> run scoped edit -> validate -> commit explicit files -> push dev -> report; use a new stable job for a new task",
            isolation: "CPU-only sandbox; no network during run; no production access; operator review required for integration" });
          await ctx.session.command({ sessionID: context.sessionID, name: "remember", text: recipe }, { signal: context.signal });
          result.memory = "Native /remember requested for this verified pushed receipt; inspect its native receipt before assuming remote delivery";
        }
}
export async function install(ctx) {
  await ctx.tool.transform(editor => {
    editor.add({
      name: "watoom_dev_workspace",
      options: { codemode: false, permission: "watoom_dev_workspace" },
      description: "Edit/test the isolated homelab dev clone; fixed validated commits and dev-only pushes. Operations: status, run, validate, commit, push, report. Preserve one stable job ID. No production, secrets, Kubernetes or GPU access.",
      input: { type: "object", properties: {
        op: {type:"string",enum:["status","run","validate","commit","push","report"]},
        job: {type:"string",pattern:"^[a-z0-9][a-z0-9_-]{2,63}$"},
        command: {type:"string",minLength:1,maxLength:8000},
        timeout: {type:"integer",minimum:1,maximum:120},
        files: {type:"array",items:{type:"string"},minItems:1,maxItems:30},
        message: {type:"string",minLength:1,maxLength:500}, retry: {type:"boolean"}
      }, required:["op","job"], additionalProperties:false },
      output: {},
      async execute(input, context) {
        if (context.agent !== agent || !(ctx.location.directory === root || ctx.location.directory.startsWith(root + "/"))) throw new Error("DEV_ISOLATION: select the homelab-dev project and watoom-dev agent");
        const args = ["-T","-F","/dev/null","-o","BatchMode=yes","-o","IdentitiesOnly=yes","-o","StrictHostKeyChecking=yes","-o","UserKnownHostsFile="+ctx.options.knownHosts,"-i",ctx.options.key,ctx.options.user+"@"+ctx.options.host];
        const result = await new Promise((resolve, reject) => {
          const child = spawn("/usr/bin/ssh", args, { env:{PATH:"/usr/bin:/bin",LANG:"C.UTF-8"}, signal:context.signal, timeout:180000 });
          let stdout="", stderr="";
          child.stdout.on("data", chunk => { stdout += chunk.toString(); if(stdout.length>65536)child.kill("SIGTERM"); });
          child.stderr.on("data", chunk => { stderr=(stderr+chunk.toString()).slice(-2000); });
          child.once("error", reject);
          child.once("close", code => {
            if(code!==0) { reject(new Error("Constrained development request failed: "+(stdout || stderr).slice(-14000))); return; }
            try { resolve(JSON.parse(stdout)); } catch { reject(new Error("Development transport returned an invalid receipt")); }
          });
          child.stdin.end(JSON.stringify({...input,session:context.sessionID}));
        });
        await saveRecipe(ctx, input, context, result);
        return {output:result,content:JSON.stringify(result)};
      }
    });
    for (const entry of editor.list()) editor.update(entry.id, tool => {
      const execute=tool.execute;
      tool.execute=(input, context)=>{assertTool(context.agent,entry.name);return execute(input,context);};
    });
  });
}
export default { id:"watoom.dev-workspace", setup:install };
