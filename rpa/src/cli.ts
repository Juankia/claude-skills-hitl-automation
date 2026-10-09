/**
 * CLI for the HITL filing agent.
 *
 *   npm run agent -- --filing examples/filing.json
 *   npm run agent -- --filing examples/filing.json --approve-token <token>
 *
 * Without a token, an interactive terminal gets a prompt; a non-interactive
 * run (CI, cron, an LLM tool call) stops at the gate, prints the summary and
 * the token, and exits with code 3. A human then re-runs with
 * `--approve-token`. Exit codes: 0 submitted, 3 awaiting approval, 1 error.
 */
import { readFile } from "node:fs/promises";
import path from "node:path";
import { parseArgs } from "node:util";
import { chromium } from "@playwright/test";
import { PromptApprover, TokenApprover, formatSummary, type Approver } from "./approval";
import { runFiling, validateFiling } from "./agent";
import { describeCredentials, resolveCredentials } from "./credentials";

export const EXIT = { submitted: 0, error: 1, awaitingApproval: 3 } as const;

async function checkChecklist(file: string): Promise<void> {
  const report = JSON.parse(await readFile(file, "utf8"));
  if (report.status !== "ready_for_human_review") {
    const blocking = report.summary?.blocking ?? "?";
    throw new Error(`Filing-prep report ${file} has status "${report.status}" (${blocking} blocking gap(s)); refusing to run.`);
  }
}

export async function main(argv = process.argv.slice(2)): Promise<number> {
  const { values } = parseArgs({
    args: argv,
    options: {
      filing: { type: "string" },
      "base-url": { type: "string", default: process.env.PORTAL_URL ?? "http://127.0.0.1:4317" },
      "approve-token": { type: "string" },
      checklist: { type: "string" },
      account: { type: "string" },
      artifacts: { type: "string", default: "artifacts" },
      headed: { type: "boolean", default: false },
    },
  });
  if (!values.filing) {
    console.error("Usage: agent --filing <filing.json> [--approve-token <token>] [--checklist gap_report.json]");
    return EXIT.error;
  }

  const filing = validateFiling(JSON.parse(await readFile(values.filing, "utf8")));
  if (values.checklist) await checkChecklist(values.checklist);
  const credentials = await resolveCredentials({ account: values.account });
  console.log(`Using credentials: ${describeCredentials(credentials)}`);

  const interactive = Boolean(process.stdin.isTTY) && !values["approve-token"];
  const approver: Approver = interactive ? new PromptApprover() : new TokenApprover(values["approve-token"]);

  const browser = await chromium.launch({ headless: !values.headed });
  try {
    const page = await browser.newPage();
    const result = await runFiling({
      page,
      baseUrl: values["base-url"]!,
      filing,
      credentials,
      approver,
      artifactsDir: path.resolve(values.artifacts!),
    });

    if (result.status === "submitted") {
      console.log(`Submitted. Confirmation number: ${result.confirmation}`);
      return EXIT.submitted;
    }
    if (result.status === "blocked") {
      if (!interactive && result.summary && result.token && result.screenshotPath) {
        console.log(formatSummary({ summary: result.summary, token: result.token, screenshotPath: result.screenshotPath }));
      }
      console.log(`NOT submitted: ${result.reason}`);
      console.log(`To approve this exact filing, re-run with: --approve-token ${result.token}`);
      return EXIT.awaitingApproval;
    }
    console.error(`Aborted: ${result.reason}`);
    return EXIT.error;
  } finally {
    await browser.close();
  }
}

if (require.main === module) {
  main()
    .then((code) => process.exit(code))
    .catch((err) => {
      console.error(err instanceof Error ? err.message : err);
      process.exit(EXIT.error);
    });
}
