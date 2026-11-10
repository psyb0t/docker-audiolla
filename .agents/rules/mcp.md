# MCP rules

Prefix: MCP.

The MCP server is `build_mcp_server()` in `src/audiolla/mcp_server.py`, mounted at `/v1/mcp` by `src/audiolla/server.py`. The OpenClaw bridge in `.agents/plugins/audiolla/` and the MCP Registry entry `server.json` point clients at it.

## Server and transport

- **MCP1:** Keep FastMCP stateless with JSON responses (`stateless_http=True`, `json_response=True`) and `mcp.settings.streamable_http_path = "/"`, so clients connect to `/v1/mcp`, not `/v1/mcp/mcp`. `_MCPSlashRewriteMiddleware` in `server.py` rewrites bare `/v1/mcp` to `/v1/mcp/` so the mount never answers with a 307; it is added last, which makes it the outermost layer. The lifespan in `server.py` runs `MCP_SERVER.session_manager.run()`; keep that when touching startup.
- **MCP2:** `mcp_server.py` never imports `server.py`. It gets server state injected through `build_mcp_server(engines=..., registry=..., presets=...)` and uses `audio.py`, `pipeline.py`, `fetch.py` and `files.py` directly, as the module docstring explains (it avoids a circular import).

## Tools

- **MCP3:** A tool reports failure by raising `ValueError` with a caller-readable message, which FastMCP returns as a tool error. Translate at the tool boundary: `AudioConversionError`, `FilePathError` and `FetchError` become `ValueError(str(exc))`; a missing engine is `ValueError("<slug> engine not configured")`.
- **MCP4:** Tools take the same inputs as REST: exactly one of `file_path` or `file_url`, resolved through `_load_input`, so staged paths go through `files.sanitize_path` and URLs through `fetch.fetch_to_bytes` and the fetch policy.
- **MCP5:** Audio-producing tools take exactly one of `output_path` or `output_url` and return `{path|url, size, ...}`, matching REST; per-stem tools (`separate`, `hpss`) take `output_paths` / `output_urls` maps. Route results through `_emit_audio` (or `fetch.upload_bytes` directly), never a bare `httpx` client (SEC5). Several tools still break this (only `output_url` on `restore`, `enhance`, `deess`, `audio_thumbnail` and the MIDI tools; only `output_path` on `stretch`; no output argument on `hpss` and `slice_at_beats`); fix them toward this rule when you touch them, never copy them.
- **MCP6:** No new base64 audio, MIDI, image or video in tool results; results land in staging or at `output_url`. `put_file` is the one base64 input, validated with `base64.b64decode(..., validate=True)` and capped at `config.MAX_UPLOAD_BYTES`. `get_file` returns only `path` and `size`, despite its docstring. `beats`, `melody` and `silence` still return inline base64 when asked for audio or MIDI without an output.
- **MCP8:** The tool count (82 today) is written in several places: the README table and documentation table, `docs/mcp.md`, `docs/architecture.md` and `AGENTS.md`. The `mcp server initialised: %d tools` log line counts live. Adding, removing or renaming a tool updates all of them, the `docs/mcp.md` tool table and the skill in the same change.

## Bridge plugin

- **MCP9:** `.agents/plugins/audiolla/bin/cli.js` only launches `mcp-remote` (pinned to an exact version in `package.json`) against `$AUDIOLLA_URL/v1/mcp` with `--transport http-only`. stdout is the MCP channel, so the bridge writes diagnostics to stderr only, and it passes `AUDIOLLA_AUTH_TOKEN` as a header argument without logging it.
