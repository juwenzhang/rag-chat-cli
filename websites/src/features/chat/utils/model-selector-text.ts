import type { ProviderWithModels } from "@/features/chat/components/model-selector/model-selector-menu";

/**
 * Toast message after the user picks a different provider/model in the
 * selector. ``null`` provider+model means "fall back to user default".
 */
export function getSwitchMessage(
  nextProviderId: string | null,
  nextModel: string | null,
  providers: ProviderWithModels[]
): string {
  if (nextProviderId === null && nextModel === null) {
    return "Reverted to user default";
  }
  const providerName =
    providers.find((provider) => provider.id === nextProviderId)?.name ?? "provider";
  return nextModel
    ? `Switched to ${providerName} · ${nextModel}`
    : `Switched to ${providerName}`;
}

/** Label rendered on the model-selector trigger button. */
export function getButtonLabel(
  model: string | null,
  providerName: string | null
): string {
  if (model && providerName) return `${providerName} · ${model}`;
  if (model) return model;
  if (providerName) return `${providerName} · auto`;
  return "Default model";
}
