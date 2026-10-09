import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { TokenApprover, approvalToken } from "../src/approval";
import { SubmissionGuard, runFiling } from "../src/agent";
import { RecordingApprover, demoCredentials, filing, resetPortal, submittedFilings } from "./helpers";

test.beforeEach(async ({ request }) => {
  await resetPortal(request);
});

const run = (page: any, baseURL: string | undefined, testInfo: any, approver: any, overrides = {}) =>
  runFiling({
    page,
    baseUrl: baseURL!,
    filing: { ...filing, ...overrides },
    credentials: demoCredentials,
    approver,
    artifactsDir: testInfo.outputPath("artifacts"),
  });

test("stops at the review page and does NOT submit without approval", async ({ page, baseURL, request }, testInfo) => {
  const result = await run(page, baseURL, testInfo, new TokenApprover(undefined));

  expect(result.status).toBe("blocked");
  expect(result.reason).toMatch(/No approval token/);
  expect(await submittedFilings(request)).toHaveLength(0);
  // The browser is parked on the review step with the irreversible button untouched.
  await expect(page.getByRole("button", { name: "Submit filing" })).toBeEnabled();
  await expect(page.locator("#step-done")).toBeHidden();
  // Evidence for the human: a screenshot and an audit trail without secrets.
  expect(existsSync(result.screenshotPath!)).toBe(true);
  const auditLog = readFileSync(path.join(testInfo.outputPath("artifacts"), "audit.jsonl"), "utf8");
  expect(auditLog).toContain('"event":"awaiting_approval"');
  expect(auditLog).not.toContain(demoCredentials.password);
});

test("a wrong approval token is rejected", async ({ page, baseURL, request }, testInfo) => {
  const result = await run(page, baseURL, testInfo, new TokenApprover("000000000000"));
  expect(result.status).toBe("blocked");
  expect(result.reason).toMatch(/does not match/);
  expect(await submittedFilings(request)).toHaveLength(0);
});

test("human denial at the prompt blocks submission", async ({ page, baseURL, request }, testInfo) => {
  const approver = new RecordingApprover(() => false);
  const result = await run(page, baseURL, testInfo, approver);
  expect(result.status).toBe("blocked");
  expect(approver.requests).toHaveLength(1);
  // The summary shown to the human is what the portal displayed on its review page.
  expect(approver.requests[0].summary).toMatchObject({ caseNumber: filing.caseNumber, account: "demo.filer" });
  expect(await submittedFilings(request)).toHaveLength(0);
});

test("the matching token submits exactly once", async ({ page, baseURL, request }, testInfo) => {
  const first = await run(page, baseURL, testInfo, new TokenApprover(undefined));
  expect(first.status).toBe("blocked");

  const second = await run(page, baseURL, testInfo, new TokenApprover(first.token));
  expect(second.status).toBe("submitted");
  expect(second.confirmation).toMatch(/^EF-2026-\d{6}$/);
  const stored = (await submittedFilings(request)) as Array<Record<string, string>>;
  expect(stored).toHaveLength(1);
  expect(stored[0]).toMatchObject({ caseNumber: filing.caseNumber, submittedBy: "demo.filer" });
});

test("a token is bound to the reviewed content", async ({ page, baseURL, request }, testInfo) => {
  const original = await run(page, baseURL, testInfo, new TokenApprover(undefined));
  const changed = await run(page, baseURL, testInfo, new TokenApprover(original.token), {
    documentTitle: "Motion to Dismiss",
  });
  expect(changed.status).toBe("blocked");
  expect(changed.token).not.toBe(original.token);
  expect(await submittedFilings(request)).toHaveLength(0);
});

test("network guard aborts submit requests even if the button is clicked before approval", async ({ page, request }) => {
  const guard = new SubmissionGuard(page, "**/api/filings");
  await guard.install();
  await page.goto("/");
  await page.getByLabel("Username").fill(demoCredentials.username);
  await page.getByLabel("Password").fill(demoCredentials.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByLabel("Case number").fill(filing.caseNumber);
  await page.getByLabel("Court").selectOption({ label: filing.court });
  await page.getByLabel("Filing type").selectOption(filing.filingType);
  await page.getByLabel("Filer name").fill(filing.filerName);
  await page.getByLabel("Document title").fill(filing.documentTitle);
  await page.getByLabel(/I certify/).check();
  await page.getByRole("button", { name: "Review filing" }).click();

  await page.getByRole("button", { name: "Submit filing" }).click(); // simulated rogue click
  await expect(page.locator("#submit-error")).toContainText("Submission failed");
  expect(guard.blockedRequests).toBe(1);
  expect(await submittedFilings(request)).toHaveLength(0);
});

test("invalid credentials abort before any form is filled", async ({ page, baseURL, request }, testInfo) => {
  const result = await runFiling({
    page,
    baseUrl: baseURL!,
    filing,
    credentials: { ...demoCredentials, password: "wrong" },
    approver: new TokenApprover("irrelevant"),
    artifactsDir: testInfo.outputPath("artifacts"),
  });
  expect(result.status).toBe("aborted");
  expect(result.reason).toMatch(/Login failed/);
  expect(await submittedFilings(request)).toHaveLength(0);
});

test("invalid filing input is rejected before the browser does anything", async ({ page, baseURL }, testInfo) => {
  await expect(run(page, baseURL, testInfo, new TokenApprover("x"), { caseNumber: "1234" })).rejects.toThrow(
    /caseNumber must look like/,
  );
  expect(page.url()).toBe("about:blank");
});

test("approval token is deterministic and order-independent", () => {
  const summary = { portal: "p", account: "a", caseNumber: "c", court: "co", filingType: "f", filerName: "n", documentTitle: "d" };
  const reordered = Object.fromEntries(Object.entries(summary).reverse()) as typeof summary;
  expect(approvalToken(summary)).toBe(approvalToken(reordered));
  expect(approvalToken(summary)).toMatch(/^[0-9a-f]{12}$/);
  expect(approvalToken({ ...summary, court: "other" })).not.toBe(approvalToken(summary));
});
