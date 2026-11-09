---
title: "Architecture"
description: "How audiolla is put together: one FastAPI process, the engine registry, staging area, URL fetcher, job queue, MCP mount and the request path."
nav_order: 22
---

# Architecture

audiolla is one Python process: a FastAPI app served by uvicorn on port 8000, with the MCP server mounted inside it. There is no database, no queue broker and no second service. State lives in memory (loaded models, job records) and on disk under `/data` (staged files, model caches).

## Components

| Component | Source | Job |
| --- | --- | --- |
| Entrypoint | [entrypoint.sh](https://github.com/psyb0t/docker-audiolla/blob/main/entrypoint.sh) | Mirrors the Hugging Face token variables, creates `/data` directories, validates `AUDIOLLA_ENABLED_ENGINES`, downloads Demucs checkpoints, starts `python3 -m audiolla`. |
| Configuration | [config.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/config.py) | Reads every `AUDIOLLA_*` variable at import and raises on a bad value; loads and filters the engine registry. |
| HTTP app | [server.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/server.py) | All 94 REST routes, the middleware stack, the idle, job and file sweepers, `/v1/catalog`, and the MCP mount. |
| API contract | [openapi.yaml](https://github.com/psyb0t/docker-audiolla/blob/main/openapi.yaml) and [schema/](https://github.com/psyb0t/docker-audiolla/tree/main/src/audiolla/schema) | The OpenAPI 3.1 spec. Request models are generated from it into `schema/_generated.py`; the server serves the spec itself at `/openapi.json`. |
| Engines | [engines/](https://github.com/psyb0t/docker-audiolla/tree/main/src/audiolla/engines) | One class per executor, built from the registry by `build_engines()`. Each has lazy load, a lock and idle unload from `engines/base.py`. |
| DSP functions | [audio.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/audio.py) | Stateless operations (trim, mix, fade, EQ, pan, de-ess, multiband compression and more) on ffmpeg, numpy and scipy. |
| Input and output | [input_resolver.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/input_resolver.py), [output_writer.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/output_writer.py) | Turn `file_path` or `file_url` into bytes; write results to `output_path` or `PUT` them to `output_url`. |
| Staging area | [files.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/files.py), [file_retention.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/file_retention.py) | Path sanitizing and containment under `/data/files`, atomic writes, and the lock-coordinated retention sweep. |
| URL fetcher | [fetch.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/fetch.py) | Fetch policy, private-address checks, manual redirects, size cap. |
| Jobs | [jobs.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/jobs.py) | In-memory job queue, status, cancellation and webhook delivery. |
| Presets and pipelines | [presets.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/presets.py), [pipeline.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/pipeline.py), [presets/](https://github.com/psyb0t/docker-audiolla/tree/main/presets) | Named op chains loaded from YAML, and the op table that runs them in memory. |
| MCP server | [mcp_server.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/mcp_server.py) | FastMCP server with 82 tools, mounted at `/v1/mcp`. |
| Auth | [auth.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/auth.py) | Optional bearer token as ASGI middleware. |
| Logging | [logging.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/logging.py) | JSON lines on stderr with request correlation. |

## Request path

```text
client
  -> MCP slash rewrite (/v1/mcp -> /v1/mcp/)
  -> request log (X-Request-Id, one summary line per request)
  -> bearer auth (skips /healthz and OPTIONS)
  -> file retention lease (every /v1/ request holds a shared lock)
  -> route
       REST handler: validate JSON body (generated model)
                     -> resolve input (staging or file_url)
                     -> engine or audio.py function
                     -> write output (staging, output_url, or job)
       /v1/mcp:      FastMCP tool -> same engines and audio.py functions
```

Middleware is listed outermost first. With `"async_job": true` the handler returns 202 at once and the same work runs as a background task that holds its own retention lease until it finishes.

## Startup

1. `entrypoint.sh` prepares `/data` and prefetches Demucs.
2. `python3 -m audiolla` configures logging and starts uvicorn.
3. Importing `server.py` loads the configuration and the registry, builds the engines and loads the presets. Any error here stops the process.
4. The lifespan hook creates `/data/files`, preloads `AUDIOLLA_PRELOAD`, starts the engine, job and file sweepers, and runs the MCP session manager.

## Memory model

Each engine holds its model between calls and drops it after `AUDIOLLA_ENGINE_TTL` of idleness. Heavy endpoints unload all other engines first, so one large model owns the GPU at a time. Requests to the same engine share its lock for loading; heavy requests to different engines evict each other. Job records live in a Python dictionary and disappear on restart, while their result files stay in the staging area until retention removes them.
