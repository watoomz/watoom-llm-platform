export function hasCustomAgent(items: Array<{ name?: string; native?: boolean }>) {
  // V2 agent discovery identifies agents by name and no longer sends native.
  // The caller has already removed hidden agents and delegation-only agents.
  return items.some(
    (item) => item.native === false ||
      (item.native === undefined && item.name !== undefined && item.name !== "build" && item.name !== "plan"),
  )
}

export function resolveAgent<T extends { name: string }>(items: T[], name?: string, defaultAgent?: string) {
  return items.find((item) => item.name === name) ?? items.find((item) => item.name === defaultAgent) ??
    items.find((item) => item.name === "build") ?? items[0]
}
