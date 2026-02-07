# genimg Library - Technical Specification

**Version:** 1.0  
**Date:** February 7, 2026  
**Status:** Draft  
**Relationship:** Underlying library for the product specified in [SPEC.md](SPEC.md). This document specifies the programmatic API and core behavior of the library only; it does not specify CLI or UI.

---

## Table of Contents

1. [Problem Statement & Goals](#1-problem-statement--goals)
2. [Consumers & Use Cases](#2-consumers--use-cases)
3. [Core Concepts & Terminology](#3-core-concepts--terminology)
4. [Library Operations & Call Flows](#4-library-operations--call-flows)
5. [Functional Requirements](#5-functional-requirements)
6. [Data Contracts](#6-data-contracts)
7. [Integration Contracts](#7-integration-contracts)
8. [Quality Attributes](#8-quality-attributes)
9. [Constraints & Assumptions](#9-constraints--assumptions)
10. [Out of Scope](#10-out-of-scope)

---

## 1. Problem Statement & Goals

### 1.1 Problem Statement

The product described in SPEC.md (AI image generation with optional prompt optimization and reference images) must be deliverable through multiple interfaces: CLI, web UI, and direct Python usage. To avoid duplication and ensure consistent behavior, all interfaces must share a single implementation of domain logic. That shared implementation is the **underlying library**.

The library must:

- Expose a stable, testable programmatic API that covers all product capabilities.
- Encapsulate configuration, external service calls, prompt optimization, image generation, reference image handling, and caching.
- Be usable from synchronous Python code without imposing a specific concurrency model on callers.
- Fail in a predictable way with distinguishable error types so that CLI and UI can present appropriate messages and recovery options.

### 1.2 Goals

1. **Single source of truth**: All product behavior (validation, optimization, generation, reference handling) is implemented once in the library.
2. **Interface-agnostic**: The library does not depend on CLI or UI; callers pass in configuration and inputs and receive structured results or errors.
3. **Testability**: Every capability can be tested in isolation by substituting or mocking integration points.
4. **Clear contracts**: Inputs, outputs, and error conditions are well-defined so that CLI, UI, and scripts can rely on consistent behavior.
5. **Cancellation support**: Long-running operations (optimization, generation) can be cancelled by the caller when the library supports it.

### 1.3 Non-Goals for This Spec

- This spec does not define CLI commands, flags, or UI layout.
- This spec does not mandate specific package layout, class names, or design patterns.
- This spec does not specify programming language or runtime beyond “callable from Python.”

---

## 2. Consumers & Use Cases

### 2.1 Primary Consumers

| Consumer | Description | Usage pattern |
|----------|-------------|---------------|
| **CLI** | Command-line entry point | One-shot or short sequences: load config, validate, run optimization and/or generation, write output to file. |
| **Web UI** | Browser-based interface | Interactive: same operations with user-driven flow, progress/cancellation, display of results and errors. |
| **Scripts / automation** | Python scripts or notebooks | Programmatic: config set in code or env, batch or repeated calls, custom handling of results and errors. |

### 2.2 Use Cases the Library Must Support

- **Validate configuration**: Check that required credentials and settings are present and valid before any operation.
- **Validate prompt**: Check that a prompt is non-empty and acceptable for optimization or generation.
- **Optimize prompt**: Given a prompt (and optional reference context), return an optimized prompt using a configurable optimization backend; use caching when inputs match a previous request.
- **Generate image**: Given a prompt, optional reference image, and model selection, call the image generation backend and return image data plus metadata.
- **Process reference image**: Load, validate, resize (if needed), and encode a reference image for use in optimization or generation.
- **Manage session cache**: Allow callers to read, clear, or reason about the prompt optimization cache (e.g., for “clear cache” or “refresh” behavior).
- **Cancel long-running work**: Where supported, allow the caller to request cancellation of an in-flight optimization or generation.

---

## 3. Core Concepts & Terminology

Terms from SPEC.md (Prompt, Prompt Optimization, Reference Image, Image Generation Model, Generated Image) apply. The following concepts are specific to the library layer.

### 3.1 Configuration

**Configuration** is the set of settings the library needs to perform operations: API keys, base URLs, default model IDs, timeouts, image size limits, and any feature flags (e.g., optimization enabled). Configuration can be supplied by the caller (e.g., in-memory object), loaded from environment, or a combination. The library must not assume a single global process state; callers may pass configuration per call or use a shared config instance.

### 3.2 Operation

An **operation** is a single logical unit of work that may run for a long time and may be cancellable: e.g., one prompt optimization request or one image generation request. The library exposes operations as callable entry points. Outcomes are success (with result data) or failure (with a typed error).

### 3.3 Result and Error

A **result** is the successful output of an operation: e.g., an optimized prompt string, or generated image bytes plus metadata. An **error** is a failure with a defined **error type** (e.g., validation, configuration, network, API, timeout, cancellation, image processing) and a message suitable for logging or for the consumer to translate into user-facing text.

### 3.4 Session and Cache

**Session** here means the scope in which the library is used (e.g., one CLI run, one UI session). The **prompt optimization cache** is session-scoped: keyed by inputs (e.g., prompt, model, optional reference hash), storing the optimized prompt text. The library does not define session boundaries; the caller decides when a “session” starts and ends and whether to reuse or clear cache between operations.

### 3.5 Backend / Adapter

A **backend** (or **adapter**) is the concrete mechanism the library uses to talk to an external system: e.g., “OpenRouter HTTP API” for image generation, “Ollama subprocess” for prompt optimization. The library’s behavior is specified in terms of these integration points; this spec defines the **contract** the library requires from them, not the implementation.

---

## 4. Library Operations & Call Flows

### 4.1 Configuration Loading and Validation

- Caller provides or loads configuration (e.g., from environment).
- Library validates configuration (required fields, formats, ranges).
- If invalid: library raises a configuration error with clear reason.
- If valid: configuration can be used for subsequent operations.

No long-running work; no cancellation.

### 4.2 Prompt Validation

- Caller provides a prompt string.
- Library checks non-empty and any other prompt rules.
- If invalid: library raises a validation error.
- If valid: caller may proceed to optimization or generation.

Synchronous; no I/O.

### 4.3 Prompt Optimization

- **Inputs**: Prompt text, optimization model identifier, optional reference image context (e.g., hash or “has reference” flag for cache keying).
- **Optional**: Configuration (API key not needed for Ollama; model and timeout come from config or overrides).
- **Flow**:
  1. Validate prompt.
  2. Check cache for existing optimized result for same inputs; if hit, return cached optimized prompt.
  3. Call optimization backend (e.g., Ollama) with prompt (and any reference context if supported).
  4. On success: store in cache, return optimized prompt text.
  5. On failure: raise appropriate error (e.g., timeout, backend failure); no cache update.
- **Cancellation**: If the library supports cancellation, caller may request cancel; library should stop waiting on backend and raise a cancellation error.

Long-running; cancellable if supported.

### 4.4 Reference Image Processing

- **Input**: Image data (e.g., file path or bytes) and format or MIME type.
- **Flow**:
  1. Validate format (supported types: e.g., PNG, JPEG, WebP, HEIC/HEIF if supported).
  2. Decode and validate dimensions; if over size limit (e.g., 2 megapixels), resize preserving aspect ratio.
  3. Convert to a canonical form (e.g., RGB) and encode for downstream use (e.g., base64 data URL or opaque reference).
  4. Optionally compute a stable hash for cache keying.
- **Output**: Encoded reference (and optionally hash) for use in optimization and/or generation.
- On validation failure (unsupported format, corrupt data): library raises an image-processing or validation error.

May be I/O-bound (file read, decode); typically fast. No cancellation required.

### 4.5 Image Generation

- **Inputs**: Prompt (original or optimized), optional reference image (already processed), model ID, API key, timeout.
- **Flow**:
  1. Validate prompt non-empty; validate configuration (e.g., API key present).
  2. Build request per integration contract (text + optional image).
  3. Call image generation backend (e.g., OpenRouter).
  4. On success: parse response (e.g., base64 image or binary), return image bytes plus metadata (model used, prompt used, generation time, whether reference was used).
  5. On failure: raise network, API, or timeout error as appropriate.
- **Cancellation**: If supported, caller may request cancel; library should abort request and raise cancellation error.

Long-running; cancellable if supported.

### 4.6 Cache Management

- **Get cached optimized prompt**: Given inputs that form the cache key, return cached value if present, otherwise nothing.
- **Clear cache**: Remove all entries from the prompt optimization cache (e.g., so next optimization runs again).
- **Inspect cache**: Optional; allow caller to know if an entry exists or cache size (if needed for UI/CLI behavior).

Synchronous; no cancellation.

---

## 5. Functional Requirements

### 5.1 Configuration

- Library SHALL accept configuration that includes at least: OpenRouter API key (or equivalent), OpenRouter base URL, default image model, default optimization model, generation timeout, optimization timeout, max reference image pixels, and any feature flags needed for optimization.
- Library SHALL validate configuration before use; missing or invalid required values SHALL result in a configuration error.
- Library SHALL allow configuration to be provided per operation or via a shared object; behavior SHALL be defined when configuration is passed explicitly vs when a default/global is used.
- Library SHALL NOT log or expose API keys in error messages or return values.

### 5.2 Prompt Handling

- Library SHALL provide a way to validate that a prompt is non-empty and acceptable for optimization and generation.
- Library SHALL provide a way to optimize a prompt using a configurable optimization backend.
- Library SHALL support an optional cache for optimized prompts keyed by prompt, optimization model, and optional reference context; cache lookup SHALL be deterministic for the same inputs.
- Library SHALL allow cache to be cleared by the caller.
- Optimization SHALL be optional; callers may generate with the original prompt without calling optimization.

### 5.3 Reference Images

- Library SHALL accept reference image input as file path or in-memory bytes (and format/MIME type if not inferrable).
- Library SHALL validate format against a defined set (e.g., PNG, JPEG, WebP; HEIC/HEIF optional).
- Library SHALL resize images that exceed the configured pixel limit while preserving aspect ratio.
- Library SHALL output a form suitable for the image generation backend (e.g., base64 data URL) and optionally a hash for cache keying.
- Library SHALL raise a distinct error for unsupported format, corrupt data, or processing failure.

### 5.4 Image Generation

- Library SHALL accept: prompt, optional processed reference image, model ID, and configuration (API key, timeout, base URL).
- Library SHALL call the image generation backend according to the integration contract and return image bytes plus metadata (model used, prompt used, generation time, had_reference).
- Library SHALL raise distinct errors for validation failure, authentication failure, rate limit, server error, timeout, and network failure.
- Library SHALL support cancellation of in-flight generation when the implementation supports it; cancellation SHALL result in a cancellation error and no partial image.

### 5.5 Errors

- Library SHALL use a defined set of error types (e.g., validation, configuration, network, API, timeout, cancellation, image processing).
- Each error SHALL carry a message and, where useful, a field or code so callers can show targeted guidance.
- Errors SHALL be raised (or returned) in a way that allows callers to distinguish type and message without parsing strings.

### 5.6 Concurrency and Blocking

- Library operations MAY block for the duration of backend calls; callers that need non-blocking behavior SHALL run library calls in a thread or process.
- Library SHALL NOT require a specific event loop or async framework; async support MAY be added as a separate layer (e.g., async wrappers) without changing this spec.

---

## 6. Data Contracts

All structures below are logical; no specific in-memory representation is mandated.

### 6.1 Configuration (Input)

- **openrouter_api_key**: string; required for image generation.
- **openrouter_base_url**: string; base URL for API.
- **default_image_model**: string; model ID for generation when not overridden.
- **default_optimization_model**: string; model ID for optimization when not overridden.
- **generation_timeout**: positive integer; seconds.
- **optimization_timeout**: positive integer; seconds.
- **max_image_pixels**: positive integer; max pixels for reference images (e.g., 2_000_000).
- **default_image_quality**: integer; e.g., JPEG quality 1–100 for saved output (if library is responsible for encoding).

Optional or implementation-defined fields (e.g., optimization_enabled) may be part of configuration where needed.

### 6.2 Prompt Optimization

- **Input**: prompt (string), optimization_model (string), optional reference_hash or “has_reference” (for cache key).
- **Output (success)**: optimized_prompt (string).
- **Cache key**: deterministic function of (prompt, optimization_model, reference_hash or equivalent).

### 6.3 Reference Image Processing

- **Input**: image source (path or bytes), optional format/MIME.
- **Output (success)**: encoded_reference (e.g., base64 data URL or opaque handle), optional hash (string).
- **Output (failure)**: image processing or validation error.

### 6.4 Image Generation

- **Input**: prompt (string), model (string), api_key (string), timeout (integer), optional reference_encoded (e.g., base64 data URL).
- **Output (success)**:
  - image: PIL Image (primary; caller can save, convert format, or get bytes as needed).
  - image_data: binary (bytes), derived from image for backward compatibility.
  - format: string (e.g. JPEG or PNG), derived for backward compatibility.
  - generation_time: float (seconds).
  - model_used: string.
  - prompt_used: string.
  - had_reference: boolean.
- **Output (failure)**: validation, API, network, timeout, or cancellation error.

### 6.5 Error (Output)

- **type**: one of Validation, Configuration, Network, API, Timeout, Cancellation, ImageProcessing (or equivalent).
- **message**: string (suitable for logging or for consumer to map to user message).
- **field** or **code**: optional; for validation or API details.

---

## 7. Integration Contracts

The library depends on two external systems. This section defines what the library **requires** from them, not how they are implemented.

### 7.1 Image Generation Backend (e.g., OpenRouter)

- **Role**: Produce an image from a text prompt and optional reference image.
- **Authentication**: Bearer token (API key) in request.
- **Request**: Model ID, prompt text, optional reference image in a defined encoding (e.g., base64 data URL in a multimodal message).
- **Success response**: Image data (e.g., in JSON as base64 or as binary body); library must be able to obtain raw image bytes.
- **Failure responses**: HTTP and body or timeout; library must map to network, API, or timeout errors.
- **Cancellation**: If the library supports cancellation, it must be able to abort the in-flight HTTP (or equivalent) request.

Details of URL, message format, and response parsing are implementation concerns as long as they satisfy the above.

### 7.2 Prompt Optimization Backend (e.g., Ollama)

- **Role**: Return an optimized/enhanced prompt string given a prompt and optional context.
- **Invocation**: Out-of-process or out-of-band call (e.g., subprocess or local HTTP) with model ID and prompt; no authentication required for local service.
- **Success**: Single optimized prompt string (e.g., from stdout or response body).
- **Failure**: Timeout, non-zero exit, or error output; library must map to timeout or backend error.
- **Cancellation**: If supported, library must be able to terminate the subprocess or request so that the operation does not complete and a cancellation error can be raised.

---

## 8. Quality Attributes

### 8.1 Testability

- Every operation SHALL be invokable with explicit inputs and configuration.
- Backends (HTTP client, subprocess, etc.) SHALL be replaceable or mockable so that unit tests do not require network or Ollama.
- Errors SHALL be assertable by type and message.

### 8.2 Observability

- Library SHALL NOT require a specific logging API; it MAY accept a logger or log function. If it logs, it SHALL NOT log credentials or full image payloads.
- Progress during long operations (e.g., “optimization started”, “generation started”) MAY be exposed via callback or optional progress type if the design supports it; this spec does not mandate a particular mechanism.

### 8.3 Performance

- Prompt validation and cache lookup SHALL be fast (no network).
- Reference image processing SHALL complete in reasonable time for typical image sizes (e.g., under a few seconds).
- Optimization and generation latency are dominated by backends; library SHALL not add unnecessary serialization or copying beyond what is required by the contracts.

### 8.4 Security

- API keys and secrets SHALL only be used for backend calls and SHALL NOT appear in logs, exceptions, or return values.
- Temporary files (if any) SHALL be created with safe permissions and deleted after use.

### 8.5 Backward Compatibility

- Public API (entry points, configuration and result shapes, error types) SHALL be versioned; breaking changes SHALL be documented and, where possible, delayed or made opt-in.

---

## 9. Constraints & Assumptions

### 9.1 Constraints

- **Language**: The library is implemented in Python and consumed from Python (version as per project; e.g., 3.8+).
- **Blocking I/O**: Operations may block; no requirement for native async in this spec.
- **Session scope**: Cache and “session” boundaries are defined by the caller (e.g., one process, one CLI run, or one UI session).
- **Backends**: Image generation and prompt optimization are delegated to external backends; the library does not implement models itself.

### 9.2 Assumptions

- Callers have access to configuration (env, file, or in-memory) and pass it (or a reference) where required.
- Callers handle threading or multiprocessing if they need to avoid blocking the main thread.
- Backend contracts (OpenRouter, Ollama) remain stable enough that the library can adapt with minimal changes.
- Reference image formats and size limits align with backend capabilities.
- Cancellation is “best effort”; some backends may not support abort, in which case the library may only raise cancellation after the call returns or times out.

---

## 10. Out of Scope

The following are explicitly **out of scope** for the library spec:

- **CLI or UI**: Commands, flags, prompts, screens, or widgets.
- **Persistence**: Saving history, favorites, or cache to disk across runs.
- **Batch or queue**: Processing multiple prompts or jobs in a single call; callers may loop.
- **Streaming**: Streaming tokens or progressive image data; only final result is in scope.
- **Plugins or alternate backends**: How to plug in a different image API or optimizer is not specified; the contract in Section 7 defines what the library expects.
- **Installation and packaging**: How the package is built, installed, or distributed.
- **Concrete module layout**: File and class names; only behavioral contracts and data shapes are specified.

---

## Appendix A: Glossary

**Backend**: External system used by the library (e.g., OpenRouter, Ollama).

**Cache**: Session-scoped store for optimized prompts, keyed by prompt, model, and optional reference.

**Configuration**: Settings (API key, URLs, models, timeouts, limits) required for library operations.

**Contract**: Required inputs, outputs, and error behavior for an operation or integration point.

**Operation**: Single logical unit of work (e.g., one optimization, one generation) that may be long-running and cancellable.

**Result**: Successful output of an operation (e.g., optimized prompt, image bytes + metadata).

**Session**: Scope defined by the caller in which cache and possibly config are shared (e.g., one CLI run).

---

## Appendix B: Document Revision History

| Version | Date       | Author  | Changes                    |
|---------|------------|---------|----------------------------|
| 1.0     | 2026-02-07 | System  | Initial library specification |

---

**End of Library Specification**
