# Content Repurposing Pipeline

A multi-agent content pipeline: give it a source URL (or raw text) and a
target keyword, and it produces an SEO-briefed article, a critique-scored
draft, repurposed social variants (Twitter/X thread, LinkedIn post, email
snippet), and a relevant royalty-free image — with full cost/token tracking
per run.

Built as a portfolio-scale rebuild of a production content-automation system,
generalized so it isn't tied to any client's NDA'd data.

## Architecture

A **supervisor** multi-agent graph, built with LangGraph. Every specialist
agent does one job and reports back to the supervisor; the supervisor is the
only node that decides what runs next, based purely on what's present in
pipeline state.

```
                        ┌─────────────┐
          ┌────────────▶│  Supervisor │◀────────────┐
          │             └──────┬──────┘              │
          │                    │ routes by state      │
          │     ┌──────────────┼──────────────┐       │
          │     ▼              ▼              ▼       │
      scrape  summarize   seo_research      brief      │
          │     │              │              │        │
          └─────┴──────────────┴──────────────┴────────┤
                                                          │
              writer ──▶ critic ──(fails, under cap)──▶ writer (loop)
                │                                        │
                └──────────────┬─────────────────────────┘
                                ▼ (passes, or cap reached)
                          repurposer → image → assembler → END
```

**Why a supervisor instead of a fixed linear chain:** the pipeline has a real
branch (short source content skips the summarizer; a failing critique loops
back to the writer, up to a cap) and a real loop (critique → rewrite). A
supervisor that reads state and decides the next hop handles both cleanly,
without every agent needing to know about every other agent.

**Why the supervisor is a plain function, not an LLM call:** the routing
decision here is fully determined by what's in state — there's no judgment
call to make. A deterministic router is free, instant, and trivially unit
testable (see `tests/test_graph_smoke.py`, including a test that specifically
exercises the critique-loop-and-cap path). If the pipeline grows a branch
that genuinely needs judgment, swapping in an LLM-based structured-output
router is a one-function change — nothing else in the graph has to change.

### The scraped-content problem

Firecrawl can return a lot of text, and naively truncating it (e.g. first
1,000 characters) throws away whatever's at the end of the source — often
the conclusion, a key stat, or a call to action. Instead:

