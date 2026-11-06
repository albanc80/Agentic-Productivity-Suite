// What the UI says about connectors, the same way on every page.
// Chat agents get every connector that is on; a playbook step only the connectors its playbook lists.
import type { ConnectorInfo, Overview } from "./api";

/** On, set up and not paused: agents can use it now. */
export function isLive(c: ConnectorInfo): boolean {
  return c.enabled && !c.offline_paused && !["unconfigured", "disabled", "offline", "error"].includes(c.status);
}

export function connectorName(ov: Overview, id: string): string {
  return ov.connectors.find((c) => c.id === id)?.name || id;
}

/** Short name for tags: the part before any bracket ("Google Workspace (Gmail, …)" → "Google Workspace"). */
export function shortName(ov: Overview, id: string): string {
  return connectorName(ov, id).replace(/\s*\(.*\)\s*$/, "");
}

/** Playbooks that list this connector (they are the only playbooks whose steps can use it). */
export function playbooksUsing(ov: Overview, id: string) {
  return ov.playbooks.filter((p) => p.connectors.includes(id));
}

/** The accounts a sign-in connector reads, as saved in the app (default first). */
export function connectorAccounts(c: ConnectorInfo): string[] {
  const names = c.signin?.accounts_vars || [];
  return names.flatMap((n) => (c.variables.find((v) => v.name === n)?.value || "").split(/[\s,;]+/)).filter(Boolean);
}

/** Open Settings on the Connectors tab. */
export function openConnectors() {
  try { sessionStorage.setItem("suite.settingsTab", "connectors"); } catch { /* storage unavailable */ }
  location.hash = "#/settings";
}
