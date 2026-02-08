# MCP Server Specification

**Version:** 1.0  
**Status:** Draft (pre-implementation)  
**Depends on:** genimg public API; Model Context Protocol (MCP) Streamable HTTP

---

## Table of Contents

1. [Scope and Goals](#1-scope-and-goals)
2. [Requirements Summary](#2-requirements-summary)
3. [Environment Variables](#3-environment-variables)
4. [MCP Tool: generate_image](#4-mcp-tool-generate_image)
5. [Architecture](#5-architecture)
6. [Module Layout](#6-module-layout)
7. [Genimg Core: CLI vs Ollama HTTP](#7-genimg-core-cli-vs-ollama-http)
8. [Implementation Notes and Gotchas](#8-implementation-notes-and-gotchas)
9. [Files to Add or Change](#9-files-to-add-or-change)
10. [Out of Scope](#10-out-of-scope)
11. [Open Points](#11-open-points)

---

## 1. Scope and Goals

### 1.1 Purpose

Provide an MCP (Model Context Protocol) server for genimg that exposes image generation as a single tool over Streamable HTTP. Clients (e.g. Cursor IDE) connect via URL. Generated images are temporarily served from the same HTTP process and referenced by URL in the tool response.

### 1.2 Scope

- **Single tool**: Only `generate_image`. No separate tools for optimize_prompt, validate_prompt, or list_ollama_models.
- **Transport**: Streamable HTTP only. No stdio transport.
- **Monolithic server**: One process, one port. MCP endpoint at `/mcp`; image downloads at `/serve/<token>.<ext>` on the same host and port.
- **Default install**: MCP SDK is a normal dependency of genimg. `genimg mcp` is always available after `pip install genimg`.
- **Public API boundary**: The MCP server depends only on the genimg library. It imports only from `genimg` (e.g. `generate_image`, `optimize_prompt`, `process_reference_image`, `Config`, exceptions). It does not import from `genimg.core.*` or `genimg.utils.*` and does not implement or depend on Ollama internals.

### 1.3 Goals

- Enable IDE and other MCP clients to generate images via the genimg API without base64 in responses (images are fetched by URL).
- Keep the MCP server thin: configuration and optimization backend (CLI vs Ollama HTTP) are genimg library concerns.
- Support Docker and remote deployment with a single published port and optional base URL for `image_url`.

---

## 2. Requirements Summary

| ID    | Requirement |
| ----- | ----------- |
| MCP-1 | The server SHALL expose exactly one MCP tool: `generate_image`. |
| MCP-2 | The tool response SHALL include a `message` field whose string SHALL include the image URL (e.g. "Image available at: " followed by the URL), and an `image_url` field. It SHALL NOT return image data as base64. |
| MCP-3 | Generated images SHALL be served at `GET /serve/<token>.<ext>` on the same host and port as the MCP endpoint. |
| MCP-4 | Image retention TTL SHALL be configurable via environment; default SHALL be 7 days. |
| MCP-5 | The server SHALL use only the genimg public API and `Config.from_env()`. No Ollama-specific logic in the MCP package. |
| MCP-6 | The server SHALL start without requiring `OPENROUTER_API_KEY`; validation SHALL occur on first tool use (lazy). |
| MCP-7 | MCP SHALL be mounted at path `/mcp`. Client connection URL SHALL be `http://<host>:<port>/mcp` (or equivalent with configured base URL). |
| MCP-8 | Logging SHALL go to stderr so the JSON-RPC stream is not corrupted. |

---

## 3. Environment Variables

Variables read by the MCP server or by genimg when used by the MCP server:

| Variable | Read by | Purpose | Default |
| -------- | ------- | ------- | ------- |
| `GENIMG_MCP_IMAGE_TTL_DAYS` | MCP server | Days to keep generated images in the token store. | `7` |
| `GENIMG_MCP_BASE_URL` | MCP server | Base URL for `image_url` when behind a proxy or in Docker. | Derived from host and port |
| `GENIMG_OLLAMA_BASE_URL` or `OLLAMA_BASE_URL` | genimg Config | Ollama service URL for prompt optimization when not local. | None (genimg uses local `ollama` CLI) |
| `OPENROUTER_API_KEY` | genimg Config | Required for image generation (validated on first generate). | — |
| `GENIMG_DEFAULT_MODEL`, etc. | genimg Config | As in genimg today. | — |

---

## 4. MCP Tool: generate_image

### 4.1 Description

Generate an image from a text prompt using the genimg library. Optionally optimize the prompt (via genimg) and optionally use a reference image. The result includes a URL from which the client can download the image.

### 4.2 Parameters

| Parameter | Type | Required | Description |
| --------- | ---- | -------- | ----------- |
| `prompt` | string | Yes | Text prompt for the image. |
| `model` | string | No | Model ID; default from genimg config. |
| `optimize` | boolean | No | If true, run prompt optimization before generation (genimg). |
| `reference_image_path` | string | No | File path on the server. |
| `reference_image_url` | string | No | HTTP/HTTPS URL; server fetches with timeout and size limit. |
| `reference_image_b64` | string | No | Base64 or data URL. Precedence when multiple provided: path > url > b64. |
| `output_path` | string | No | Optional local path to also write the file. |

### 4.3 Return Value (JSON)

The tool SHALL return a single JSON object (as MCP text content) with at least:

| Field | Type | Description |
| ----- | ---- | ----------- |
| `message` | string | Human-readable text that SHALL include the image URL in the string (e.g. "Image available at: http://host:8000/serve/abc.png"). REQUIRED. |
| `image_url` | string | URL from which the client can GET the image. Same host/port as MCP. |
| `output_path` | string | Local path if `output_path` was provided. |
| `format` | string | Image format (e.g. png, jpeg). |
| `model_used` | string | Model that generated the image. |
| `generation_time_seconds` | number | Time taken for generation. |
| `optimized_prompt` | string | Present if `optimize` was true. |

Base64 image data SHALL NOT be included in the response.

### 4.4 Reference Image from URL

When `reference_image_url` is provided, the tool handler SHALL:

1. Fetch the URL (HTTP/HTTPS only) with a timeout and maximum content size.
2. Infer format from Content-Type where possible.
3. Call genimg `process_reference_image(source=bytes, format_hint=...)` and pass the result into `generate_image`.

This behavior is implemented in the MCP tool layer; no change to genimg core is required.

### 4.5 Errors

On genimg exceptions (`GenimgError` and subclasses), the tool SHALL return a structured error in the tool result (e.g. `{"error": "ConfigurationError", "message": "..."}`) or the MCP SDK’s recommended form so the client can display it.

---

## 5. Architecture

### 5.1 Process Model

- One process. Started via CLI: `genimg mcp [--host] [--port] [--base-url]`.
- One HTTP server (e.g. uvicorn) serving a single Starlette application.

### 5.2 Application Structure

- **Root app**: Starlette.
  - Route for `GET /serve/<token>.<ext>`: serves files from an in-process token store (token → (path, expiry)). Path and extension SHALL be validated (safe token charset; allow only specific image extensions) to prevent path traversal.
  - Mount at `"/mcp"`: the MCP Streamable HTTP app (e.g. `mcp.streamable_http_app()`).
- **Token store**: In-memory. On successful generation, save image to a temp directory, register token with expiry = now + `GENIMG_MCP_IMAGE_TTL_DAYS` days. Return `image_url = base_url + "/serve/" + token + "." + ext`. Clean up on expiry and on shutdown.

### 5.3 Base URL

`image_url` SHALL use a base URL from (in order of precedence): `--base-url` CLI option, `GENIMG_MCP_BASE_URL` env, or `http://<host>:<port>` from server bind address and port.

### 5.4 Client Configuration (Cursor)

Clients SHALL connect to the MCP server at `http://<host>:<port>/mcp` (e.g. `http://localhost:8000/mcp`). Streamable HTTP uses path `/mcp`; SSE is a different transport.

---

## 6. Module Layout

- **Package**: `src/genimg/mcp/`
  - `__init__.py`: Re-export `run_server` and optionally the app for testing.
  - `server.py`: Construct FastMCP (or SDK equivalent); register the `generate_image` tool; build Starlette app with `/serve` route and `/mcp` mount; implement token store and TTL; provide `run_server(host, port, base_url)` that runs the app (e.g. via uvicorn).
- **CLI**: Subcommand `mcp` in `src/genimg/cli/commands.py` with options `--host`, `--port`, `--base-url`, invoking `genimg.mcp.run_server(...)`.
- No separate file server process or `file_server.py` module.

---

## 7. Genimg Core: CLI vs Ollama HTTP

The MCP server does not implement Ollama logic. Support for “local Ollama CLI” vs “remote Ollama HTTP” is a **genimg library** concern.

### 7.1 Current State

- genimg optimization uses only the **local `ollama` CLI** (subprocess `ollama run`, `ollama list`) in `genimg.core.prompt`.
- Config has no `ollama_base_url`. Optimization therefore works only when the `ollama` binary is available on the same host.

### 7.2 Required Core Changes (for Remote Ollama)

To support “MCP in Docker with Ollama as a separate service” (or any consumer using a remote Ollama), the genimg **core** SHALL:

1. **Config** (`src/genimg/core/config.py`): Add `ollama_base_url: str | None`, populated from env (e.g. `GENIMG_OLLAMA_BASE_URL` or `OLLAMA_BASE_URL`) in `from_env()`. Default `None`.
2. **Implementation** (`src/genimg/core/prompt.py`):
   - When `config.ollama_base_url` is **set**: use the **Ollama HTTP API** (e.g. POST `{base_url}/api/generate` with `stream: false`) for optimization and, if needed, list models (e.g. GET `{base_url}/api/tags`). Reuse existing prompt/strip/thinking logic; only the transport changes.
   - When `config.ollama_base_url` is **None**: retain **current behavior** (subprocess `ollama run` / `ollama list`).

### 7.3 When Each Path Is Used

| Scenario | `ollama_base_url` | Behavior |
| -------- | ----------------- | -------- |
| Local CLI / UI, Ollama on same machine | Unset (default) | Subprocess CLI |
| MCP or other consumer in Docker, Ollama as separate service | Set (e.g. `http://ollama:11434`) | HTTP API |

### 7.4 Optional for MCP v1

The MCP server MAY be shipped without the above core changes. In that case, optimization when running in Docker will only work if Ollama is installed in the same container. Implementing §7.2 enables “MCP in Docker + remote Ollama.”

---

## 8. Implementation Notes and Gotchas

### 8.1 MCP Streamable HTTP and Mounting

- When mounting the MCP app under a root Starlette (e.g. at `/mcp`), the **mounted app’s lifespan is not run**—only the root app’s lifespan runs. The Streamable HTTP session manager **requires** its `run()` context (task group). The root Starlette MUST use a lifespan that runs the session manager (e.g. `async with mcp.session_manager.run(): yield`). Otherwise: `RuntimeError: Task group is not initialized. Make sure to use run().`
- Use **Starlette** as the root app when adding custom routes like `/serve`. FastAPI mount can cause redirects (e.g. POST `/mcp` → 307 → 404).
- Mount the MCP app at `"/mcp"` and register the `/serve` route on the root app. Order routes so the more specific `/serve` is matched first.

### 8.2 SDK Usage

- Call `streamable_http_app()` to obtain the Starlette app; do not pass the method un-called to `Mount`.
- If the MCP app does not provide a lifespan, use the session manager’s `run()` as the root app lifespan (e.g. `lifespan = lambda app: mcp.session_manager.run()`).
- Tool handlers SHALL return content as expected by the SDK (e.g. `TextContent(type="text", text=json.dumps({...}))`).

### 8.3 Token Store and /serve

- Validate token (e.g. alphanumeric and hyphen only, fixed length) and allow only safe image extensions (e.g. png, jpeg, webp) to prevent path traversal.
- Use a dedicated temp subdirectory; close files before deletion on Windows.

### 8.4 Cursor and DNS Rebinding

- Some MCP SDK configurations enforce DNS rebinding protection. For local or Docker use, disabling via env (e.g. `MCP_DISABLE_DNS_REBINDING_PROTECTION=true`) may be necessary if clients cannot connect.

### 8.5 Production

- The server is unauthenticated in v1. Documentation SHALL recommend network-level protection or reverse proxy with auth if exposed.
- An optional GET `/health` route MAY be added for readiness checks.

---

## 9. Files to Add or Change

| Action | File | Description |
| ------ | ---- | ----------- |
| Add | `src/genimg/mcp/__init__.py` | Re-export `run_server`, optionally app. |
| Add | `src/genimg/mcp/server.py` | FastMCP, generate_image tool, token store, Starlette app with /mcp and /serve, `run_server`. |
| Edit | `src/genimg/cli/commands.py` | Add `mcp` subcommand (--host, --port, --base-url). |
| Edit | `pyproject.toml` | Add MCP SDK to default dependencies. |
| Edit | `src/genimg/core/config.py` | Add `ollama_base_url` from env (§7). |
| Edit | `src/genimg/core/prompt.py` | When `ollama_base_url` set use Ollama HTTP API; when unset keep subprocess CLI (§7). |
| Add | `tests/unit/test_mcp_server.py` | Tool behavior, error mapping, /serve and TTL. |
| Edit | `tests/unit/test_cli.py` | Test `genimg mcp --help`. |
| Edit | `README.md` | MCP section: single tool, env vars, Cursor URL example. |
| Edit | `docs/DECISIONS.md` | ADR for MCP (default install, monolithic, single tool, 7-day TTL, Ollama URL in core). |

---

## 10. Out of Scope

- MCP resources or prompts.
- Authentication or authorization on the HTTP transport in v1.
- Optional: GET `/health` and detailed deployment guidance (may be added later).

---

## 11. Open Points

1. **PyPI package name** for the MCP SDK (e.g. `mcp`, `mcp[cli]`) for default dependencies. ANSWER: `mcp`
2. **Ollama (genimg core)**: Final env name (`GENIMG_OLLAMA_BASE_URL` vs `OLLAMA_BASE_URL`) and HTTP API details (e.g. `/api/generate`, `stream: false`) are decided and implemented in genimg core only; the MCP server is unchanged. ANSWER: `OLLAMA_BASE_URL`
