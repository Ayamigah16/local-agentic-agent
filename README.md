# local-agentic-agent

A local agentic coding harness: a small [Qwen3](https://ollama.com/library/qwen3) model
running via [Ollama](https://ollama.com), given Claude-Code-style Agent Skills and
[MCP](https://modelcontextprotocol.io) tools, driven through a tool-calling REPL loop.

Runs fully on-device (CPU-only here, no GPU required).

## Quick start

```bash
./run.sh
```

This makes sure Ollama is running (starting the systemd user service if needed), then
launches the agent REPL. Type a task at the `>` prompt; type `exit` to quit.

## How it works

- **`agent/ollama_client.py`** — thin wrapper over Ollama's `/api/chat` endpoint
  (tool-calling enabled, `num_thread` tuned to use all CPU cores).
- **`agent/skills.py`** — loads [Agent Skills](vendor/agent-skills) (`SKILL.md` files:
  YAML frontmatter + a workflow description). Their names and one-line descriptions go
  into the system prompt; full instructions are only loaded on demand.
- **`agent/tools.py`** — built-in tools: `load_skill`, `read_file`, `write_file`,
  `run_shell`, plus whatever's registered in `agent/token_api_tools.py` (currently
  `figma_api_get`, `vercel_api_get`). Writes and shell commands ask for `[y/N]`
  confirmation in the terminal before running.
- **`agent/token_api_tools.py`** — declarative registry for "GET a REST API with a
  personal access token" tools. Add an entry here (base URL, token env var, header
  format) instead of hand-writing a new function each time — see below.
- **`agent/mcp_client.py`** — `MCPManager` connects to MCP servers over stdio or
  streamable HTTP (config in [`mcp_servers.json`](mcp_servers.json)), discovers their
  tools, and namespaces them as `mcp_<server>_<tool>` so the model can call them like any
  other tool. A server that fails to connect (unreachable, not running, etc.) is skipped
  with a warning rather than blocking startup.
- **`agent/harness.py`** — the REPL: merges built-in + MCP tool schemas, sends them to
  the model each turn, executes whatever tool calls come back, and loops until the model
  responds with plain text.

## Models

Two models are pulled:

| Model | Size | Notes |
|---|---|---|
| `qwen3:4b` | 2.5GB | **Default.** ~2 min per turn on this hardware — usable interactively. |
| `qwen3:8b` | 5.2GB | Higher quality, but ~5-6 min per turn (CPU-only) — better suited to background/batch tasks than live chat. |

Switch models with `--model`:

```bash
./run.sh --model qwen3:8b
```

Note: qwen3.6 (Qwen's newest generation) only ships in 27B+ sizes, which don't fit in
16GB of RAM without a GPU — that's why this setup uses regular Qwen3 instead.

## Tool count vs. speed

Every tool's schema — MCP or built-in — gets sent to the model on *every* turn. On
CPU-only inference, more tools means a longer prompt means a slower response, regardless
of whether that tool came from MCP or was hand-written. This isn't an MCP-specific cost;
it's a straight token-count cost.

Given that, **prefer `run_shell` + an existing CLI over adding a new MCP server** when a
good CLI already exists (`aws`, `gh`, `vercel`, etc.) — one generic shell tool costs far
less prompt budget than a dedicated MCP server's full tool catalog (the filesystem MCP
server alone exposed 14 tools; `read_file`/`write_file`/`run_shell` cover the same ground
for a fraction of the token cost). Reach for MCP only when there's no reasonable CLI, or
when you specifically need MCP-native structured output.

`mcp_servers.json` ships with `"mcpServers": {}` — no servers connected by default — for
exactly this reason. See "Currently configured integrations" below for what's active and
how.

## Adding MCP servers

Edit `mcp_servers.json` (same `mcpServers` format as Claude Desktop/Claude Code):

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/scope"]
    },
    "some-other-server": {
      "command": "uvx",
      "args": ["some-mcp-server"],
      "env": { "API_KEY": "..." }
    }
  }
}
```

Restart `./run.sh` to pick up changes — servers are connected once at startup.

HTTP-transport servers (as opposed to subprocess/stdio ones) are configured with a `url`
instead of `command`/`args`:

```json
{
  "mcpServers": {
    "some-http-server": {
      "url": "http://127.0.0.1:PORT/mcp",
      "headers": { "Authorization": "Bearer ..." }
    }
  }
}
```

Note on OAuth-gated remote MCP servers (e.g. Figma's hosted `mcp.figma.com`, Vercel's
`mcp.vercel.com`, Railway's `mcp.railway.com`): these require a browser login *and* are
often restricted to an allowlist of known clients (Claude Code, Cursor, VS Code, etc.) —
a homegrown client like this one generally can't complete that flow. Where a service also
exposes a plain REST API with a personal access token (no OAuth, no allowlist), prefer
adding an entry to `agent/token_api_tools.py` instead of wiring the MCP server:

```python
TokenApiTool(
    name="some_service_api_get",
    base_url="https://api.example.com/v1",
    token_env_var="SOME_SERVICE_TOKEN",
    header_name="Authorization",
    header_format="Bearer {token}",   # or just "{token}" for a raw-value header
    token_help="Generate one at example.com > Settings > Tokens.",
    description="Read-only GET against Example's REST API. Use for ...",
)
```

### Currently configured integrations

No MCP servers are connected by default (`mcp_servers.json` is `{"mcpServers": {}}`).
Instead:

| Service | Path | Auth |
| --- | --- | --- |
| Filesystem | built-in `read_file`/`write_file`/`run_shell` | none — writes/commands ask `[y/N]` first |
| AWS | `run_shell` + `aws` CLI | existing `~/.aws/credentials` / CLI profile chain (already configured on this machine) |
| GitHub | `run_shell` + `gh` CLI | already authenticated on this machine (`gh auth status`) |
| Figma | direct API tool (`token_api_tools.py`) | `FIGMA_TOKEN` in `.env` |
| Vercel | direct API tool (`token_api_tools.py`) | `VERCEL_TOKEN` in `.env` |

Figma and Vercel stay as dedicated tools rather than `run_shell` + `curl` because there's
no CLI for either — a direct API tool is still cheaper than an MCP server here, just not
as cheap as reusing an existing CLI.

### Not yet wired up — needs your CLI login first

Railway, Azure, and GCP don't have a clean token-only path like the ones above — each
needs its own CLI installed *and* logged in interactively (a browser or device-code flow
I can't complete on your behalf in this session):

- **Railway** — install the CLI, run `railway login`, then the MCP server can reuse that
  session (`railway setup agent`). Check first whether Railway also issues a plain API
  token for headless/CI use — if so, `token_api_tools.py` is simpler than the CLI route.
- **Azure** — needs the `az` CLI (not currently installed in this WSL environment) and
  either `az login` or a service principal (`AZURE_CLIENT_ID`/`AZURE_CLIENT_SECRET`/
  `AZURE_TENANT_ID`) for headless auth.
- **GCP** — needs the `gcloud` CLI (not currently installed) and either
  `gcloud auth application-default login` or a service account JSON key file.

Once any of these is set up on your end, tell me and I'll wire up the corresponding
`mcp_servers.json` entry.

## Skills

Skills come from a fork of [`addyosmani/agent-skills`](https://github.com/addyosmani/agent-skills)
([`Ayamigah16/agent-skills`](https://github.com/Ayamigah16/agent-skills)), vendored as a
git submodule at `vendor/agent-skills/`.

Cloning this repo for the first time:

```bash
git clone --recurse-submodules <this-repo-url>
```

If you already cloned without that flag:

```bash
git submodule update --init
```

To pull upstream (`addyosmani/agent-skills`) updates into the fork, then bump this repo's
pinned submodule commit:

```bash
cd vendor/agent-skills && git pull upstream main && git push
cd ../.. && git add vendor/agent-skills && git commit -m "Bump agent-skills submodule"
```

## Managing the Ollama service

Ollama runs as a `systemd --user` service (no sudo required), enabled to start
automatically whenever this WSL instance starts:

```bash
systemctl --user status ollama.service    # check it's running
systemctl --user stop ollama.service      # stop it
systemctl --user restart ollama.service   # restart it
journalctl --user -u ollama.service -f    # tail its logs
```

## Requirements

- Python 3 with `requests`, `pyyaml`, `mcp` (`pip install --user mcp` if missing)
- Node.js/`npx` for MCP servers distributed as npm packages
- Ollama, installed as a portable user binary under `~/.local/ollama/` (no root needed)
