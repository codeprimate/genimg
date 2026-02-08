# MCP Server Implementation Tasks

**Source:** [MCP_SERVER_SPEC.md](./MCP_SERVER_SPEC.md)  
**Purpose:** Track implementation tasks and completion for the genimg MCP server.

---

## Task key

| Symbol | Meaning |
|--------|--------|
| ☐ | Not started |
| ◐ | In progress |
| ☑ | Done |

---

## Phase 1: Dependencies and core (optional for v1)

! DECIDED: IMPLEMENT !

Optional for MCP v1: ship MCP without these; optimization in Docker then requires Ollama in same container.

- [ ] **1.1** Edit `pyproject.toml`: add MCP SDK (`mcp`) to default dependencies.
- [ ] **1.2** Edit `src/genimg/core/config.py`: add `ollama_base_url: str | None`, populated from `OLLAMA_BASE_URL` (or `GENIMG_OLLAMA_BASE_URL`) in `from_env()`; default `None`. (§7.2)
- [ ] **1.3** Edit `src/genimg/core/prompt.py`: when `config.ollama_base_url` is set, use Ollama HTTP API (e.g. POST `{base_url}/api/generate`, GET `{base_url}/api/tags`); when unset, keep current subprocess CLI behavior. (§7.2)

---

## Phase 2: MCP package and server

- [ ] **2.1** Add `src/genimg/mcp/__init__.py`: re-export `run_server`, optionally the app for testing.
- [ ] **2.2** Add `src/genimg/mcp/server.py`:
  - [ ] **2.2a** Construct MCP app (e.g. FastMCP / `streamable_http_app()`).
  - [ ] **2.2b** Register `generate_image` tool with spec params (§4.2); return JSON with `message`, `image_url`, etc.; no base64 (§4.3, MCP-2).
  - [ ] **2.2c** Implement reference image from URL: fetch with timeout/size limit, infer format, call `process_reference_image` + `generate_image` (§4.4).
  - [ ] **2.2d** Map genimg exceptions to structured tool error (e.g. `{"error": "ConfigurationError", "message": "..."}`) (§4.5).
  - [ ] **2.2e** In-memory token store: on success save image to temp dir, register token with expiry = now + `GENIMG_MCP_IMAGE_TTL_DAYS` (default 7); validate token (safe charset) and image extension (png, jpeg, webp) (§5.2, MCP-3, MCP-4, §8.3).
  - [ ] **2.2f** Root Starlette app: route `GET /serve/<token>.<ext>` serving from token store; mount MCP at `"/mcp"`; root lifespan runs MCP session manager `run()` (§5.2, §8.1, §8.2).
  - [ ] **2.2g** Base URL: `--base-url` > `GENIMG_MCP_BASE_URL` > `http://<host>:<port>` (§5.3).
  - [ ] **2.2h** `run_server(host, port, base_url)` running app via uvicorn; logging to stderr (MCP-8).
  - [ ] **2.2i** Lazy validation: no `OPENROUTER_API_KEY` required at startup; validate on first tool use (MCP-6).

---

## Phase 3: CLI

- [ ] **3.1** Edit `src/genimg/cli/commands.py`: add `mcp` subcommand with options `--host`, `--port`, `--base-url`, invoking `genimg.mcp.run_server(...)` (§6).

---

## Phase 4: Tests

- [ ] **4.1** Add `tests/unit/test_mcp_server.py`: tool behavior, error mapping, `/serve` and TTL (and token/extension validation).
- [ ] **4.2** Edit `tests/unit/test_cli.py`: test `genimg mcp --help`.

---

## Phase 5: Documentation

- [ ] **5.1** Edit `README.md`: MCP section (single tool, env vars, Cursor URL example e.g. `http://localhost:8000/mcp`).
- [ ] **5.2** Edit `docs/DECISIONS.md`: ADR for MCP (default install, monolithic, single tool, 7-day TTL, Ollama URL in core).

---

## Requirements checklist (from §2)

| ID    | Requirement | Task(s) |
| ----- | ----------- | ------- |
| MCP-1 | Exactly one tool: `generate_image` | 2.2a, 2.2b |
| MCP-2 | Response: `message` (includes URL), `image_url`; no base64 | 2.2b |
| MCP-3 | Images at `GET /serve/<token>.<ext>` | 2.2e, 2.2f |
| MCP-4 | Image TTL configurable (default 7 days) | 2.2e |
| MCP-5 | Use only genimg public API + `Config.from_env()` | 2.2b, 2.2c |
| MCP-6 | Start without OPENROUTER_API_KEY; validate on first use | 2.2i |
| MCP-7 | MCP at `/mcp`; client URL `http://<host>:<port>/mcp` | 2.2f, 3.1 |
| MCP-8 | Logging to stderr | 2.2h |

---

## Optional / later

- [ ] GET `/health` for readiness (§8.5).
- [ ] Deployment and auth guidance in docs (§8.5, §10).

---

## Completion summary

| Phase | Done | Total |
|-------|------|-------|
| 1. Dependencies and core | 0 | 3 |
| 2. MCP package and server | 0 | 10 |
| 3. CLI | 0 | 1 |
| 4. Tests | 0 | 2 |
| 5. Documentation | 0 | 2 |
| **Total** | **0** | **18** |

*Update the checkboxes and this table as tasks are completed.*
