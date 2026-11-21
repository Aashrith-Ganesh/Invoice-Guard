export function paymentToken(fragment) {
  const token = fragment.slice(1);
  return /^sim_[0-9a-f]{32}\.[0-9a-f]{64}$/.test(token) ? token : null;
}

export function createHostedPayment(origin, token, request = fetch) {
  let inFlight;
  async function call(operation) {
    const response = await request(`${origin}/api/v1/simulated-payment/${operation}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "omit",
      redirect: "error",
      cache: "no-store",
      referrerPolicy: "no-referrer",
      body: JSON.stringify({ token }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error?.message || "The simulation link is unavailable.");
    return payload;
  }
  return {
    load: () => call("status"),
    simulate: () => inFlight ??= call("simulate").finally(() => { inFlight = null; }),
  };
}
