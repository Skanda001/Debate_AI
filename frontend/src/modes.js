// Answer modes — each one rewrites the prompt before sending to the models.

export const MODES = [
  {
    id: "direct",
    label: "Direct",
    icon: "💬",
    prefix: "",
  },
  {
    id: "simple",
    label: "Simple",
    icon: "🪶",
    prefix:
      "Answer in the simplest possible way. Short sentences. No jargon. If you must use a technical term, define it in one line. Aim for ~100 words. ",
  },
  {
    id: "summary",
    label: "Summary",
    icon: "📝",
    prefix:
      "Summarize your answer as a compact bullet list (max 5 bullets). Then add a single 'TL;DR' line. ",
  },
  {
    id: "code",
    label: "Code",
    icon: "💻",
    prefix:
      "Respond with a complete, runnable code example in a fenced code block. Add short comments. After the code, give 2-3 bullet notes about pitfalls. Use the most idiomatic language for the task. ",
  },
  {
    id: "research",
    label: "Research",
    icon: "🔬",
    prefix:
      "Answer like a research brief. Structure it as: Background → Key findings (3-5) → Open questions. Cite well-known sources or studies where possible. Be precise, not vague. ",
  },
  {
    id: "detailed",
    label: "Detailed",
    icon: "📚",
    prefix:
      "Give a thorough, well-structured answer with sections and examples. Cover edge cases. Roughly 400-600 words. ",
  },
];

export function buildPrompt(question, modeId) {
  const mode = MODES.find((m) => m.id === modeId) || MODES[0];
  return mode.prefix ? mode.prefix + "\n\n" + question : question;
}