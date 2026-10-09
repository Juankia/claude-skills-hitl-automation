/**
 * Human approval gate for irreversible actions.
 *
 * The agent never decides on its own to perform the final submit. It builds a
 * summary of exactly what the portal is about to receive (read back from the
 * review page, not from the agent's input) and asks an Approver.
 *
 * Approval is bound to content: the approval token is a hash of the summary,
 * so a token issued for one filing cannot approve a different or modified
 * one. "y" is not accepted at the interactive prompt; the human must type
 * the token shown, which forces them to actually look at the summary.
 */
import { createHash } from "node:crypto";
import { createInterface } from "node:readline/promises";
import type { Readable, Writable } from "node:stream";

export interface FilingSummary {
  portal: string;
  account: string;
  caseNumber: string;
  court: string;
  filingType: string;
  filerName: string;
  documentTitle: string;
}

export interface ApprovalRequest {
  summary: FilingSummary;
  token: string;
  screenshotPath: string;
}

export interface ApprovalDecision {
  approved: boolean;
  method: "token" | "prompt" | "none";
  reason: string;
}

export interface Approver {
  decide(request: ApprovalRequest): Promise<ApprovalDecision>;
}

/** Deterministic, order-independent token for a summary (12 hex chars). */
export function approvalToken(summary: FilingSummary): string {
  const canonical = JSON.stringify(
    Object.fromEntries(Object.entries(summary).sort(([a], [b]) => a.localeCompare(b))),
  );
  return createHash("sha256").update(canonical).digest("hex").slice(0, 12);
}

export function formatSummary(req: ApprovalRequest): string {
  const s = req.summary;
  return [
    "",
    "================ APPROVAL REQUIRED: IRREVERSIBLE ACTION ================",
    `  Portal          ${s.portal}`,
    `  Signed in as    ${s.account}`,
    `  Case number     ${s.caseNumber}`,
    `  Court           ${s.court}`,
    `  Filing type     ${s.filingType}`,
    `  Filer name      ${s.filerName}`,
    `  Document title  ${s.documentTitle}`,
    `  Screenshot      ${req.screenshotPath}`,
    "",
    `  Approval token  ${req.token}`,
    "=========================================================================",
    "",
  ].join("\n");
}

/** Approves only when a pre-issued token matches this exact summary. */
export class TokenApprover implements Approver {
  constructor(private readonly token: string | undefined) {}

  async decide(req: ApprovalRequest): Promise<ApprovalDecision> {
    if (!this.token) {
      return { approved: false, method: "none", reason: "No approval token supplied." };
    }
    if (this.token.trim() !== req.token) {
      return {
        approved: false,
        method: "token",
        reason: "Approval token does not match this filing (data changed or wrong token).",
      };
    }
    return { approved: true, method: "token", reason: "Pre-issued token matches the reviewed summary." };
  }
}

/** Interactive approval: the human must type the token printed with the summary. */
export class PromptApprover implements Approver {
  constructor(
    private readonly input: Readable = process.stdin,
    private readonly output: Writable = process.stdout,
  ) {}

  async decide(req: ApprovalRequest): Promise<ApprovalDecision> {
    this.output.write(formatSummary(req));
    const rl = createInterface({ input: this.input, output: this.output, terminal: false });
    // A closed/EOF stdin must count as "no", never hang and never default to "yes".
    const closed = new Promise<null>((resolve) => rl.once("close", () => resolve(null)));
    try {
      const answer = await Promise.race([
        rl.question("Type the approval token to submit, anything else to cancel: "),
        closed,
      ]);
      if (answer === null) {
        return { approved: false, method: "prompt", reason: "Prompt closed without an answer." };
      }
      if (answer.trim() === req.token) {
        return { approved: true, method: "prompt", reason: "Operator typed the matching token." };
      }
      return { approved: false, method: "prompt", reason: "Operator did not confirm." };
    } catch {
      return { approved: false, method: "prompt", reason: "Prompt failed; treated as denial." };
    } finally {
      rl.close();
    }
  }
}
