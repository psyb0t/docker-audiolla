# Docs and release rules

Prefix: DOC.

## Where docs live

- **DOC1:** `docs/` is the documentation, published by GitHub Pages from `main` with Just the Docs (`remote_theme` pinned in `docs/_config.yml`, the bundled `mocha` scheme in `docs/_sass/`). `README.md` is the front door: pitch, run, quick start, a Documentation section with full `https://psyb0t.github.io/docker-audiolla/...` links (relative links break on Docker Hub), agents, build, sponsor, license. Reference material goes into `docs/`, not the README; each fact has one home.
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

- **DOC3:** A changed project convention updates `AGENTS.md` or the matching file in `.agents/rules/` in the same change.
- **DOC4:** Every docs page has front matter with `title`, a `description` of 50 to 170 characters naming the page's real nouns, and `nav_order`; one `#` heading per page. Link pages with relative `.md` paths and repository files outside `docs/` with full `https://github.com/psyb0t/docker-audiolla/blob/main/<path>` URLs. Wrap any `{{` or `{%` in raw tags. Before calling docs done, `make docs` builds and the site checker reports no errors.

## Prose style

- **DOC5:** No em dashes or en dashes in new or changed prose: docs, README, skill, plugin manifests, rules, docstrings, comments, commit and tag messages (`d2a09b4`, "drop em dashes from the plugin manifest text"). Use a comma, colon, parentheses or a new sentence. Older files still contain dashes; remove them from lines you edit.
- **DOC6:** In `docs/` keep each paragraph on one source line, headings in sentence case, plain specific words with real route, field and variable names, tables for settings and endpoints, `curl` examples split with `\` and multi-field JSON bodies one member per line. "Directory", never "folder". No hype words.
- **DOC7:** Anything written to other people (release notes, issue replies, the pull request close message in `.github/workflows/collaborators-only.yml`) speaks as one person: "I", never "we", "our" or "the team".

## CHANGELOG

- **DOC8:** Every user-visible change gets a `CHANGELOG.md` entry. A release section goes at the top, below the intro, with the heading `## vX.Y.Z. YYYY-MM-DD` as v2.0.0 and v2.0.1 use (older headings use an em dash; do not copy that). Then a summary paragraph on its own line, then bullets. A docs-only release says so in the summary (v2.0.1: "Documentation only.").
- **DOC9:** Write each bullet for the user: what they will see, naming the exact routes, variables, files and fields, and what they must do before upgrading when something breaks (v2.0.0 told users to set `AUDIOLLA_FILES_TTL=0` first).
- **DOC10:** Versions follow the CHANGELOG intro: from v1.0.0 the REST API is stable, a breaking change is a major bump and says so, a minor bump is additive, a patch bump is docs, build or fixes only.

## Versions, tags and publishing

- **DOC11:** `pyproject.toml` `version` is canonical: `make version` prints it, `make build*` tags images `v<version>` from it, and the server reports it from package metadata. A release sets the same version in `openapi.yaml` `info.version` and `.agents/.codex-plugin/plugin.json` in the same commit. `.agents/.claude-plugin/plugin.json` has no version. `server.json`, `.agents/plugins/audiolla/package.json` and `.agents/plugins/audiolla/openclaw.plugin.json` stay at `0.0.0` in git; at publish time the MCP Registry workflow stamps the tag's version into `server.json` and the ClawHub workflow into `package.json`.
- **DOC12:** Each release is an annotated tag `vX.Y.Z` on the release commit. The tag message's first line is exactly `vX.Y.Z`, then a blank line, then that release's CHANGELOG section without its `##` heading. GitHub titles the release with the tag subject, so the version line keeps the title clean (v2.0.0 and v2.0.1 follow this; older tags start with a summary).
- **DOC13:** Pushing a `v*` tag runs `.github/workflows/pipeline.yml`: it waits for the tagged commit's `main` run to pass, promotes that run's `sha-<commit>` images to `vX.Y.Z` and `vX.Y.Z-cuda` without rebuilding, creates the GitHub release, then publishes the skill and plugin to ClawHub and `server.json` to the MCP Registry. Tag only a commit whose `main` pipeline passed. The registry rejects a `server.json` `description` over 100 characters after the images are out, so check it before tagging.
- **DOC14:** Commit subjects use `type(scope): summary` as recent history does (`ci:`, `docs(agents):`, `feat(mcp):`), or `vX.Y.Z: summary` for a release commit, with a body that says what changed and why. Never put `Closes #N`, `Fixes #N` or `Resolves #N` in a commit, tag or release note unless the user said to close that issue.
- **DOC15:** Never commit, tag, push or publish unless the user asked for that specific action in the current turn.
