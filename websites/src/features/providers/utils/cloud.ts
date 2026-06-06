/**
 * Detect Ollama Cloud models. Both ``"<name>:cloud"`` and
 * ``"<name>-cloud"`` conventions are accepted because different
 * registries use different separators; pulling either is near-instant
 * (no GB-sized layers download to local disk).
 */
export function isCloudModel(id: string): boolean {
  const normalized = id.trim().toLowerCase();
  return normalized.endsWith(":cloud") || normalized.endsWith("-cloud");
}
