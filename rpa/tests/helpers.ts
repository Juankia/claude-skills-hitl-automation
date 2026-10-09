import type { APIRequestContext } from "@playwright/test";
import type { Approver, ApprovalDecision, ApprovalRequest } from "../src/approval";
import type { FilingInput } from "../src/agent";
import type { Credentials } from "../src/credentials";

export const filing: FilingInput = {
  caseNumber: "26-CV-01234",
  court: "Demo County District Court",
  filingType: "motion",
  filerName: "Dana Whitfield",
  documentTitle: "Motion to Extend Time to Respond",
};

export const demoCredentials: Credentials = {
  username: "demo.filer",
  password: "demo-only-password",
  source: "env",
};

export async function submittedFilings(request: APIRequestContext): Promise<unknown[]> {
  return (await request.get("/__test__/filings")).json();
}

export async function resetPortal(request: APIRequestContext): Promise<void> {
  await request.post("/__test__/reset");
}

/** Records what the human was shown and answers with a fixed decision. */
export class RecordingApprover implements Approver {
  public requests: ApprovalRequest[] = [];
  constructor(private readonly answer: (req: ApprovalRequest) => boolean) {}
  async decide(req: ApprovalRequest): Promise<ApprovalDecision> {
    this.requests.push(req);
    const approved = this.answer(req);
    return { approved, method: "prompt", reason: approved ? "test approved" : "test denied" };
  }
}
