/**
 * HITL filing agent: fills the portal form, stops at the review page, and
 * only clicks the irreversible "Submit filing" button after explicit human
 * approval.
 *
 * Defense in depth:
 *  1. Control flow - the submit click is only reachable after `approver.decide`
 *     returns `approved: true`.
 *  2. Network guard - until approval, any request to the submission endpoint
 *     is aborted at the browser level, so a stray click (bug, retry, or a
 *     misbehaving script) still cannot file anything.
 *  3. Read-back - the summary shown to the human is scraped from the portal's
 *     own review page and compared with the intended data; any mismatch aborts.
 */
import { mkdir, appendFile } from "node:fs/promises";
import path from "node:path";
import type { Page, Route } from "@playwright/test";
import { approvalToken, type Approver, type FilingSummary } from "./approval";
import type { Credentials } from "./credentials";

export interface FilingInput {
  caseNumber: string;
  court: string;
  filingType: "motion" | "complaint" | "notice";
  filerName: string;
  documentTitle: string;
}

export type FilingStatus = "submitted" | "blocked" | "aborted";

export interface FilingResult {
  status: FilingStatus;
  reason: string;
  token?: string;
  summary?: FilingSummary;
  screenshotPath?: string;
  confirmation?: string;
}

export interface RunOptions {
  page: Page;
  baseUrl: string;
  filing: FilingInput;
  credentials: Credentials;
  approver: Approver;
  artifactsDir: string;
  /** Endpoint pattern guarded until approval. */
  submitEndpoint?: string;
}

const FIELDS = ["caseNumber", "court", "filingType", "filerName", "documentTitle"] as const;
const CASE_NUMBER = /^\d{2}-(CV|PR|DR)-\d{5}$/;

export function validateFiling(input: unknown): FilingInput {
  const f = input as Record<string, unknown>;
  const problems: string[] = [];
  for (const key of FIELDS) {
    if (typeof f?.[key] !== "string" || !(f[key] as string).trim()) problems.push(`${key} is required`);
  }
  if (typeof f?.caseNumber === "string" && !CASE_NUMBER.test(f.caseNumber)) {
    problems.push("caseNumber must look like 26-CV-01234");
  }
  if (typeof f?.filingType === "string" && !["motion", "complaint", "notice"].includes(f.filingType)) {
    problems.push("filingType must be motion, complaint or notice");
  }
  if (problems.length) throw new Error(`Invalid filing input: ${problems.join("; ")}`);
  return f as unknown as FilingInput;
}

/** Blocks the submission endpoint until `release()` is called. */
export class SubmissionGuard {
  private armed = true;
  public blockedRequests = 0;

  constructor(private readonly page: Page, private readonly pattern: string) {}

  async install(): Promise<void> {
    await this.page.route(this.pattern, (route: Route) => {
      if (this.armed && route.request().method() !== "GET") {
        this.blockedRequests += 1;
        return route.abort("blockedbyclient");
      }
      return route.continue();
    });
  }

  release(): void {
    this.armed = false;
  }
}

async function audit(dir: string, event: Record<string, unknown>): Promise<void> {
  const line = JSON.stringify({ at: new Date().toISOString(), ...event });
  await appendFile(path.join(dir, "audit.jsonl"), line + "\n", "utf8");
}

export async function runFiling(opts: RunOptions): Promise<FilingResult> {
  const { page, baseUrl, credentials, approver, artifactsDir } = opts;
  const filing = validateFiling(opts.filing);
  await mkdir(artifactsDir, { recursive: true });
  const guard = new SubmissionGuard(page, opts.submitEndpoint ?? "**/api/filings");
  await guard.install();
  await audit(artifactsDir, { event: "start", baseUrl, caseNumber: filing.caseNumber, account: credentials.username });

  // 1. Sign in. The password goes straight into the browser field, nowhere else.
  await page.goto(new URL("/", baseUrl).toString());
  await page.getByLabel("Username").fill(credentials.username);
  await page.getByLabel("Password").fill(credentials.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  const outcome = await Promise.race([
    page.waitForURL("**/filing.html").then(() => "ok" as const),
    page.locator("#login-error").waitFor({ state: "visible" }).then(() => "error" as const),
  ]);
  if (outcome === "error") {
    const reason = `Login failed: ${await page.locator("#login-error").innerText()}`;
    await audit(artifactsDir, { event: "aborted", reason });
    return { status: "aborted", reason };
  }

  // 2. Fill the form and go to the review step (reversible).
  await page.getByLabel("Case number").fill(filing.caseNumber);
  await page.getByLabel("Court").selectOption({ label: filing.court });
  await page.getByLabel("Filing type").selectOption(filing.filingType);
  await page.getByLabel("Filer name").fill(filing.filerName);
  await page.getByLabel("Document title").fill(filing.documentTitle);
  await page.getByLabel(/I certify/).check();
  await page.getByRole("button", { name: "Review filing" }).click();
  await page.locator("#step-review").waitFor({ state: "visible" });

  // 3. Read back what the portal will actually submit and compare.
  const shown: Record<string, string> = {};
  for (const key of FIELDS) {
    shown[key] = (await page.locator(`#review-list [data-field="${key}"]`).innerText()).trim();
  }
  const mismatches = FIELDS.filter((k) => shown[k] !== filing[k]);
  if (mismatches.length) {
    const reason = `Review page does not match intended data: ${mismatches.join(", ")}`;
    await audit(artifactsDir, { event: "aborted", reason });
    return { status: "aborted", reason };
  }

  const summary: FilingSummary = {
    portal: new URL(baseUrl).origin,
    account: credentials.username,
    caseNumber: shown.caseNumber,
    court: shown.court,
    filingType: shown.filingType,
    filerName: shown.filerName,
    documentTitle: shown.documentTitle,
  };
  const token = approvalToken(summary);
  const screenshotPath = path.join(artifactsDir, `review-${filing.caseNumber}-${token}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await audit(artifactsDir, { event: "awaiting_approval", token, summary, screenshotPath });

  // 4. The gate.
  const decision = await approver.decide({ summary, token, screenshotPath });
  await audit(artifactsDir, { event: "decision", token, ...decision });
  if (!decision.approved) {
    return { status: "blocked", reason: decision.reason, token, summary, screenshotPath };
  }

  // 5. Approved: release the guard and perform the irreversible click once.
  guard.release();
  await page.getByRole("button", { name: "Submit filing" }).click();
  const confirmation = page.locator("#confirmation");
  const failure = page.locator("#submit-error");
  await Promise.race([confirmation.waitFor({ state: "visible" }), failure.waitFor({ state: "visible" })]);
  if (await failure.isVisible()) {
    const reason = await failure.innerText();
    await audit(artifactsDir, { event: "submit_failed", token, reason });
    return { status: "aborted", reason, token, summary, screenshotPath };
  }
  const number = (await confirmation.innerText()).trim();
  await page.screenshot({ path: path.join(artifactsDir, `confirmation-${number}.png`), fullPage: true });
  await audit(artifactsDir, { event: "submitted", token, confirmation: number });
  return { status: "submitted", reason: decision.reason, token, summary, screenshotPath, confirmation: number };
}
