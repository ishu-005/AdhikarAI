import assert from "node:assert/strict";
import {
  isRetryCommand,
  makeThreadTitle,
  resolveOutgoingQuestion,
} from "./chatActions.mjs";

assert.equal(isRetryCommand("retry"), true);
assert.equal(isRetryCommand("rety"), true);
assert.equal(isRetryCommand("try again"), true);
assert.equal(isRetryCommand("How do I file an RTI application?"), false);

assert.equal(
  resolveOutgoingQuestion("rety", "How do I file an RTI application?"),
  "Please retry and improve the previous answer for this question: How do I file an RTI application?"
);

assert.equal(
  resolveOutgoingQuestion("explain more", "What are my rights if police arrest me?"),
  "Explain this in more practical detail with clear next steps: What are my rights if police arrest me?"
);

assert.equal(
  resolveOutgoingQuestion("retry", ""),
  "retry"
);

assert.equal(makeThreadTitle("How do I file an RTI application?"), "RTI Filing Help");
assert.equal(makeThreadTitle("A shop refused to refund a defective product. What can I do?"), "Consumer Refund Issue");
assert.equal(makeThreadTitle("What are my rights if police arrest me?"), "Police Arrest Rights");
assert.equal(makeThreadTitle("What documents must be registered under the Registration Act?"), "Property Registration");

console.log("chatActions tests passed");
