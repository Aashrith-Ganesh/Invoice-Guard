import assert from "node:assert/strict";
import test from "node:test";
import { bankReference } from "../bank-reference.js";

test("only opaque bank references are forwarded", () => {
  assert.equal(bankReference(" ref:vendor-1 "), "ref:vendor-1");
  assert.equal(bankReference("demo:vendor-1:current"), "demo:vendor-1:current");
  assert.equal(bankReference("123456789012"), "");
  assert.equal(bankReference("ref:"), "");
  assert.equal(bankReference(""), "");
});
