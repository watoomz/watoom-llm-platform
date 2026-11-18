export function isModelVisible(state: "show" | "hide" | undefined, latest: boolean, released?: number) {
  if (state !== undefined) return state === "show"
  if (latest) return true
  // The server uses epoch zero for configured models with no release metadata.
  return released === undefined || !Number.isFinite(released) || released <= 0
}
