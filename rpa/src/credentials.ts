/**
 * Credential resolution for the RPA agent.
 *
 * Order: OS keychain (macOS Keychain, Windows Credential Manager, libsecret on
 * Linux) via `keytar`, then environment variables. Credentials are only ever
 * handed to the browser; they are never logged, written to the audit trail,
 * included in summaries, or passed to a language model.
 */

export interface Credentials {
  username: string;
  password: string;
  source: "keychain" | "env";
}

/** The subset of the keytar API we use; lets tests inject a fake keychain. */
export interface Keychain {
  getPassword(service: string, account: string): Promise<string | null>;
  findCredentials(service: string): Promise<Array<{ account: string; password: string }>>;
  setPassword?(service: string, account: string, password: string): Promise<void>;
}

export const DEFAULT_SERVICE = "hitl-filing-agent";

export class CredentialsError extends Error {}

/** Load keytar lazily; it is an optional native dependency. */
export async function loadKeychain(): Promise<Keychain | null> {
  try {
    const mod: any = await import("keytar");
    const api = mod.default ?? mod;
    return typeof api.getPassword === "function" ? (api as Keychain) : null;
  } catch {
    return null;
  }
}

export interface ResolveOptions {
  service?: string;
  account?: string;
  env?: NodeJS.ProcessEnv;
  /** `undefined` = try to load keytar; `null` = skip the keychain. */
  keychain?: Keychain | null;
}

export async function resolveCredentials(opts: ResolveOptions = {}): Promise<Credentials> {
  const service = opts.service ?? DEFAULT_SERVICE;
  const env = opts.env ?? process.env;
  // PORTAL_CREDENTIAL_SOURCE=env skips the keychain entirely (CI, tests, containers),
  // so a headless run can never block on an OS keychain access dialog.
  const envOnly = env.PORTAL_CREDENTIAL_SOURCE === "env";
  const keychain = envOnly ? null : opts.keychain === undefined ? await loadKeychain() : opts.keychain;
  const account = opts.account ?? env.PORTAL_USERNAME;

  if (keychain) {
    try {
      if (account) {
        const password = await keychain.getPassword(service, account);
        if (password) return { username: account, password, source: "keychain" };
      } else {
        const [first] = await keychain.findCredentials(service);
        if (first) return { username: first.account, password: first.password, source: "keychain" };
      }
    } catch {
      // Keychain locked/unavailable (e.g. headless CI): fall through to env.
    }
  }

  if (env.PORTAL_USERNAME && env.PORTAL_PASSWORD) {
    return { username: env.PORTAL_USERNAME, password: env.PORTAL_PASSWORD, source: "env" };
  }
  throw new CredentialsError(
    `No portal credentials found. Store them with "npm run creds:set -- --account <user>" ` +
      `(service "${service}") or set PORTAL_USERNAME and PORTAL_PASSWORD.`,
  );
}

/** Safe representation for logs: never includes the password. */
export function describeCredentials(c: Credentials): string {
  return `${c.username} (from ${c.source}, password redacted)`;
}
