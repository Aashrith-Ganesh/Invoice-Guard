const apiOrigin = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export async function runAgent({ agentId, sessionId, input, history = [] }, authenticatedFetch) {
  const response = await authenticatedFetch(`${apiOrigin}/api/v1/agent-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agent_id: agentId,
      session_id: sessionId,
      input: { type: "text", content: input },
      history,
    }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.error?.message || `Agent request failed (${response.status})`);
  }
  return response.json();
}
