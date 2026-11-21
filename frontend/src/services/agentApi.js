const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

export async function runAgent({ agentId, sessionId, input, history = [] }, request = fetch) {
  const response = await request(`${API_BASE_URL}/api/v1/agent-runs`, {
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
    const message = await response.text();
    throw new Error(`Agent request failed (${response.status}): ${message}`);
  }

  return response.json();
}
