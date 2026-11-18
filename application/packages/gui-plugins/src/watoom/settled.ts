import type { Resource } from "solid-js"

/**
 * A resource's last loaded value, kept while it refetches, or undefined while it has failed. Read resources through
 * this in render code: reading a failed resource directly rethrows its error and takes the whole page down with it,
 * where the page should show its own error alert instead.
 */
export function settled<T>(resource: Resource<T>): T | undefined {
  return resource.error ? undefined : resource.latest
}
