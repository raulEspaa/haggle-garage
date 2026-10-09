# Week 2: Tracer bullet and the policy engine

> **Goal:** prove that the risky integrations (ADK ↔ MCP ↔ A2A) work *before* building on them,
> then build the part of the system that must never be wrong: the code that decides prices and
> deals.

**Definition of Done** ([05-delivery-plan.md](../05-delivery-plan.md#week-2-tracer-bullet-and-policy-engine-9-h)):

| Done when… | Status |
|------------|--------|
| Integration path proven, or fallbacks chosen and recorded | ✅ S1, S2, S3, S4, S6 done. S5 needs a real LLM (Week 3) |
| Property tests pass 1,000 examples per invariant | ✅ I1–I5, after Hypothesis found a real bug (§3) |
| `close_deal` below the floor returns `not_accepted` | ✅ at every level, with the precise reason only in the audit log |
| A real client can call both tools with a token, and gets 401 without one | ✅ end-to-end over HTTP with the official MCP client, plus `curl` against the container |
| Model sheets written | ✅ three sheets with real, sourced facts ([ADR-0011](../adr/0011-real-iconic-cars.md)) in [`db/sheets/`](../../db/sheets/) |

---

## 1. What a tracer bullet is (and why first)

In the dark, a tracer round shows you where your shots go *before* you commit. In software,
it's the thinnest end-to-end path through the real components, built to answer questions, not
to ship. Week 2's questions were the riskiest assumptions of the whole plan (S1–S6 in
[02-architecture.md §11](../02-architecture.md#11-spikes-de-risk-before-building-on-them)).
If any had failed, the design would have changed *now*, cheaply, not in Week 5.

**File:** [`spikes/w02_tracer_bullet.py`](../../spikes/w02_tracer_bullet.py) · run: `make spike`

```
a2a-sdk client ──A2A──▶ to_a2a(ADK agent) ──MCP──▶ MCPServer v2 tool "whoami"
   contextId=X            session id = X?           header X-Haggle-Game-Id = X?
                          state persisted?
```

### Trick: an LLM agent with no LLM

ADK documents that if `before_model_callback` returns an `LlmResponse`, **the model is never
called**. The spike uses that to *script* the model: the first call returns a `function_call`
to the tool, and the second returns text with the tool result. Zero tokens, fully deterministic,
runnable in CI. The same trick will drive the guard tests in Week 3.

### Results

| Question | Answer |
|----------|--------|
| S1: ADK 2.x + MCP v2 in one lockfile? | Yes, but see §2: the real conflict was elsewhere |
| S2: does A2A `contextId` become the ADK session id? | **Yes**, and a client-provided id is accepted. State persisted in Postgres across messages |
| S3: can *code* send the game id to MCP? | **Yes**: `McpToolset(header_provider=...)` gets the session. The tool saw the header |
| S4: hide tools per level? | Yes (source reading): `tool_filter` accepts a predicate with the session context |
| S6: where is the answer in A2A? | One `Task` per turn, `COMPLETED`, text in `artifacts`. a2a-sdk 1.x uses **protobuf** types |

---

## 2. Lesson: resolvers "solve" conflicts by downgrading

`uv add "google-adk[a2a]"` succeeded, but the lockfile had **ADK 1.10**, a year old. Forcing
`>=2.11` revealed why:

```
google-adk>=2.11.0 depends on opentelemetry-api>=1.39,<=1.42.1
fastapi>=0.143.0 depends on opentelemetry-api>=1.44.0
```

The conflict was not MCP, as we feared in risk R3. It was **OpenTelemetry**, a transitive
dependency of two unrelated packages. Without a lower bound on ADK, uv found a "valid" solution
by going back in time. Fix: relax FastAPI's floor (it resolves to 0.141.1).

> **Rule:** put lower bounds on the frameworks you care about. Read the lockfile diff on every
> dependency change, not just "it installed". Same idea as checking `packages.lock.json` diffs
> in .NET.

Two more surprises surfaced the same way:

- **SQLAlchemy 2.1 no longer installs `greenlet`.** The async engine fails at *runtime* without
  `sqlalchemy[asyncio]`. Week 1's `session.py` had this latent bug. Now there's a regression
  test, `test_async_engine_works`.
- **a2a-sdk 1.x** was resolvable. uv had picked 0.3.26 only because nothing asked for more.
  Requesting `>=1.2` gave the spec 1.0 implementation.

---

## 3. The policy engine: pure functions + property-based testing

**Files:** [`haggle_core/policy.py`](../../packages/core/src/haggle_core/policy.py), [`tests/test_policy.py`](../../packages/core/tests/test_policy.py)

### Why pure functions

The policy takes numbers and returns a decision. No database, no clock, no LLM. That makes it:

- trivially testable (thousands of cases per second),
- reusable by the MCP server (with the secret floor) **and** by the evals (to measure how much
  the policy itself leaks, `FEE_policy`),
- easy to reason about in an interview: *"code decides" lives in 100 lines you can read.*

### The Boulware curve

```
target(t) = F + (L − F) · (1 − (t/T)^(1/β))        β = 0.5 → concede late
```

Real output for the example policy used in the tests (L = 38,900, secret F = 27,385, margin 3.4%, 12 turns, buyer
stubbornly offering 25,000):

| turn | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|------|---|---|---|---|---|---|---|---|---|----|----|----|
| counter | 38,900 | 38,600 | 38,200 | 37,700 | 37,000 | 36,100 | 35,000 | 33,800 | 32,500 | 31,000 | 29,300 | **28,400** |

Small concessions first, big ones at the end, and never below **28,400** (= the floor + margin,
rounded *up*). The secret 27,385 never appears.

### Example-based vs property-based tests

- **Example-based** (xUnit style): "for *this* input, expect *that* output". Good for readable
  scenarios (`test_floor_is_only_reachable_on_the_last_turn`).
- **Property-based** (Hypothesis ≈ FsCheck in .NET): "for *any* input, this must hold". You
  describe valid inputs (`@st.composite def policies(...)`), state the invariant, and Hypothesis
  generates up to 1,000 cases and tries to break it.

### Hypothesis found a real bug

Invariant I2 says every counter is **strictly** above the floor. Hypothesis broke it and
**shrank** the failure to the smallest example:

```
list=10_000, floor=4_000, margin=0, step=50  →  minimum counter = 4_000 = the floor
```

With `margin = 0` and a floor that is a multiple of the price step, `ceil(F·(1+m)) == F`: the
seller would quote the secret floor verbatim. Real games use non-round floors, so it "couldn't
happen"… until someone sets a margin of 0. The fix makes the invariant hold **by construction**:
the minimum counter is at least one step above the floor. A unit test would never have tried that
combination.

### Defensive validation

`decide()` refuses a `last_counter` outside `[minimum_counter, list price]`. With a bogus value,
"accept anything ≥ the last counter" could accept below the floor. The invariant holds **whoever
the caller is**, not only when the MCP server passes the right value.

> 🔐 **Security note found by ruff (S311):** `sample_floor()` takes an `rng`. In production it
> must be `random.SystemRandom()`. Python's default Mersenne Twister can be reconstructed from
> enough outputs, and every floor is *revealed* at the end of its game. Week 4 (the api) will
> use the system CSPRNG.

---

## 4. The MCP server

**Files:** [`services/mcp/src/haggle_mcp/`](../../services/mcp/src/haggle_mcp/), contracts in [`haggle_core/contracts.py`](../../packages/core/src/haggle_core/contracts.py)

### Three layers (≈ ASP.NET controller / service / DTO)

| Layer | File | Job |
|-------|------|-----|
| Contracts | `haggle_core/contracts.py` | Pydantic models = the tools' **output JSON Schemas**. Shared with the seller (Week 3) |
| Service | `service.py` | Business rules, one DB transaction each, `SELECT … FOR UPDATE` on the game row |
| Server | `server.py` | Thin MCP tools: authorize, read the trusted header, call the service |

### How MCP v2 builds a tool

```python
@mcp.tool(annotations=ToolAnnotations(idempotent_hint=True, ...), structured_output=True)
async def evaluate_offer(
    offer_usd: Annotated[int, Field(ge=1, le=10_000_000, description="...")],
    ctx: Context,
) -> OfferDecisionOut:
    """Evaluate the buyer's latest explicit price offer..."""   # ← the LLM reads this
```

- The **docstring** becomes the tool description: it is *prompt text*.
- **Type hints + `Field`** become the input JSON Schema. `ctx` is injected, not exposed.
- **The return type** becomes the output schema, and the result is sent as `structuredContent`.
- Notice what's missing from the schema: **any game id**. The game comes from the
  `X-Haggle-Game-Id` header, set by the seller's code (ADR-0008). A test fails if anyone adds
  `game_id` to a tool.

### Rules enforced by the service (each one has a test)

| Rule | Why |
|------|-----|
| One evaluation per buyer turn. A different second offer gets `already_evaluated_this_turn` | Stops binary search for the floor inside one turn (threat T3) |
| Counters carry over between turns and never rise | Invariant I3, now through the database |
| `close_deal` below the floor is refused at **every** level | The core invariant of the project |
| L3 close needs an earlier `accept` for exactly that price | "Code decides" at Level 3 |
| Rejections say only `not_accepted` | "below floor" would itself leak the floor (T9) |
| The precise reason is stored in `negotiation_events` | Audit trail and eval metrics, never returned |
| Same `idempotency_key` → same answer | Safe retries on network errors |

### Authentication: why a plain ASGI middleware

MCP v2 has its own middleware hook, but its docstring says *"Provisional — the signature may
change in a 2.x minor release"*. Building security on a provisional API is a bad trade. An ASGI
middleware is a stable standard (≈ ASP.NET Core middleware) and independent of MCP.

- Unknown or missing token → **401** before MCP even parses the request.
- `hmac.compare_digest` compares tokens in **constant time**, so response timing can't reveal
  how much of a guessed token was right.
- **Scopes at call time:** the catalog token (future buyer agent) is refused by
  `evaluate_offer`. The 2026-07-28 spec says `tools/list` must not vary per client, so hiding
  tools isn't an option.

---

## 5. Testing patterns worth stealing

| Pattern | Where |
|---------|-------|
| Root `conftest.py` shared by every package | [`conftest.py`](../../conftest.py) |
| Fixture **factories** (`new_game(level=1, status="walked_away")`) | same file |
| **Contract snapshot**: tool schemas saved to JSON. Any change fails CI until regenerated with `UPDATE_SNAPSHOTS=1` and reviewed | [`snapshots/tools.json`](../../services/mcp/tests/snapshots/tools.json) |
| **Real HTTP end-to-end**: uvicorn on port 0 (the OS picks a free port) + the official MCP client with headers | `test_server.py` |

### The bug that cost 15 minutes: one event loop, not two

The end-to-end tests hung with `ReadTimeout`, yet the same code worked in a script. Cause:
pytest-asyncio ran **fixtures** on a session-wide event loop (our setting) but each **test** on
its own loop. The uvicorn server lived in a loop that wasn't running while the test waited.
Fix in `pyproject.toml`:

```toml
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"   # ← same loop for tests and fixtures
```

Debugging method: **reproduce outside the framework** (a 20-line script). If it works there, the
problem is the harness, not your code.

---

## 6. Try it yourself

```bash
make spike                                   # the tracer bullet, no LLM
make test-db                                 # 66 tests incl. 1,000-case properties
docker compose up -d --build mcp             # MCP server on 127.0.0.1:8100
curl -s localhost:8100/health
```

Call a tool by hand (create a game first, as in the commands of this week's session). The token
comes from an environment variable, never typed inline: inline secrets end up in your shell
history (gitleaks blocked the first version of this very example):

```bash
export MCP_TOKEN=local-seller-token   # the compose value; in real life: read from a secret store
curl -s http://127.0.0.1:8100/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H "X-Haggle-Token: $MCP_TOKEN" -H "X-Haggle-Game-Id: $GAME" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"evaluate_offer","arguments":{"offer_usd":30000}}}'
```

That's the whole protocol: JSON-RPC 2.0 over HTTP POST. No magic.

---

## 7. Your turn

1. ~~Write model sheets #1 and #2~~ Done instead by Claude at your request, with **real** cars (ADR-0011): read them in `db/sheets/` and check the facts against the sources in each front matter. Template:
   [`db/sheets/_TEMPLATE.md`](../../db/sheets/_TEMPLATE.md). Keep them consistent with
   [`db/seed/cars.yaml`](../../db/seed/cars.yaml). Week 3 embeds them for RAG.
2. **Break an invariant on purpose:** in `policy.py`, change `ceil_to_step` to round *down*
   (`math.floor`). Run `uv run pytest packages/core/tests/test_policy.py` and read Hypothesis's
   shrunk counterexample. Revert.
3. **Interview drill:** explain why `close_deal` returns the same `not_accepted` for "below
   floor" and "no matching accept", and why `lowball` is relative to the list price.

## 8. Glossary

| Term | Meaning |
|------|---------|
| Tracer bullet / spike | Throwaway end-to-end experiment that answers a risky question early |
| Property-based test | A test that states an invariant and lets a generator search for counterexamples |
| Shrinking | Hypothesis reducing a failing input to the simplest one that still fails |
| Structured output (MCP) | Tool results as typed JSON (`structuredContent`) with a declared output schema |
| Idempotency key | Client-chosen id that makes a retried request return the original result |
| `SELECT … FOR UPDATE` | Row lock until the transaction ends. It serializes concurrent changes to one game |
| Confused deputy | A trusted component tricked into misusing its authority (here: the LLM choosing the game) |
