# API contract: spec-first, non-negotiable

Prefix: API.

The REST API contract lives in `openapi.yaml`. Period. It is the single source of truth for every REST endpoint's request and response shape: paths, methods, parameters, request bodies, response bodies, error codes, examples. Everything. The MCP endpoint at `/v1/mcp` is not described there (`mcp.md`).

## The rule

- **API1:** Write the contract in `openapi.yaml` first. Adding an endpoint, changing a request body, changing a response shape, documenting a parameter: all of it happens in `openapi.yaml` before any handler code. When code and spec disagree, the change that touches either one brings them back in line.
- **API2:** Generate the Pydantic models from it with `make generate` (`scripts/generate_models.sh`, datamodel-code-generator, run inside the dev container). The output is `src/audiolla/schema/_generated.py`. Handler code imports models from `audiolla.schema`.
- **API3:** Never hand-edit `src/audiolla/schema/_generated.py`. Every `make generate` regenerates it from the YAML and clobbers manual edits.
- **API4:** Never hand-write Pydantic request or response models elsewhere. No `class FooRequest(BaseModel)` anywhere in the codebase. If a handler needs a request model, it is defined in the YAML and imported from `audiolla.schema`. The one sanctioned exception is `src/audiolla/schema/__init__.py`, which re-declares generator aliases (`X = BaseAudioInputRequest`) as empty subclasses because FastAPI needs a real class for body detection; it adds no fields.
- **API5:** Never hand-write FastAPI `Form()` or `File()` parameters for new endpoints. A handler takes a single Pydantic body parameter, `async def foo(req: FooRequest)`, generated from the YAML. If you are about to type `= Form(...)`, `= File(...)` or `class FooRequest(BaseModel)`, stop, edit `openapi.yaml`, run `make generate`, then continue. `/v1/midi/compose`, `/v1/midi/generate` and `/v1/midi/drum` still predate this (raw `Request` body plus `Form()` defaults read from query parameters); do not copy them.

## When you add or change an endpoint

- **API6:** Follow these steps in order:
  1. Edit `openapi.yaml`: add the path and define the request and response schemas, using `$ref` to shared components under `components/schemas`.
  2. Run `make generate` to regenerate `src/audiolla/schema/_generated.py`.
  3. Add or edit the handler in `src/audiolla/server.py`, importing the request model from `audiolla.schema`. The handler is hand-written because it holds business logic; the request and response shape is not.
  4. Commit `openapi.yaml` and the regenerated `_generated.py` together.
- **API7:** If two endpoints share a request shape, define it once under `components/schemas` and `$ref` it from every path. Do not duplicate. Every audio endpoint inherits `BaseAudioInputRequest` (`file_path` / `file_url`) and every audio-producing one `BaseAudioOutputRequest` (`output_path` / `output_url`, `output_format`, `async_job`, `webhook_url`) through `allOf`; multi-input endpoints use `MultiAudioInputRequest`. Pydantic models inherit cleanly when generated from `allOf` and `oneOf`.

## Wire conventions the contract encodes

- **API8:** Every audio endpoint takes an `application/json` body. Raw bytes enter only through `PUT /v1/files/{path}` (raw request body). No base64 audio in REST responses.
- **API9:** Input is exactly one of `file_path` or `file_url`; an audio-producing endpoint needs exactly one of `output_path` or `output_url` unless `async_job` is true, in which case the result is staged at `jobs/{id}.{ext}`. The spec keeps both fields nullable because a top-level `oneOf` does not survive datamodel-codegen inheritance, so every handler calls `validate_input_xor` (or `validate_multi_input_xor`) and `validate_output_xor` from `audiolla.schema` right after validation.
- **API10:** Errors are `HTTPException` with a string `detail`, rendered as `{"detail": "..."}` (the `ErrorBody` schema). Keep the meanings: 400 bad input or a refused URL, 404 unknown engine, preset, job or staged file, 413 over `AUDIOLLA_MAX_UPLOAD_BYTES`, 415 unsupported `output_format`, 422 schema validation, 401 from the auth middleware. Engine failures raise a subclass of `AudioConversionError`, which handlers turn into 400.
- **API11:** A new route also goes into `_CATALOG_GROUPS` in `server.py` (served at `/v1/catalog`), and into the docs (DOC2).

## Why this matters

The project started spec-first. Over many sessions every new endpoint got hand-coded `Form(...)` parameters in `server.py`, because that is the FastAPI default and the path of least resistance. By the v0.24.0 audit `openapi.yaml` had 17 paths and `server.py` had 90 endpoints: 73 endpoints with no spec coverage. The spec rotted into a stale subset of reality, clients could not trust it, generated SDKs would have missed 80% of the API, and OpenAPI reviews became impossible.

The cleanup (shipped as v1.0.0) backfilled the spec to every route, regenerated the models, moved handlers to `audiolla.schema`, dropped multipart from the audio routes, required `output_path` or `output_url` on audio-producing endpoints and removed base64 audio from MCP responses. Today `openapi.yaml` covers all 94 routes in `server.py`. From then on spec-first is the only way new endpoints get added.

## Build infrastructure

- `openapi.yaml`: source of truth, OpenAPI 3.1, over 4000 lines.
- `scripts/generate_models.sh`: the datamodel-codegen wrapper.
- `make generate`: runs the script inside the dev container.
- `src/audiolla/schema/_generated.py`: generated, committed, never edited; prod images do not need the generator.
- `src/audiolla/schema/__init__.py`: hand-written re-export layer, fine to edit; a thin wrapper that exposes generated names plus the validators and coercion helpers.
- **API12:** CI fails when `openapi.yaml` changes without a re-run of `make generate`: the `code` job in `pipeline.yml` passes `generate_command: "make generate"` to `code-workflow.yml`, which regenerates and fails on any `git status` change. That only works while generation is deterministic, so `scripts/generate_models.sh` passes `--disable-timestamp` (and `--set-default-enum-member`, which keeps enum defaults type-correct); keep both. Run `make generate` and check `git status` locally before pushing an API change.