- Real token count is checked (via `tiktoken`, with a character-based
  fallback if the encoding file can't be downloaded).
- If it's under the configured threshold, it's passed through unchanged —
  no LLM call spent on something that didn't need summarizing.
- If it's over, it's **chunked and map-reduce summarized**: each chunk is
  summarized individually (preserving concrete facts/stats), then the
  partial summaries are combined into one dense summary. Every part of the
  source gets read; nothing is silently dropped.

### Confidence-gated critique loop

The critic scores the draft against the brief (keyword coverage, heading
coverage, length) and only "passes" it above a configurable threshold. A
failing draft loops back to the writer with specific issues to fix, capped
at `MAX_CRITIQUE_LOOPS` so a stubborn draft can't loop forever — it proceeds
anyway once the cap is hit, with the failing critique visible in the final
package rather than hidden.

## Stack

| Concern | Tool | Why |
|---|---|---|
| Orchestration | LangGraph | Supervisor + specialist agent graph |
| Structured LLM output | Instructor + any OpenAI-compatible LLM (Groq recommended — free tier, fast) | Every LLM call returns a validated Pydantic object, not a text blob to parse |
| Scraping | Firecrawl | Clean markdown extraction from source URLs |
| SEO research | Serper | Cheap, fast Google SERP data (2,500 free searches/month) |
| Images | Pexels | Fully free, real licensed photos — no AI-image copyright ambiguity |
| API | FastAPI | Async job pattern: `/generate` kicks off a background run, `/status/{run_id}` polls it |
| Retries | tenacity | Exponential backoff + jitter on every external call |
| Logging | structlog | Structured, run_id-tagged logs traceable end to end |

## How to run (step by step)

### 1. Install

```bash
cd content-repurposer
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. (Optional) Smoke-test with no API keys

Mocks every external call — proves wiring, supervisor routing, and the
critique-loop cap without spending credits:

```bash
pytest -v
```

### 3. Configure API keys (needed for a real run)

```bash
cp .env.example .env
```

Fill in `.env` with four keys: LLM, Firecrawl, Serper, Pexels.

**Recommended LLM — Groq (free tier):**

1. Get a key at [console.groq.com/keys](https://console.groq.com/keys)
2. Set in `.env`:
   ```
   LLM_API_KEY=<your groq key>
   LLM_BASE_URL=https://api.groq.com/openai/v1
   LLM_MODEL=openai/gpt-oss-120b
   LLM_SUMMARIZER_MODEL=openai/gpt-oss-120b
   ```
3. One pipeline run makes ~6–10 LLM calls; occasional 429s are handled by
   the retry policy in `src/utils/retry.py`.

OpenRouter or OpenAI work the same way — swap `LLM_BASE_URL` / `LLM_MODEL`
(see comments in `.env.example`).

Also set:

| Variable | Where to get it |
|---|---|
| `FIRECRAWL_API_KEY` | [firecrawl.dev](https://firecrawl.dev) |
| `SERPER_API_KEY` | [serper.dev](https://serper.dev) (2,500 free searches/month) |
| `PEXELS_API_KEY` | [pexels.com/api](https://www.pexels.com/api/) |

### 4. Run it three ways

Activate the venv first (`source .venv/bin/activate`) for each option below.

---

#### A. CLI (no server)

Fastest way to sanity-check a real run. Results print to the terminal and
are written under `outputs/{run_id}/`.

```bash
# With a source URL
python -m src.main "https://example.com/some-article" "your target keyword"

# With no args — uses a built-in sample text + default keyword
python -m src.main
```

---

#### B. FastAPI (API only)

Start the server:

```bash
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Kick off a job, then poll until `status` is `done` or `failed`:

```bash
# Start generation
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "source_url": "https://example.com/some-article",
    "target_keyword": "ai engineering freelance",
    "brand_voice": "clear, confident, and helpful"
  }'
# -> {"run_id": "...", "status": "running"}

# Poll progress / result
curl http://127.0.0.1:8000/status/<run_id>

# List / reload saved runs (survive a server restart)
curl http://127.0.0.1:8000/runs
curl http://127.0.0.1:8000/runs/<run_id>
```

You can paste text instead of a URL:

```bash
curl -X POST http://127.0.0.1:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "raw_text": "Your article or notes here…",
    "target_keyword": "ai content automation"
  }'
```

---

#### C. Demo UI (same server)

The portfolio UI is served by the same FastAPI app.

```bash
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

1. Paste a **source URL** *or* raw text  
2. Set the **target keyword** (and optional brand voice)  
3. Click **Generate package**  
4. Watch live agent steps, then review article / social / critique tabs and cost  

Typical run: about 30s–2min depending on rate limits and source size.

## Output

Every completed run writes to `outputs/{run_id}/`:

```
outputs/{run_id}/
├── article.md              # publish-ready: YAML frontmatter + embedded image + full body
├── image.<ext>              # downloaded locally (jpg/jpeg/png), not just a remote URL that can rot
├── social/
│   ├── twitter_thread.md
│   ├── linkedin_post.md
│   └── email_snippet.md
└── package.json              # the full raw structured result (for debugging/reprocessing)
```

`article.md` uses YAML frontmatter (`title`, `description`, `date`, `image`, `image_alt`)
since that's what most static-site generators and headless CMSs expect — Hugo, Jekyll,
Next.js MDX, and Ghost imports all read this format natively.

Retrieve saved runs via the API too:
```bash
curl localhost:8000/runs                # list saved run_ids
curl localhost:8000/runs/<run_id>       # full result + output_folder + list of files
```

Note the graph itself never touches disk — persistence and markdown export both live in
`src/main.py` / `src/utils/`, called *after* `compiled_graph.invoke()` returns. That's why
`tests/test_graph_smoke.py` can invoke the graph directly, twice, with zero filesystem
side effects.

## Production details worth calling out

- **Cost tracking**: every LLM call's token usage is recorded per node;
  the final package includes a full cost report (`$ per run`, tokens by
  node) — clients can see exactly what a generation costs to run.
- **Caching**: Firecrawl/Serper/Pexels responses are cached by input hash,
  so repeated dev/demo runs don't burn free-tier API credits.
- **Retries**: every external call (LLM, Firecrawl, Serper, Pexels) is
  wrapped in the same exponential-backoff-with-jitter policy, with a capped
  attempt count that fails loudly (`UpstreamFailure`) instead of hanging.
- **Graceful degradation**: a failed image search doesn't fail the run — the
  pipeline finishes without an image rather than losing the whole article
  over a non-essential step.
- **Async by design**: generation takes 30s–2min, so it never blocks an HTTP
  request; the API returns a `run_id` immediately and the client polls.

## Next steps / known limitations

- Run store in `main.py` is in-memory — fine for a demo, but swap for Redis
  + Celery/RQ before running multiple workers in production.
- No auth on the API yet — add an API key check before deploying publicly.
- Demo UI lives in `static/` and is served at `/` by FastAPI — fine for client demos; swap for a separate frontend deploy if you need auth/CDN hosting.
