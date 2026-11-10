# Security rules

Prefix: SEC.

audiolla is a self-hosted service with one optional shared token and one server-wide staging area; it is not multi-tenant (`docs/security.md`). The repository is public.

## Secrets

- **SEC1:** The server logs only whether auth is on (`auth=%s` in `_lifespan`), never the token, and the auth middleware logs method and path on a rejection, never the presented value.
- **SEC2:** Secret scanning uses `.gitleaks.toml`, which extends the default rules. Add allowlist entries by path, never as a regex on matched text.

## Authentication

- **SEC3:** Auth stays ASGI middleware (`BearerAuthMiddleware` in `src/audiolla/auth.py`), so one check covers every route, the mounted MCP app and `/openapi.json`. Only `/healthz` and `OPTIONS` preflights are exempt; any new route or mount sits behind it.

## Input handling

- **SEC4:** Every caller-supplied staging path goes through `files.sanitize_path` and then `files.resolve_under(config.FILES_DIR, ...)` before any disk access, on REST and MCP alike: no null bytes, backslashes, empty, `.` or `..` segments, and the resolved path stays under the root. Reads and deletes refuse symlinks, listings skip them, writes go through `files.write_atomic`.
- **SEC5:** Every outbound request built from caller input goes through `src/audiolla/fetch.py`: `fetch_to_bytes` for downloads and `upload_bytes` for `output_url`. Both call `validate_url`, so `AUDIOLLA_FETCH_MODE` (default `disabled`), the host lists, the scheme list and the private-address check apply, redirects are re-validated by hand (`follow_redirects=False`), and downloads stream under `AUDIOLLA_MAX_UPLOAD_BYTES`. Known violations to fix, not copy: the `audio_thumbnail`, `chords_to_midi`, `deess`, `drum_pattern` and `midi_humanize` MCP tools upload with a bare `httpx.AsyncClient`, and job webhooks (`JobQueue._fire_webhook` in `jobs.py`) post to an unchecked URL.
- **SEC6:** Every ingress path has a size cap of `config.MAX_UPLOAD_BYTES`: `PUT /v1/files`, staged inputs (`_read_staged`), fetched bodies, staged outputs (`_write_staged`) and MCP `put_file`. A new input path gets the same cap in the same change.

## Retention and shared data

- **SEC8:** Code that writes or reads staged files during a request or job must run under a retention lease: `FileRetentionMiddleware` covers `/v1/` requests, and `_submit_job` holds one until the job finishes (`on_done=lease.close`). A new background path that touches `/data/files` acquires `FileRetention.acquire()` itself. The sweep skips `.part` files and symlinks; keep both exclusions.

## Logs and errors

- **SEC9:** Fetch and upload URLs are logged at INFO with their query strings, which include presigned signatures (`fetch.py`). Do not add more URL or body logging at INFO; anything that may carry credentials or user content belongs at DEBUG or nowhere.
- **SEC10:** The global exception handler returns `{"detail": "<Class>: <message>"}` on 500. Do not put secrets, tokens or full upstream responses into exception messages.

## Images and supply chain

- **SEC11:** Supply chain pins: the heavy stack with `--require-hashes`, light dependencies from the frozen `uv.lock` behind the seven-day `exclude-newer` gate, `mcp-remote` by exact version. The maintainer's reusable workflows are referenced at `@master` on purpose; do not pin them.
- **SEC12:** Both images run as uid and gid 1000 (`USER 1000:1000`), own `/data` as that user, and keep the `HEALTHCHECK` against `/healthz`.
- **SEC13:** `docker run` examples in `README.md` and `docs/` publish the port on loopback (`-p 127.0.0.1:8000:8000`) and pass tokens with `-e NAME` from the environment, never inline.
- **SEC14:** Torch 2.5.1 carries CVE-2025-32434 (unsafe checkpoint loading). Never `torch.load` a caller-supplied file or let a request choose a checkpoint path; models come only from each engine's fixed source.
- **SEC15:** Every third-party component installed into a published image under a copyleft or notice-requiring license is listed in `THIRD_PARTY.md` with license, source and location, and its license text goes into `LICENSES/` when the license requires shipping it.
