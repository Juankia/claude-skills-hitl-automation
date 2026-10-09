import { PassThrough } from "node:stream";
import { expect, test } from "@playwright/test";
import { PromptApprover, type ApprovalRequest } from "../src/approval";
import { CredentialsError, describeCredentials, resolveCredentials, type Keychain } from "../src/credentials";

const request: ApprovalRequest = {
  summary: { portal: "http://x", account: "a", caseNumber: "26-CV-00001", court: "c", filingType: "motion", filerName: "n", documentTitle: "d" },
  token: "abc123def456",
  screenshotPath: "review.png",
};

async function promptWith(answer: string | null) {
  const input = new PassThrough();
  const output = new PassThrough();
  let printed = "";
  output.on("data", (chunk) => (printed += chunk.toString()));
  const pending = new PromptApprover(input, output).decide(request);
  if (answer === null) input.end();
  else input.write(answer + "\n");
  return { decision: await pending, printed };
}

test.describe("PromptApprover", () => {
  test("requires the exact token; 'y' is not enough", async () => {
    expect((await promptWith("y")).decision.approved).toBe(false);
    expect((await promptWith("yes")).decision.approved).toBe(false);
  });

  test("approves when the operator types the token and shows the summary first", async () => {
    const { decision, printed } = await promptWith("abc123def456");
    expect(decision).toMatchObject({ approved: true, method: "prompt" });
    expect(printed).toContain("APPROVAL REQUIRED");
    expect(printed).toContain("26-CV-00001");
  });

  test("closed stdin counts as denial", async () => {
    expect((await promptWith(null)).decision.approved).toBe(false);
  });
});

class FakeKeychain implements Keychain {
  constructor(private readonly entries: Record<string, string>, private readonly fail = false) {}
  async getPassword(_service: string, account: string) {
    if (this.fail) throw new Error("keychain locked");
    return this.entries[account] ?? null;
  }
  async findCredentials() {
    if (this.fail) throw new Error("keychain locked");
    return Object.entries(this.entries).map(([account, password]) => ({ account, password }));
  }
}

test.describe("resolveCredentials", () => {
  test("prefers the OS keychain", async () => {
    const creds = await resolveCredentials({
      keychain: new FakeKeychain({ "demo.filer": "from-keychain" }),
      env: { PORTAL_USERNAME: "demo.filer", PORTAL_PASSWORD: "from-env" },
    });
    expect(creds).toEqual({ username: "demo.filer", password: "from-keychain", source: "keychain" });
  });

  test("finds the first account for the service when none is given", async () => {
    const creds = await resolveCredentials({ keychain: new FakeKeychain({ "ops.user": "pw" }), env: {} });
    expect(creds.username).toBe("ops.user");
  });

  test("falls back to env when the keychain is missing or locked", async () => {
    const env = { PORTAL_USERNAME: "demo.filer", PORTAL_PASSWORD: "from-env" };
    expect((await resolveCredentials({ keychain: null, env })).source).toBe("env");
    expect((await resolveCredentials({ keychain: new FakeKeychain({}, true), env })).source).toBe("env");
  });

  test("fails clearly when nothing is configured", async () => {
    await expect(resolveCredentials({ keychain: null, env: {} })).rejects.toBeInstanceOf(CredentialsError);
  });

  test("never prints the password", () => {
    const text = describeCredentials({ username: "u", password: "s3cret", source: "env" });
    expect(text).not.toContain("s3cret");
    expect(text).toContain("redacted");
  });
});
