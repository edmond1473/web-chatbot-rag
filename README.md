# Ask about Edmond — a portfolio assistant chatbot

A small web chatbot with document-grounded Q&A (a simplified RAG setup). Visitors to Edmond's portfolio site chat with an assistant that answers questions about him — his education, skills, projects, and experience — using only the resume and project notes baked into the backend.

## What it does

- Serves a single-page chat UI.
- Takes a visitor's message, sends it (along with that visitor's recent conversation history) to an LLM, and returns the reply.
- Keeps each visitor's conversation separate using a signed Flask session cookie, so different browsers don't share history.
- Constrains the assistant, via a system prompt, to answer **only** from a fixed resume/portfolio knowledge base and to refuse off-topic questions.

## Key features

- **Document-grounded Q&A (simplified RAG).** The entire knowledge base — a `<resume>` block plus a set of `<documents>` describing individual projects — is written verbatim into the system prompt. There is **no vector store, no embeddings, and no retrieval step**: the full context is sent to the model on every request. (See the "How the RAG works" section below.)
- **Prompt-based guardrails.** The system prompt instructs the model to answer only about Edmond, to refuse unrelated requests (news, homework, coding, chit-chat, translation), to never invent facts, and to say "I don't know, contact Edmond" when the answer isn't in the documents. These rules are enforced by the model, not by separate code.
- **Multilingual replies.** The system prompt tells the model to reply in Chinese, English, or Bahasa Melayu, following the visitor's language.
- **Per-visitor session memory.** Conversation history is stored in the Flask session. History is capped at the last 12 messages (6 turns) to control token cost and stay under the browser cookie size limit, and is trimmed so the first stored message is always a user turn.
- **Input validation.** Empty messages are rejected; messages longer than 1000 characters are rejected.
- **Reset endpoint.** A "新对话" (New chat) button clears the current visitor's history.
- **API key stays server-side.** The key is read from an environment variable in the backend only. The frontend talks solely to the Flask backend and never sees or calls the LLM provider directly.
- **Polished single-file frontend.** Welcome screen with clickable suggestion chips, typing indicator, auto-growing input, Enter-to-send / Shift+Enter-for-newline, friendly error bubbles, XSS-safe rendering (`textContent`), responsive layout, and reduced-motion support.

## How the RAG works

This is the "stuff everything into the context window" flavour of RAG, not a retrieval pipeline:

- Edmond's resume and per-project notes live inside `SYSTEM_PROMPT` in `app.py` as `<resume>` and `<documents>` blocks.
- On every `/chat` request, that whole system prompt is sent to the model unchanged, together with the recent conversation history.
- The model is instructed to ground its answers strictly in those blocks and to refuse anything they don't cover.

There is no similarity search, chunking, or embedding index — the "retrieval" is simply that all documents are always present in the prompt.

## Tech stack

- **Python 3** + **Flask** — backend, routing, and session management.
- **Anthropic Python SDK** (`anthropic`) — pointed at DeepSeek's Anthropic-compatible endpoint:
  - `base_url="https://api.deepseek.com/anthropic"`
  - model `deepseek-v4-flash`
  - `max_tokens=1024`
- **Frontend** — a single `templates/index.html` file (plain HTML + CSS + vanilla JavaScript, no build step, no external libraries).

## Setup

Requirements: Python 3 and `pip3`.

1. Install dependencies:

   ```bash
   pip3 install -r requirements.txt
   ```

   (`requirements.txt` lists `flask` and `anthropic`.)

2. Set your API key as an environment variable. The key is **never** hard-coded — the app reads it from `DEEPSEEK_API_KEY` and will not start without it:

   ```bash
   export DEEPSEEK_API_KEY="your-deepseek-api-key"
   ```

3. (Optional) Set a stable Flask secret key so sessions survive restarts. If you skip this, the app generates a random one at startup, which invalidates all existing sessions each time you restart:

   ```bash
   export FLASK_SECRET_KEY="some-long-random-string"
   ```

## Run

```bash
python3 app.py
```

The app runs on port **5001** (port 5000 is avoided because macOS AirPlay Receiver can occupy it). Once it's running, open:

```
http://localhost:5001
```

Debug mode is enabled in the code, so it's set up for local development, not production.

## Notes

This project was built as part of a self-taught AI crash course.
