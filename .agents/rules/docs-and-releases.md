# Docs and release rules

Prefix: DOC.

## Where docs live

- **DOC1:** `docs/` is the documentation, published by GitHub Pages from `main` with Just the Docs (`remote_theme` pinned in `docs/_config.yml`, the bundled `mocha` scheme in `docs/_sass/`). `README.md` is the front door: pitch, run, quick start, a Documentation section with full `https://psyb0t.github.io/docker-audiolla/...` links (relative links break on Docker Hub), agents, build, sponsor, license. Reference material goes into `docs/`, not the README.
- **DOC2:** A change ships with its docs in the same change. Owners:

  | Change | Update |
  | --- | --- |
  | REST endpoint or field | `openapi.yaml` (API1), the feature page in `docs/`, `docs/api.md` (regenerate it from the spec; it must match `openapi.yaml` exactly) |
  | Setting | `docs/configuration.md`, `.env.example`, the skill's `references/setup.md` |
  | Engine | `docs/engines.md`, the feature page, README and `docs/index.md` counts (ENG8) |
  | MCP tool | `docs/mcp.md` and the counts (MCP8) |
  | Error message | `docs/troubleshooting.md`, which quotes messages verbatim |
  | Security behaviour | `docs/security.md` |
  | Make target or CI | `docs/development.md`, `AGENTS.md` Dev workflow |

- **DOC4:** Docs pages carry a `nav_order`. Wrap any `{{` or `{%` in raw tags. Before calling docs done, `make docs` builds and the site checker reports no errors.

## CHANGELOG

- **DOC8:** In `CHANGELOG.md`, a release section goes at the top, below the intro, with the heading `## vX.Y.Z. YYYY-MM-DD` as v2.0.0 and v2.0.1 use (older headings use an em dash; do not copy that). Then a summary paragraph on its own line, then bullets. A docs-only release says so in the summary (v2.0.1: "Documentation only.").

## Versions, tags and publishing

- **DOC11:** `pyproject.toml` `version` is canonical: `make version` prints it, `make build*` tags images `v<version>` from it, and the server reports it from package metadata. A release sets the same version in `openapi.yaml` `info.version` and `.agents/.codex-plugin/plugin.json` in the same commit. `.agents/.claude-plugin/plugin.json` has no version. `server.json`, `.agents/plugins/audiolla/package.json` and `.agents/plugins/audiolla/openclaw.plugin.json` stay at `0.0.0` in git; at publish time the MCP Registry workflow stamps the tag's version into `server.json` and the ClawHub workflow into `package.json`.
- **DOC12:** Each release is an annotated tag `vX.Y.Z` on the release commit. The tag message's first line is exactly `vX.Y.Z`, then a blank line, then that release's CHANGELOG section without its `##` heading. GitHub titles the release with the tag subject, so the version line keeps the title clean (v2.0.0 and v2.0.1 follow this; older tags start with a summary).
- **DOC13:** Pushing a `v*` tag runs `.github/workflows/pipeline.yml`: it waits for the tagged commit's `main` run to pass, promotes that run's `sha-<commit>` images to `vX.Y.Z` and `vX.Y.Z-cuda` without rebuilding, creates the GitHub release, then publishes the skill and plugin to ClawHub and `server.json` to the MCP Registry. Tag only a commit whose `main` pipeline passed. The registry rejects a `server.json` `description` over 100 characters after the images are out, so check it before tagging.
