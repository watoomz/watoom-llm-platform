/** Reference Node fetch adapter. No hidden retries or default mutations. */
export class NativeClient {
  constructor(baseURL, password, username = "opencode") {
    const url = new URL(baseURL);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new Error("Use an HTTP(S) base URL without embedded credentials/query/fragment");
    }
    this.baseURL = baseURL.replace(/\/$/, "");
    this.authorization = `Basic ${Buffer.from(`${username}:${password}`, "utf8").toString("base64")}`;
  }
  async request(method, path, body) {
    if (!path.startsWith("/api/")) throw new Error("Expected native /api/ path");
    const response = await fetch(this.baseURL + path, {
      method, headers: {Authorization: this.authorization, "Content-Type": "application/json"},
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(30000),
    });
    if (!response.ok) throw new Error(`WatooM HTTP ${response.status}; reconcile before retrying a mutation`);
    return response.status === 204 ? null : response.json();
  }
  info() { return this.request("GET", "/api/info"); }
  sessions(limit = 20) { return this.request("GET", `/api/session?limit=${limit}&order=desc`); }
  prompt(sessionID, text, id) {
    return this.request("POST", `/api/session/${encodeURIComponent(sessionID)}/prompt`,
      {text, resume: true, ...(id ? {id} : {})});
  }
}
