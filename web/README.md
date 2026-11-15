# RegLens web UI

Next.js (App Router) + Tailwind + shadcn/ui front end for the RegLens API
(`src/reglens/api/app.py`). Two pages:

- **Ask** (`/`): question form, live research progress streamed from the API (retrieval,
  routing, each agent tool call), the answer with citation badges, sources with their legal
  level, the citation check and the research steps.
- **Policy gap analysis** (`/gap`): the saved coverage matrix with filters and CSV / Excel export.

## Run

```bash
# from the repository root: database and API
docker compose up -d
uv run uvicorn reglens.api.app:app --port 8000

# in web/
npm install
npm run dev            # http://localhost:3000
```

The browser calls the API directly at `NEXT_PUBLIC_REGLENS_API` (default
`http://localhost:8000`; CORS allows any `localhost` / `127.0.0.1` port, so `npm run dev -- -p 3200`
works when 3000 is taken or reserved). Streamed agent answers can take a minute
or more, longer than a dev-server proxy should be trusted to hold open.

**API keys:** with "Your API key", the key is kept in the page's memory only (gone on reload),
sent with each request to the local API and from there only to the Anthropic API.

Checks: `npx tsc --noEmit` and `npm run lint`.
