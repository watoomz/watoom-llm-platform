// OpenCode 2.0.18 adapter. The audited upstream capture implementation is
// retained byte-for-byte under ./agentmemory/agentmemory-capture.ts.
import { AgentmemoryCapturePlugin } from "./agentmemory/agentmemory-capture.ts";
export default {
  id: "watoom.agentmemory.capture",
  async setup(ctx) {
    const legacy = await AgentmemoryCapturePlugin({ worktree: ctx.location.directory });
    const sessions = new Set();
    const controller = new AbortController();
    const emit = (type, properties) => legacy.event({event:{type,properties}});
    async function ensure(sid, info) {
      if (!sid || sessions.has(sid)) return;
      const s = info ?? await ctx.session.get({sessionID:sid});
      await emit("session.created", {info:{...s,id:sid,directory:s.location?.directory ?? ctx.location.directory}});
      sessions.add(sid);
    }
    const before = await ctx.tool.hook("execute.before", async e => {
      await ensure(e.sessionID);
      await legacy["tool.execute.before"]({tool:e.tool,sessionID:e.sessionID},{args:e.input});
    });
    const after = await ctx.tool.hook("execute.after", async e => {
      await ensure(e.sessionID);
      await emit("message.part.updated", {part:{type:"tool",sessionID:e.sessionID,tool:e.tool,
        callID:e.id ?? e.callID ?? `${e.messageID}:${e.tool}:${Date.now()}`,
        state:{status:"completed",input:e.input,output:e.output?.output ?? e.output,title:e.output?.title,metadata:e.output?.metadata}}});
    });
    const feed = (async () => {
      for await (const e of ctx.event.subscribe({signal:controller.signal})) {
        const d=e.data ?? {};const sid=d.sessionID;
        if(!sid)continue;
        if(e.type==="session.created") {await ensure(sid,d);continue;}
        if(e.type==="session.deleted") {
          // A deleted session's SDK row is gone. Use its established attribution.
          if(sessions.has(sid))await emit("session.deleted",{sessionID:sid});
          sessions.delete(sid);continue;
        }
        if(!e.type.startsWith("session."))continue;
        await ensure(sid);
        if(e.type==="session.inbox.enqueued") {
          const text=d.item?.text;
          if(typeof text==="string")await legacy["chat.message"]({sessionID:sid},{parts:[{type:"text",text}]});
        } else if(e.type==="session.execution.started") {
          await emit("session.status",{sessionID:sid,status:{type:"busy"}});
        } else if(["session.execution.succeeded","session.execution.failed","session.execution.interrupted"].includes(e.type)) {
          if(d.error)await emit("session.error",{sessionID:sid,error:d.error});
          await emit("session.status",{sessionID:sid,status:{type:"idle"}});
        } else if(e.type==="session.renamed") {
          await emit("session.updated",{info:{id:sid,title:d.title}});
        } else if(e.type==="session.step.ended") {
          await emit("message.updated",{info:{id:d.assistantMessageID,sessionID:sid,role:"assistant",tokens:d.tokens,cost:d.cost,finish:d.finish}});
        } else if(e.type==="session.reasoning.ended") {
          await emit("message.part.updated",{part:{type:"reasoning",sessionID:sid,messageID:d.assistantMessageID,text:d.text}});
        } else if(e.type==="session.compaction.ended") {
          await emit("session.compacted",{sessionID:sid});
        }
      }
    })().catch(e=>{if(!controller.signal.aborted)console.error("[agentmemory-v2] event capture failed",e);});
    // Do not wire the upstream system-transform/compacting context hooks:
    // AGENTMEMORY_INJECT_CONTEXT=false is an explicit integration boundary.
    console.error("[agentmemory-v2] capture active; context injection disabled");
    return async()=>{controller.abort();await before.dispose();await after.dispose();await feed;};
  },
};
