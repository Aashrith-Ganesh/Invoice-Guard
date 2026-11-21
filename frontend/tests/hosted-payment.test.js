import assert from "node:assert/strict";
import test from "node:test";

import { paymentToken, createHostedPayment } from "../hosted-payment.js";

const token = `sim_${"a".repeat(32)}.${"b".repeat(64)}`;

test("validates the fragment before making a request", () => {
  assert.equal(paymentToken(`#${token}`), token);
  assert.equal(paymentToken("#broken"), null);
  assert.equal(paymentToken(""), null);
});

test("hosted client reads status, submits once in flight and reloads persisted status", async () => {
  let status = "READY";
  let count = 0;
  const fetch = async (url, options) => {
    assert.equal(options.method, "POST");
    assert.equal(options.credentials, "omit");
    assert.equal(options.cache, "no-store");
    assert.equal(new URL(url, "https://example.test").hash, "");
    assert.equal(JSON.parse(options.body).token, token);
    assert.equal(url.includes(token), false);
    if (url.endsWith("/simulate")) {
      count++;
      await Promise.resolve();
      status = "SUCCESS";
    }
    return { ok: true, json: async () => ({ status, payment_reference: "sim_demo" }) };
  };
  const client = createHostedPayment("", token, fetch);
  assert.equal((await client.load()).status, "READY");
  const [first, repeat] = await Promise.all([client.simulate(), client.simulate()]);
  assert.equal(count, 1);
  assert.deepEqual(first, repeat);
  assert.deepEqual(await createHostedPayment("", token, fetch).load(), first);
});

test("expired or invalid links surface a readable error", async () => {
  const client = createHostedPayment("", token, async () => ({
    ok: false, json: async () => ({ error: { message: "This simulation link has expired." } }),
  }));
  await assert.rejects(client.load(), /simulation link has expired/);
});
