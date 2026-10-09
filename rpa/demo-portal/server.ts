/**
 * Demo "e-filing portal" used to exercise the RPA agent locally and in CI.
 *
 * It mimics the shape of a real court/agency portal: a login page, a filing
 * form, a review step and a final, irreversible "Submit filing" button. All
 * data lives in memory. Nothing here talks to the outside world.
 *
 * The demo account is `demo.filer` with password `DEMO_PORTAL_PASSWORD`
 * (default `demo-only-password`). It is a throwaway credential for a local
 * fake site, documented on purpose.
 */
import { randomBytes } from "node:crypto";
import path from "node:path";
import express, { type NextFunction, type Request, type Response } from "express";

export interface StoredFiling {
  confirmation: string;
  submittedAt: string;
  submittedBy: string;
  caseNumber: string;
  court: string;
  filingType: string;
  filerName: string;
  documentTitle: string;
}

export function createPortal(opts: { password?: string } = {}) {
  const password = opts.password ?? process.env.DEMO_PORTAL_PASSWORD ?? "demo-only-password";
  const users = new Map([["demo.filer", password]]);
  const sessions = new Map<string, string>();
  const filings: StoredFiling[] = [];

  const app = express();
  app.disable("x-powered-by");
  app.use(express.json({ limit: "64kb" }));

  const sessionUser = (req: Request): string | undefined => {
    const cookie = req.headers.cookie ?? "";
    const match = /(?:^|;\s*)portal_session=([a-f0-9]+)/.exec(cookie);
    return match ? sessions.get(match[1]) : undefined;
  };

  const requireSession = (req: Request, res: Response, next: NextFunction) => {
    const user = sessionUser(req);
    if (!user) return res.status(401).json({ error: "Not signed in" });
    res.locals.user = user;
    next();
  };

  app.post("/api/login", (req, res) => {
    const { username, password: given } = req.body ?? {};
    if (typeof username !== "string" || users.get(username) !== given) {
      return res.status(401).json({ error: "Invalid username or password" });
    }
    const token = randomBytes(16).toString("hex");
    sessions.set(token, username);
    res.setHeader("Set-Cookie", `portal_session=${token}; HttpOnly; SameSite=Strict; Path=/`);
    res.json({ ok: true, user: username });
  });

  app.get("/api/me", requireSession, (_req, res) => res.json({ user: res.locals.user }));

  app.post("/api/filings", requireSession, (req, res) => {
    const b = req.body ?? {};
    const required = ["caseNumber", "court", "filingType", "filerName", "documentTitle"] as const;
    const missing = required.filter((k) => typeof b[k] !== "string" || !b[k].trim());
    if (missing.length) return res.status(422).json({ error: `Missing: ${missing.join(", ")}` });
    if (b.certified !== true) return res.status(422).json({ error: "Certification is required" });
    const filing: StoredFiling = {
      confirmation: `EF-2026-${String(filings.length + 1).padStart(6, "0")}`,
      submittedAt: new Date().toISOString(),
      submittedBy: res.locals.user,
      caseNumber: b.caseNumber,
      court: b.court,
      filingType: b.filingType,
      filerName: b.filerName,
      documentTitle: b.documentTitle,
    };
    filings.push(filing);
    res.status(201).json(filing);
  });

  // Test-only inspection hooks (a real portal obviously has none of these).
  app.get("/__test__/filings", (_req, res) => res.json(filings));
  app.post("/__test__/reset", (_req, res) => {
    filings.length = 0;
    sessions.clear();
    res.json({ ok: true });
  });

  app.use(express.static(path.join(__dirname, "public")));
  return app;
}

if (require.main === module) {
  const port = Number(process.env.PORT ?? 4317);
  createPortal().listen(port, "127.0.0.1", () => {
    console.log(`Demo e-filing portal listening on http://127.0.0.1:${port}`);
  });
}
