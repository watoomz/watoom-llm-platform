export * as Memory from "./memory.js"

import { envelope, type Envelope, type Receipt, type MemoryPort } from "./contract.js"
export interface SearchPort {
  search(
    input: { query: string; project: string; agentId: string; limit: number; format: "full" },
    signal?: AbortSignal,
  ): Promise<unknown>
}

/** Existing application HTTP owner supplies authenticated bounded transport. No server, retries or polling here. */
export interface AgentMemoryTransport {
  post(
    path: "/agentmemory/remember" | "/agentmemory/search",
    body: Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<unknown>
}
export class AgentMemory implements MemoryPort, SearchPort {
  private readonly transport: AgentMemoryTransport
  constructor(transport: AgentMemoryTransport) {
    this.transport = transport
  }
  async remember(input: Envelope, signal?: AbortSignal): Promise<Receipt> {
    const e = envelope({ scope: input.scope, job: input.job, seq: input.seq, kind: input.kind, content: input.content })
    if (input.id !== e.id || input.digest !== e.digest || input.version !== 2) throw Error("invalid envelope")
    if (e.scope.agent.length > 128) throw Error("AgentMemory agentId exceeds native limit")
    const result = await this.transport.post(
      "/agentmemory/remember",
      { content: JSON.stringify(e), project: e.scope.project, agentId: e.scope.agent },
      signal,
    )
    const r = result as {
      success?: unknown
      memory?: { id?: unknown; content?: unknown; project?: unknown; agentId?: unknown }
    }
    if (
      r?.success !== true ||
      typeof r.memory?.id !== "string" ||
      !/^[A-Za-z0-9._:-]{1,512}$/.test(r.memory.id) ||
      r.memory.content !== JSON.stringify(e) ||
      r.memory.project !== e.scope.project ||
      r.memory.agentId !== e.scope.agent
    )
      throw Error("unverified memory acknowledgment")
    return { id: e.id, digest: e.digest, scope: e.scope, memoryId: r.memory.id, durability: "observed" }
  }
  async search(
    input: { query: string; project: string; agentId: string; limit: number; format: "full" },
    signal?: AbortSignal,
  ): Promise<unknown> {
    if (
      !input.query ||
      input.query.length > 1024 ||
      input.limit < 1 ||
      input.limit > 16 ||
      !Number.isInteger(input.limit) ||
      input.format !== "full"
    )
      throw Error("search bounds")
    return this.transport.post("/agentmemory/search", { ...input, token_budget: 4096 }, signal)
  }
  /**
   * Exact-key reconciliation of an ambiguous acknowledgment: re-send the identical envelope.
   * AgentMemory supersedes a same-project memory whose content is identical (Jaccard 1.0), so the
   * re-send leaves one latest copy, and remember() accepts only a receipt whose stored content is
   * byte-identical to this envelope. No BM25 search is issued for content hashes.
   */
  async reconcile(e: Envelope, signal?: AbortSignal): Promise<Receipt | undefined> {
    return this.remember(e, signal)
  }
}
