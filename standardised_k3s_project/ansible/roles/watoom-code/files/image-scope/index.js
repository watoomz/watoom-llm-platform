import { createHash } from "node:crypto";
export const hash = value => createHash("sha256").update(value).digest("hex");
export function parseScope(text, messageID) {
  const value = text.replace(/\r\n/g, "\n");
  const positives = [...value.matchAll(/^Positive prompt:[ \t]*\n/gm)];
  if (!positives.length) return null;
  if (positives.length !== 1) throw Error("IMAGE_SCOPE_AMBIGUOUS: use one reviewed Positive prompt block per task.");
  const start = positives[0].index + positives[0][0].length;
  const end = value.indexOf("\nExecution settings:", start);
  if (end < 0) throw Error("IMAGE_SCOPE_INCOMPLETE: the reviewed Execution settings boundary is missing.");
  const section = value.slice(start, end);
  const negatives = [...section.matchAll(/^Negative prompt:[ \t]*\n/gm)];
  if (negatives.length > 1) throw Error("IMAGE_SCOPE_AMBIGUOUS: duplicate Negative prompt blocks.");
  const positive = (negatives.length ? section.slice(0, negatives[0].index) : section).trim();
  const negative = negatives.length ? section.slice(negatives[0].index + negatives[0][0].length).trim() : "";
  if (!positive || positive.length > 4096 || negative.length > 4096) throw Error("IMAGE_SCOPE_BOUNDS: reviewed prompts must fit the worker's 4096-character limit; no truncation was performed.");
  const counts = [...value.matchAll(/^- Number of images:[ \t]*([1-9][0-9]*)[ \t]*$/gm)];
  if (counts.length > 1) throw Error("IMAGE_SCOPE_AMBIGUOUS: conflicting count fields.");
  const count = counts.length ? Number(counts[0][1]) : null;
  const task = /^Task:[ \t]*([\s\S]*?)(?:\n\n(?:Project:|Specification:)|$)/m.exec(value)?.[1] || "";
  const exact = /^- Positive prompt handling:[ \t]*(?:verbatim|exact)\b/im.test(value) || /\bpositive prompt (?:verbatim|unchanged|exactly)\b/i.test(task);
  const policy = exact ? "verbatim" : "variations";
  return { messageID, positive, negative, count, policy };
}
export async function sourceScope(ctx, sessionID) {
  const visited = new Set();
  let root = sessionID;
  for (let depth = 0; depth < 8; depth++) {
    if (visited.has(root)) throw Error("IMAGE_SCOPE_SOURCE: cyclic native parent session.");
    visited.add(root);
    const session = await ctx.session.get({ sessionID: root });
    if (!session.parentID) {
      const messages = await ctx.session.context({ sessionID: root });
      const users = messages.filter(x => x.type === "user");
      const latest = users.at(-1);
      if (!latest) throw Error("IMAGE_SCOPE_SOURCE: native user request unavailable.");
      let scope = parseScope(latest.text || "", latest.id);
      if (!scope && /^(?:continue|resume|proceed|go ahead|yes)[.!]?$/i.test((latest.text || "").trim())) {
        for (const user of users.slice(0, -1).reverse()) {
          scope = parseScope(user.text || "", user.id);
          if (scope) break;
        }
      }
      return scope ? { ...scope, sessionID: root } : null;
    }
    root = session.parentID;
  }
  throw Error("IMAGE_SCOPE_SOURCE: native parent depth exceeds the supported bound.");
}
export async function install(ctx) {
  await ctx.tool.hook("execute.before", async event => {
    if (event.tool !== "watoom-images_submit_image") return;
    const scope = await sourceScope(ctx, event.sessionID);
    if (!scope) return; // Unstructured direct image requests retain the existing interface.
    const input = event.input;
    if (!input || typeof input !== "object" || Array.isArray(input)) throw Error("IMAGE_SCOPE_INPUT: native image arguments must be an object.");
    const positive = scope.policy === "verbatim" ? scope.positive : input.prompt;
    if (typeof positive !== "string" || !positive.trim() || positive.length > 4096) throw Error("IMAGE_SCOPE_BOUNDS: a bounded per-image positive prompt is required; no truncation was performed.");
    const audit = {
      version: 2, sourceSession: scope.sessionID, sourceMessage: scope.messageID,
      requestedCount: scope.count, positivePolicy: scope.policy, positiveChars: positive.length, negativeChars: scope.negative.length,
      positiveSha256: hash(positive), reviewedPositiveSha256: hash(scope.positive), negativeSha256: hash(scope.negative),
      positiveRestored: positive !== input.prompt, negativeRestored: input.negative_prompt !== scope.negative,
    };
    // Resolve reviewed negatives and policy from original user data, not assistant paraphrases.
    // Only repair prompt transport; model, settings, request ID and native guards are unchanged.
    event.input = { ...input, prompt: positive, negative_prompt: scope.negative };
    await ctx.storage.set("audit/" + event.sessionID + "/" + event.id, audit);
  });
  await ctx.tool.hook("execute.after", async event => {
    if (event.tool !== "watoom-images_submit_image" || event.status !== "completed") return;
    const audit = await ctx.storage.get("audit/" + event.sessionID + "/" + event.id);
    const output = event.result.output;
    if (!audit || !output || typeof output !== "object" || !/^[a-f0-9]{64}$/.test(output.job_id || "")) return;
    const proof = { ...audit, jobID: output.job_id, source: "native_user_scope_and_per_image_prompt", positiveTransportUnchanged: !audit.positiveRestored, negativeUnchanged: true };
    event.result.output = { ...output, scope_transport: proof };
    event.result.metadata = { ...event.result.metadata, image_scope: proof };
    const note = { type: "text", text: JSON.stringify({ scope_transport: proof, note: "The native transport preserved this job’s per-image positive prompt (or used the reviewed positive block only in explicit verbatim mode), and copied the reviewed negative block exactly. Do not resubmit or claim that supplied negatives were dropped." }) };
    event.result.content = Array.isArray(event.result.content) ? [...event.result.content, note] : [ ...(typeof event.result.content === "string" ? [{type:"text",text:event.result.content}] : []), note ];
  });
}
export default { id: "watoom.image-scope", setup: install };
