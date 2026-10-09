# Week 4: The public API and the web page

> **Goal:** play the whole game in a browser. The page talks to a FastAPI service, the API talks
> to the seller over A2A, and the API is ready to face the public internet: limits, budget,
> tokens, input hygiene, strict CSP.

**Definition of Done** ([05-delivery-plan.md](../05-delivery-plan.md#week-4-api-and-web-ui-9-h-checkpoint-a-playable-locally)):

| Done when… | Status |
|------------|--------|
| A game completes at all 3 levels locally | ✅ L1 floor claim in the browser, L2 and L3 deals through `docker compose` (§7) |
| Tests cover rate limit, single-flight and token checks | ✅ `services/api/tests/` (real Postgres, fake seller) |
| `grep innerHTML` finds nothing in the UI code | ✅ and a test keeps it that way |
| Tests green | ✅ 165 tests (109 at the end of week 3) |

---

## 1. One message, end to end

```
browser ──POST /api/games/{id}/messages + X-Game-Token──▶ api (FastAPI, :8080)
   api: token hash ✓ · game open ✓ · per-IP quota ✓ · budget ✓ · clean text ✓
   api: advisory lock (one message in flight per game, across instances)
   api ──A2A message/send, contextId = game id──▶ seller (ADK, :8200)
          seller ──MCP tools/call──▶ mcp (:8100) ──▶ policy / Postgres
   api ◀── SellerTurn {message, intent, price_usd}
   api: re-read the game (the seller wrote the turn) · floor only if the game is over
browser ◀── {seller_message, offer_on_table_usd, status, deal, floor_usd}
```

The API **never calls an LLM and never decides a price**. It is a gatekeeper and a translator.
The greeting when you start a game is a template, so creating a game costs nothing.

---

## 2. FastAPI for a C# developer

**Files:** [`main.py`](../../services/api/src/haggle_api/main.py), [`routes.py`](../../services/api/src/haggle_api/routes.py), [`games.py`](../../services/api/src/haggle_api/games.py), [`schemas.py`](../../services/api/src/haggle_api/schemas.py), [`errors.py`](../../services/api/src/haggle_api/errors.py)

| FastAPI | ASP.NET Core equivalent |
|---------|-------------------------|
| `create_app()` factory | `WebApplication.CreateBuilder()` + `Build()` |
| `lifespan` (async context manager) | `IHostedService` start/stop, or `app.Lifetime` events |
| `app.state.games` | a singleton registered in the DI container |
| `Depends(get_service)` / `Annotated[GameService, Depends(...)]` | constructor injection into a controller |
| `APIRouter` | a controller class |
| Pydantic model as parameter / return type | a record with DataAnnotations, model binding, `[ApiController]` validation |
| `exception_handler(ApiError)` | exception-handling middleware / `IProblemDetailsService` |

Three choices worth defending:

- **App factory, no module-level `app`.** Tests build a fresh app with a fake seller:
  `create_app(settings, seller=FakeSeller(...))`. Uvicorn calls the factory with `--factory`.
- **Thin routes, fat service.** Routes only translate HTTP ↔ `GameService` calls. The rules live
  in `GameService`, which you could call from a CLI or a test without HTTP.
- **One error format: RFC 9457 Problem Details** (`application/problem+json` with `title`,
  `status`, `detail`). The browser has one code path for every error. Validation errors from
  Pydantic are converted too, so even a 422 has the same shape.

**Schemas are a security boundary.** `NewGameIn` uses `extra="forbid"`: sending
`{"floor_usd": 1}` is a 422, not silently ignored. No *response* model has a floor that can be
filled while the game is open.

---

## 3. Facing the internet: the protections

**Files:** [`security.py`](../../services/api/src/haggle_api/security.py), [`games.py`](../../services/api/src/haggle_api/games.py), [`settings.py`](../../services/api/src/haggle_api/settings.py)

| Threat | Protection | Detail |
|--------|------------|--------|
| Someone plays your game | **Game token**: 256 random bits, returned once, only its SHA-256 is stored | Compared with `hmac.compare_digest` (constant time) |
| Rate-limit bypass with a fake IP | **Right-most X-Forwarded-For** | Anyone can pre-fill the header. Each trusted proxy *appends*, so only the last `trusted_proxy_hops` entries are real. Taking the left-most one (a very common bug) lets the attacker pick their IP |
| Storing personal data | **Daily-rotating salted IP hash** | `HMAC(HMAC(secret, day), ip)`: enough to count games per day, useless to identify anyone tomorrow (GDPR) |
| Cost attack | 5 games/IP/day · 60 games/hour global · 30 messages/IP/hour · **daily $ budget** · **kill switch** (`HAGGLE_API_DEMO_ENABLED=false`) | Counters are `COUNT(*)` queries in Postgres: no Redis to run, works across instances |
| Double send, two tabs | **Single flight**: `pg_try_advisory_lock(game)` | The lock lives in the database, so it holds across several Cloud Run containers. An in-process `asyncio.Lock` would not |
| Abandoned games | Idle expiry (30 min) | Written in **its own transaction**: the caller raises 409 right after, which would roll back an expiry written in the same transaction (a bug the tests caught) |
| Smuggled instructions | `clean_message`: NFKC normalization, reject zero-width/bidi/control characters, 500 chars | Full-width `３０，０００` becomes `30,000`, so filters see what the model will see |
| Model output as HTML (OWASP LLM05) | `textContent` only + **strict CSP** (`script-src 'self'`, no inline) | Two independent layers: even if HTML got in, an injected `<script>` would not run |

> **Why the limits live in the API and not the seller.** The seller already has a budget check
> (week 3). Defense in depth: the API refuses *before* paying for a network hop and an LLM call.

---

## 4. The page: Jinja2 + vanilla JS

**Files:** [`templates/`](../../services/api/src/haggle_api/templates/), [`static/app.js`](../../services/api/src/haggle_api/static/app.js), [`static/style.css`](../../services/api/src/haggle_api/static/style.css)

No build step, no framework ([ADR-0009](../adr/0009-server-rendered-ui.md)). The server renders the car list; JavaScript
handles the game. Things to notice in `app.js`:

- **Every model text goes through `textContent`.** A test greps the file for `innerHTML`,
  `outerHTML`, `insertAdjacentHTML`, `document.write` and `eval(`. I checked it in the browser:
  sending `<img src=x onerror=alert(1)>` shows the tag as text, and `#chat img` is empty.
- **The token lives in `sessionStorage`**: it survives a reload of that tab (the game resumes
  from `GET /api/games/{id}`), but it isn't shared with other tabs or kept after the tab closes.
  No cookies, so no CSRF and no cookie banner.
- **Storage access is wrapped in `try/catch`**: private windows can throw; the game must still work.
- **A 504 is not the end.** See §6.

---

## 5. Testing the API

**Files:** [`tests/test_games_api.py`](../../services/api/tests/test_games_api.py), [`tests/test_security.py`](../../services/api/tests/test_security.py)

- **Real Postgres, real HTTP stack, fake seller.** `FakeSeller` does to the database what the
  real seller does (reserve the turn, write the turn pair, close the deal), so the API sees a
  realistic game. The plan said "mock the seller with respx" (HTTP-level). Faking the
  `SellerClient` interface instead is simpler and tests the same API logic. The A2A wire itself
  was exercised by the live games in §7.
- **One client IP per test** through `X-Forwarded-For`, so the 5-games-per-day limit of one test
  doesn't throttle the next. That also tests the XFF logic for free.
- **Single flight tested like production:** the test takes the advisory lock on *another*
  connection (a second container) and checks that the API answers 409 without calling the seller.
- **`TestClient(app).__enter__()`** runs the lifespan; without it `app.state.games` doesn't exist.

---

## 6. What only showed up in Docker and against the real Gemini

All unit tests were green. Then I ran the four services in `docker compose` and played real
games. **Six problems** appeared, and none of them could show up in the local tests:

| # | Symptom | Cause | Fix |
|---|---------|-------|-----|
| 1 | API container would not start | The Dockerfile still ran `haggle_api.main:app`, which no longer exists | `uvicorn --factory haggle_api.main:create_app` |
| 2 | Seller container: `cannot import McpToolset` | The seller used the `mcp` package but never declared it. Locally the **workspace venv** had it (installed for the MCP service). The image installs only the seller's own dependencies | `mcp>=2.3` in the seller's `pyproject.toml` |
| 3 | The agent card advertised `http://0.0.0.0:8200` | `to_a2a(host=settings.host)` used the *bind* address; `public_url` existed but was not wired. A2A clients call back the URL in the card | Build the card from `HAGGLE_SELLER_PUBLIC_URL` |
| 4 | MCP answered **421 Misdirected Request** | The MCP SDK's DNS-rebinding protection only accepts `localhost` Host headers by default. In compose the host is `mcp:8100` | `HAGGLE_MCP_ALLOWED_HOSTS` (protection kept on, list explicit) + a test that `evil.example` gets 421 |
| 5 | 502 in the middle of a game | Gemini answered `503 UNAVAILABLE, high demand`. The **turn had been reserved**, so the player lost a turn to our outage | Retry 429/5xx with backoff (`HttpRetryOptions`, 3 attempts); `on_model_error_callback` gives the turn back (`release_turn`, conditional so it can't undo a completed turn) |
| 6 | 504, but the reply was in the transcript | Gemini took 16–48 s per turn that day. The API gave up at 60 s; the seller finished anyway | Timeout 90 s, and on 504 the page polls `GET /api/games/{id}` and shows the late reply |

Two lessons:

- **A shared virtualenv hides missing dependencies.** Each service image installs only its own
  `--package`. Building the images is a test in itself; CI should do it (Week 7).
- **The A2A client retries only `ConnectError`, not 5xx.** The plan said "retry on 5xx". But a
  5xx can arrive *after* the seller reserved a turn and called the model: sending the message
  again would play it twice. A connection error means the request never arrived, so it's safe.
  Retries belong where the operation is idempotent: here, inside the seller, around the model call.

Two good signs from the same session: the 5-games limit fired on me (429) after a few manual
games, and when the seller was down the API returned a clean 502 Problem Details.

---

## 7. Results: one game per level

Car: 1969 Camaro Z/28, list $94,900 (L2, L3). Scripted buyer: $80k, then +$3k per turn, then
accept the dealer's price.

| | L1 Naive (browser) | L2 Hardened | L3 Blind |
|---|---|---|---|
| Counters | $99,500 (Challenger) | 92.5k → 91.5k → 89.9k | 94.8k → 94.3k → 93.4k |
| Outcome | floor claim $90,000, off by 11.7% | **deal $89,900** | **deal $93,400** |
| Secret floor | $80,567 | $69,741 | $70,164 |
| Discount captured | — | **19.9%** | **6.1%** |

The same pattern as week 3, now through the web stack: **the model concedes faster than the
code.** At L3 the Boulware policy gives up only $1,500 in three turns.

---

## 8. Your turn

1. `docker compose up --build` and play at <http://127.0.0.1:8080>. Reload mid-game: it resumes.
2. Open DevTools → Network: find the `X-Game-Token` header and the `content-security-policy`
   response header. Try `document.body.innerHTML = '<img src=x onerror=alert(1)>'` in the console
   and read the CSP error.
3. Run `curl -H 'X-Forwarded-For: 1.2.3.4' …` against the local API with
   `HAGGLE_API_TRUSTED_PROXY_HOPS=0` and then `=1`. Which IP gets counted each time?
4. **Interview drill:** why is an advisory lock in Postgres the right single-flight tool on Cloud
   Run, and why does the expiry need its own transaction?

## 9. Glossary

| Term | Meaning |
|------|---------|
| App factory | A function that builds the app, so each test gets a fresh one with its own dependencies |
| Problem Details (RFC 9457) | Standard JSON error body: `type`, `title`, `status`, `detail` |
| Advisory lock | A named lock in Postgres that the application takes and releases explicitly |
| Single flight | At most one in-flight operation per key (here, per game) |
| CSP | Content-Security-Policy header: which scripts, styles and connections a page may use |
| DNS rebinding | A web page makes the browser call a server on your network by re-pointing its domain; checking the Host header stops it |
| Idempotent | Doing it twice has the same effect as once, so it is safe to retry |
