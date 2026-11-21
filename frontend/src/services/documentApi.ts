export type InvoiceJob = {
  job_id: string;
  status: "pending" | "running" | "completed" | "partially_completed" | "failed" | "rejected";
};

export type InvoiceResult = InvoiceJob & {
  invoice?: Record<string, unknown>;
  annotations?: unknown;
};

export function createSarvamClient(
  base = "/api/agents/sarvam",
  request: typeof fetch = fetch,
) {
  async function send<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await request(`${base}${path}`, init);
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const detail = typeof body?.detail === "string" ? body.detail : null;
      throw new Error(detail ?? `Sarvam request failed (${response.status})`);
    }
    return response.json() as Promise<T>;
  }

  return {
    submitInvoice(file: File, signal?: AbortSignal) {
      const body = new FormData();
      body.append("file", file);
      return send<InvoiceJob>("/invoices", { method: "POST", body, signal });
    },
    getInvoice(jobId: string, signal?: AbortSignal) {
      return send<InvoiceResult>(`/invoices/${encodeURIComponent(jobId)}`, { signal });
    },
    translate(text: string, targetLanguage: string, sourceLanguage = "en-IN") {
      return send<{ text: string; language: string }>("/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          source_language: sourceLanguage,
          target_language: targetLanguage,
        }),
      });
    },
  };
}
