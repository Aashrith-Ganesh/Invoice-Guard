import { createHostedPayment, paymentToken } from "./hosted-payment.js";

const get = (id) => document.getElementById(id);
const write = (id, text) => { get(id).textContent = text; };
const token = paymentToken(location.hash);
const action = get("simulate-payment");

function render(payment) {
  write("invoice-reference", payment.invoice_reference);
  write("vendor-name", payment.vendor_name);
  write("amount", `${payment.amount} ${payment.currency}`);
  write("payment-reference", payment.payment_reference);
  write("expires-at", new Date(payment.expires_at).toLocaleString());
  write("payment-status", payment.status);
  write("payment-message", payment.status === "SUCCESS"
    ? `Simulation complete. Confirmation: ${payment.payment_reference}` : "");
  get("payment-details").hidden = false;
  action.hidden = payment.status !== "READY";
}

if (!token) {
  write("payment-message", "This simulation link is invalid.");
} else {
  const origin = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
  const client = createHostedPayment(origin, token);
  client.load().then(render).catch((error) => write("payment-message", error.message));
  action.addEventListener("click", async () => {
    action.disabled = true;
    write("payment-message", "Running simulation…");
    try {
      render(await client.simulate());
    } catch (error) {
      write("payment-message", error.message);
    } finally {
      action.disabled = false;
    }
  });
}
