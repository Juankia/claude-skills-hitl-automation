import { spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { resetPortal, submittedFilings } from "./helpers";

const ROOT = path.resolve(__dirname, "..");
const TSX = path.join(ROOT, "node_modules", ".bin", process.platform === "win32" ? "tsx.cmd" : "tsx");

function agent(args: string[], baseURL: string) {
  return spawnSync(TSX, ["src/cli.ts", "--base-url", baseURL, ...args], {
    cwd: ROOT,
    encoding: "utf8",
    shell: process.platform === "win32",
    env: {
      ...process.env,
      PORTAL_USERNAME: "demo.filer",
      PORTAL_PASSWORD: "demo-only-password",
      PORTAL_CREDENTIAL_SOURCE: "env",
    },
    input: "", // non-interactive: stdin is not a TTY
    timeout: 60_000,
  });
}

test.beforeEach(async ({ request }) => resetPortal(request));

test("CLI: non-interactive run stops at the gate (exit 3), approved re-run submits (exit 0)", async ({ baseURL, request }, testInfo) => {
  const artifacts = testInfo.outputPath("cli-artifacts");
  const blocked = agent(["--filing", "examples/filing.json", "--artifacts", artifacts], baseURL!);
  expect(blocked.status, blocked.stderr).toBe(3);
  expect(blocked.stdout).toContain("APPROVAL REQUIRED");
  expect(blocked.stdout).not.toContain("demo-only-password");
  expect(await submittedFilings(request)).toHaveLength(0);

  const token = /--approve-token ([0-9a-f]{12})/.exec(blocked.stdout)?.[1];
  expect(token).toBeTruthy();
  const approved = agent(["--filing", "examples/filing.json", "--artifacts", artifacts, "--approve-token", token!], baseURL!);
  expect(approved.status, approved.stderr).toBe(0);
  expect(approved.stdout).toMatch(/Confirmation number: EF-2026-\d{6}/);
  expect(await submittedFilings(request)).toHaveLength(1);
});

test("CLI: refuses to run when the filing-prep report has blocking gaps", async ({ baseURL, request }, testInfo) => {
  const report = testInfo.outputPath("gap_report.json");
  writeFileSync(report, JSON.stringify({ status: "gaps_found", summary: { blocking: 2 } }));
  const result = agent(["--filing", "examples/filing.json", "--checklist", report], baseURL!);
  expect(result.status).toBe(1);
  expect(result.stderr).toContain("refusing to run");
  expect(await submittedFilings(request)).toHaveLength(0);
});
