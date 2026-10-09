/**
 * Save portal credentials in the OS keychain:
 *   npm run creds:set -- --account demo.filer
 * The password is read from a hidden prompt (or PORTAL_PASSWORD for scripting)
 * and never echoed.
 */
import { createInterface } from "node:readline";
import { parseArgs } from "node:util";
import { DEFAULT_SERVICE, loadKeychain } from "./credentials";

function promptHidden(question: string): Promise<string> {
  return new Promise((resolve) => {
    const rl = createInterface({ input: process.stdin, output: process.stdout, terminal: true });
    const rlAny = rl as any;
    rlAny._writeToOutput = (s: string) => {
      if (s.startsWith(question)) process.stdout.write(question);
    };
    rl.question(question, (answer) => {
      rl.close();
      process.stdout.write("\n");
      resolve(answer);
    });
  });
}

async function main() {
  const { values } = parseArgs({
    options: { account: { type: "string" }, service: { type: "string", default: DEFAULT_SERVICE } },
  });
  if (!values.account) throw new Error("--account is required");
  const keychain = await loadKeychain();
  if (!keychain?.setPassword) throw new Error("keytar is not available on this system; use PORTAL_USERNAME/PORTAL_PASSWORD instead.");
  const password = process.env.PORTAL_PASSWORD ?? (await promptHidden(`Password for ${values.account}: `));
  if (!password) throw new Error("Empty password");
  await keychain.setPassword(values.service, values.account, password);
  console.log(`Saved credentials for ${values.account} in the OS keychain (service "${values.service}").`);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
