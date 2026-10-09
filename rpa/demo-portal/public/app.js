(async () => {
  const me = await fetch("/api/me");
  if (!me.ok) { location.href = "/"; return; }
  document.getElementById("who").textContent = `Signed in as ${(await me.json()).user}`;

  const form = document.getElementById("filing-form");
  const show = (id) => ["step-form", "step-review", "step-done"].forEach((s) => (document.getElementById(s).hidden = s !== id));
  let pending = null;

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    pending = {
      caseNumber: form.caseNumber.value.trim(),
      court: form.court.value,
      filingType: form.filingType.value,
      filerName: form.filerName.value.trim(),
      documentTitle: form.documentTitle.value.trim(),
      certified: form.certify.checked,
    };
    for (const [key, value] of Object.entries(pending)) {
      const dd = document.querySelector(`[data-field="${key}"]`);
      if (dd) dd.textContent = value;
    }
    show("step-review");
  });

  document.getElementById("back").addEventListener("click", () => show("step-form"));

  document.getElementById("submit-filing").addEventListener("click", async (e) => {
    e.target.disabled = true;
    const err = document.getElementById("submit-error");
    try {
      const res = await fetch("/api/filings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(pending) });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
      document.getElementById("confirmation").textContent = body.confirmation;
      show("step-done");
    } catch (ex) {
      err.textContent = `Submission failed: ${ex.message}`;
      err.hidden = false;
      e.target.disabled = false;
    }
  });
})();
