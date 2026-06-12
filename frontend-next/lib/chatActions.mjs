const RETRY_COMMANDS = new Set([
  "retry",
  "rety",
  "try again",
  "again",
  "regenerate",
  "rerun",
  "redo",
]);

const DETAIL_COMMANDS = new Set([
  "explain more",
  "more details",
  "detail",
  "details",
  "elaborate",
]);

const HINDI_COMMANDS = new Set([
  "in hindi",
  "hindi",
  "translate hindi",
  "answer in hindi",
]);

function normalize(value) {
  return value.trim().toLowerCase().replace(/[.!?]+$/g, "").replace(/\s+/g, " ");
}

export function isRetryCommand(value) {
  const text = normalize(value);
  return RETRY_COMMANDS.has(text) || DETAIL_COMMANDS.has(text) || HINDI_COMMANDS.has(text);
}

export function resolveOutgoingQuestion(input, lastUserQuestion) {
  const command = normalize(input);
  const previous = lastUserQuestion.trim();
  if (!previous || !isRetryCommand(input)) return input.trim();

  if (DETAIL_COMMANDS.has(command)) {
    return `Explain this in more practical detail with clear next steps: ${previous}`;
  }

  if (HINDI_COMMANDS.has(command)) {
    return `Answer this in Hindi with the same legal grounding: ${previous}`;
  }

  return `Please retry and improve the previous answer for this question: ${previous}`;
}

export function makeThreadTitle(question) {
  const text = normalize(question);

  if (/\brti\b|right to information|information application/.test(text)) return "RTI Filing Help";
  if (/police|arrest|custody|fir/.test(text)) return "Police Arrest Rights";
  if (/refund|defective|consumer|shop|seller|product/.test(text)) return "Consumer Refund Issue";
  if (/salary|employer|wage|labour|labor|job/.test(text)) return "Salary And Labour Rights";
  if (/murder|bns|bharatiya nyaya|criminal|punishment/.test(text)) return "Criminal Law Question";
  if (/registration|property|land|document|deed/.test(text)) return "Property Registration";
  if (/marriage|divorce|dowry|domestic|women|family/.test(text)) return "Family Law Guidance";

  const cleaned = question
    .trim()
    .replace(/[^\p{L}\p{N}\s]/gu, "")
    .replace(/\s+/g, " ");
  if (!cleaned) return "New Legal Chat";

  const words = cleaned.split(" ").filter(Boolean).slice(0, 5);
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}

