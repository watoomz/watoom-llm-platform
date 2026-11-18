export { Profiles } from "@opencode/core/watoom/profiles"
export { ProfileInstall } from "@opencode/core/watoom/install"
export { Spaces } from "@opencode/core/watoom/spaces"

/** CPU-only discovery, without invoking backends or changing their configuration. */
export async function available(root?: string) {
  const { ProfileInstall } = await import("@opencode/core/watoom/install")
  return ProfileInstall.available(root)
}

/** Deployment-declared project spaces for the new-session picker; read-only, empty when unset or malformed. */
export async function spaces(root?: string) {
  const { Spaces } = await import("@opencode/core/watoom/spaces")
  return Spaces.spaces(root)
}
