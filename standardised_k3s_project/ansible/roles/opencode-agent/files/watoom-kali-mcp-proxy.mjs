#!/usr/bin/env node

/*
 * WatooM OpenCode local MCP transport proxy.
 *
 * OpenCode:
 *   stdio MCP
 *       ->
 * this transport-only proxy
 *       ->
 * dedicated WatooM Kali MCP over stateful Streamable HTTP.
 *
 * This process contains no target authority, no Kali command
 * construction and no Docker/Kubernetes access.
 */

import readline from "node:readline";

const endpoint =
  process.env.WATOOM_KALI_MCP_URL ??
  "http://watoom-kali-workbench-mcp.kali-agent.svc.cluster.local:8088/mcp";

const timeoutMs = Number.parseInt(
  process.env.WATOOM_KALI_MCP_TIMEOUT_MS ??
    "180000",
  10,
);

let sessionId = "";

function send(message) {
  process.stdout.write(
    JSON.stringify(message) + "\n",
  );
}

function sendError(id, message) {
  if (
    id === undefined ||
    id === null
  ) {
    console.error(
      `[watoom-kali-proxy] ${message}`,
    );
    return;
  }

  send({
    jsonrpc: "2.0",
    id,
    error: {
      code: -32000,
      message,
    },
  });
}

function parseSse(text) {
  const messages = [];

  for (
    const line of
    text.split(/\r?\n/)
  ) {
    if (!line.startsWith("data:")) {
      continue;
    }

    const raw =
      line.slice(5).trim();

    if (
      !raw ||
      raw === "[DONE]"
    ) {
      continue;
    }

    messages.push(
      JSON.parse(raw),
    );
  }

  return messages;
}

async function forward(message) {
  const controller =
    new AbortController();

  const timer =
    setTimeout(
      () => controller.abort(),
      timeoutMs,
    );

  try {
    const headers = {
      "content-type":
        "application/json",
      "accept":
        "application/json, text/event-stream",
    };

    if (sessionId) {
      headers["mcp-session-id"] =
        sessionId;
    }

    const response =
      await fetch(
        endpoint,
        {
          method: "POST",
          headers,
          body: JSON.stringify(
            message,
          ),
          signal: controller.signal,
        },
      );

    const returned =
      response.headers.get(
        "mcp-session-id",
      );

    if (returned) {
      sessionId =
        returned.trim();
    }

    const text =
      await response.text();

    if (
      response.status === 202
    ) {
      return;
    }

    if (!response.ok) {
      throw new Error(
        `HTTP ${response.status}: ` +
        text.slice(0, 2000),
      );
    }

    const type = String(
      response.headers.get(
        "content-type",
      ) ?? "",
    ).toLowerCase();

    if (
      type.includes(
        "application/json",
      )
    ) {
      if (text.trim()) {
        send(
          JSON.parse(text),
        );
      }

      return;
    }

    if (
      type.includes(
        "text/event-stream",
      )
    ) {
      for (
        const result of
        parseSse(text)
      ) {
        send(result);
      }

      return;
    }

    throw new Error(
      "unexpected content-type=" +
      `${type || "<none>"} ` +
      `body=${text.slice(0, 1000)}`,
    );
  } catch (error) {
    sendError(
      message?.id,
      error?.name === "AbortError"
        ? (
          "dedicated Kali MCP timeout " +
          `after ${timeoutMs}ms`
        )
        : String(
          error?.message ?? error,
        ),
    );
  } finally {
    clearTimeout(timer);
  }
}

async function closeSession() {
  if (!sessionId) {
    return;
  }

  try {
    await fetch(
      endpoint,
      {
        method: "DELETE",
        headers: {
          "accept":
            "application/json, text/event-stream",
          "mcp-session-id":
            sessionId,
        },
        signal:
          AbortSignal.timeout(
            5000,
          ),
      },
    );
  } catch {
    // Best-effort session cleanup.
  }

  sessionId = "";
}

const rl =
  readline.createInterface({
    input: process.stdin,
    crlfDelay: Infinity,
  });

let queue =
  Promise.resolve();

rl.on(
  "line",
  (line) => {
    const raw =
      line.trim();

    if (!raw) {
      return;
    }

    let message;

    try {
      message =
        JSON.parse(raw);
    } catch (error) {
      console.error(
        "[watoom-kali-proxy] " +
        "invalid JSON input: " +
        error.message,
      );
      return;
    }

    /*
     * Serialize messages. MCP initialized notification must reach
     * the backend before the subsequent tools/list.
     */
    queue = queue.then(
      () => forward(message),
      () => forward(message),
    );
  },
);

rl.on(
  "close",
  () => {
    queue
      .then(closeSession)
      .finally(
        () => process.exit(0),
      );
  },
);
