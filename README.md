# LLM Arena

Ask one question, get answers from several real LLMs side by side, and see an
independent judge model pick the best one — like a built-in "Claude vs GPT vs
Llama" comparison view.

## What changed from the old version

The previous project's "4 agents" were really just 4 different prompts run
against the *same* 1B Ollama model — not a genuine comparison of different
LLMs. This rebuild fixes that:

- **Contestants are real, distinct models**, configured in one place
  (`CONTESTANTS` env var). Mix local Ollama models, Gemini, and any
  OpenAI-compatible API (OpenAI, Groq, OpenRouter, etc.) — any combination.
- **The judge is a separate, configurable model** (`JUDGE_MODEL`), so it
  isn't grading its own homework.
- **The judge scores each real answer individually** and picks a winner with
  a stated reason, instead of writing a brand-new synthesized answer like
  before.
- Clean provider abstraction (`core/services/providers.py`) — adding a new
  model to compare is a one-line config change, not new agent code.
- Frontend is a proper side-by-side comparison grid (like an AI arena),
  streaming each model's answer live, with the winning card highlighted.

## Project structure

```
llm-arena/
├── backend/
│   ├── backend/            # Django project settings/urls
│   ├── core/                # the app
│   │   ├── models.py        # Question, ModelResponse, Judgment
│   │   ├── serializers.py
│   │   ├── views.py         # /ask, /ask/stream (SSE), /history...
│   │   └── services/
│   │       ├── providers.py # pluggable LLM providers (Ollama/Gemini/OpenAI)
│   │       └── judge.py     # scores + ranks the answers
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── App.jsx           # main comparison UI
    │   ├── api.js            # fetch + SSE client
    │   └── components/
    │       ├── ResponseCard.jsx   # one model's answer
    │       ├── JudgePanel.jsx     # verdict + reasoning
    │       └── HistoryDrawer.jsx
    └── package.json
```

## Setup

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # then edit .env, see below

python manage.py migrate
python manage.py runserver
```

### 2. Configure which models you're comparing

Edit `backend/.env`:

```env
# Comma-separated provider:model specs — these are the columns you'll see
CONTESTANTS=ollama:llama3.2:1b,ollama:qwen2.5:3b,ollama:phi3:mini

# A separate model that evaluates the answers above and picks a winner
JUDGE_MODEL=gemini:gemini-2.5-flash
GEMINI_API_KEY=your-key-here
```

To compare real different models locally with Ollama, pull a few:

```bash
ollama pull llama3.2:1b
ollama pull qwen2.5:3b
ollama pull phi3:mini
```

You can also mix in hosted models as contestants, e.g.:

```env
CONTESTANTS=ollama:llama3.2:1b,gemini:gemini-2.5-flash,openai:gpt-4o-mini
OPENAI_API_KEY=your-key-here
```

Any contestant that fails to start (missing key, model not pulled) is
skipped automatically instead of crashing the whole comparison.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Visit the printed local URL. Ask a question, watch each model answer live,
and see the judge's verdict once everyone's done.

## How it works

1. `POST/GET /api/ask/stream/` fans the prompt out to every configured
   contestant in parallel and streams each one's tokens over Server-Sent
   Events as they're generated.
2. Once every contestant has finished, the backend sends the question and
   all raw answers to the judge model with a strict scoring rubric and asks
   for structured JSON: a score + one-line verdict per answer, an overall
   winner, why it won, and how much the models agreed.
3. Everything is persisted (`Question`, `ModelResponse`, `Judgment`) so
   history is browsable and answers/scores never need to be regenerated.

If no judge model is reachable, the app falls back to picking the most
substantive answer and says so plainly in the verdict — it never silently
pretends to have judged something it didn't.
