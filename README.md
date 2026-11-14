# Claude Code → Elastic

An Elastic Agent integration (`claude_code`) that ships **Claude Code session transcripts** and **Claude Desktop app/MCP logs** to Elasticsearch. It maps them to ECS and the `gen_ai.*` fields, redacts secrets at ingest, and can optionally run **ML inference** on every human prompt: semantic embeddings plus NLP classification for prompt injection, jailbreaks, toxicity, intent and PII. A toggle controls the inference. It ships with business and security dashboards. Detection rules, a model-pricing table and inference monitoring are available as optional extras.

```
packages/claude_code/        the integration (elastic-package source)
  data_stream/transcript/      ~/.claude/projects/**/*.jsonl  -> logs-claude_code.transcript-*
  data_stream/desktop_log/     Claude Desktop main.log, mcp*.log -> logs-claude_desktop.log-*
  kibana/dashboard/            Business Analytics + Security dashboards
extras/                      things a package cannot install (run extras/setup.sh)
  pricing/                     claude-model-pricing lookup index (spend panels)
  inference/                   dense_vector mapping for the prompt embedding
  detection-rules/             10 Elastic Security ES|QL rules (imported disabled)
  inference-monitoring/        stats collector workflow, [ML Inference] Admin dashboard, 9 alert rules
docs/inference-models.md     models for the optional inference, eland import, sizing
```

## What gets collected

| Source | Where | Data stream |
|---|---|---|
| Claude Code (CLI, VS Code/JetBrains, Desktop "Code" tab) | `~/.claude/projects/<project>/<session>.jsonl`, subagents below it | `logs-claude_code.transcript-*` |
| Claude Desktop Cowork sessions | `%APPDATA%\Claude\local-agent-mode-sessions\…` / `claude-code-sessions\…` (macOS: `~/Library/Application Support/Claude/…`) | `logs-claude_code.transcript-*` |
| Claude Desktop app + MCP servers | `%APPDATA%\Claude\logs\`, `%LOCALAPPDATA%\Claude\Logs\`, `~/Library/Logs/Claude/` | `logs-claude_desktop.log-*` |

Desktop "Chat" conversations are stored server-side, not on disk, so they can't be collected. `~/.claude/history.jsonl` (typed prompts only) is not collected either. Claude Code deletes transcripts after `cleanupPeriodDays` (default 30, in `~/.claude/settings.json`). Never set it to 0.

See [`packages/claude_code/docs/README.md`](packages/claude_code/docs/README.md) for the field reference.

---

## Deploy

### Requirements
- Elasticsearch and Kibana **9.4 or later** with Fleet, plus Elastic Agent 9.4 or later on every machine where Claude Code or Claude Desktop runs (Windows, macOS, Linux).
- A user or API key that can manage Fleet, index templates and ingest pipelines. Importing rules and dashboards also needs Kibana privileges.
- Optional inference also needs ML nodes and the Elastic Inference Service. See [docs/inference-models.md](docs/inference-models.md).

### 1. Build the package

Alternatively, download `claude_code-<version>.zip` from the GitHub release.

```bash
go install github.com/elastic/elastic-package@latest
cd packages/claude_code
elastic-package lint && elastic-package build      # -> build/packages/claude_code-0.1.0.zip
```

### 2. Upload it to Kibana

```bash
curl -X POST "$KIBANA_URL/api/fleet/epm/packages" \
  -H "Authorization: ApiKey $ES_API_KEY" -H 'kbn-xsrf: true' \
  -H 'Content-Type: application/zip' \
  --data-binary @build/packages/claude_code-0.1.0.zip
```

This installs the index templates, the three ingest pipelines (`logs-claude_code.transcript-<ver>`, `…-inference` and `…-classify`, plus `logs-claude_desktop.log-<ver>`) and the two dashboards. `elastic-package install --zip <file>` does the same against the stack configured for elastic-package.

> If you already collect transcripts with **Custom Logs (Filestream)** under the same dataset names, read [Migrating from a Custom Logs setup](#migrating-from-a-custom-logs-setup) first.

### 3. Add the integration to agent policies

In Kibana, go to **Fleet → Integrations → Installed → Claude Code → Add Claude Code** and pick the agent policies for your workstations and servers. Then configure the two streams:

- **Claude Code session transcripts**
  - **Paths**: the defaults cover Windows, macOS, Linux (`/home/*` and `/root`) and Cowork sessions. Paths that don't exist on a host are ignored. If `CLAUDE_CONFIG_DIR` is set on a host, add that directory.
  - **Enable ML inference** (off by default): turns on prompt embedding.
  - **Prompt classification** (on by default, but only takes effect when inference is enabled): adds the NLP classifiers. Turn it off for embedding-only.
  - The advanced options cover exclude files (Cowork `audit.jsonl` is excluded), ignore-older (720h), maximum line size (20 MB), tags and agent processors.
- **Claude Desktop app and MCP logs**: the default paths cover Windows and macOS. There is no official Linux build of Claude Desktop.

Inference is switched per policy, so you can enable it for some machines and leave it off for others.

### 4. Optional extras

```bash
export ES_URL=https://elasticsearch:9200 KIBANA_URL=https://kibana:5601 ES_API_KEY=...   # or ES_USER/ES_PASSWORD
export CA_CERT=/path/to/ca.crt     # private CA, optional
extras/setup.sh pricing              # model price table for the spend panels (edit extras/pricing/*.ndjson to update prices)
extras/setup.sh rules                # 10 detection rules, imported DISABLED; enable them in Security > Rules and add actions
extras/setup.sh inference-mapping    # required before enabling inference
extras/setup.sh inference-monitoring # stats collector + [ML Inference] Admin dashboard + 9 alert rules (disabled)
extras/setup.sh all
```

`inference-monitoring` uses Kibana Workflows: a scheduled workflow samples `_ml/trained_models/_stats` and the ingest stats of the package pipelines every minute. If you install a package version other than 0.1.0, set `PKG_VERSION` so the collector watches the right pipeline names. The alert rules are created disabled, without actions. Add your connector (email, Slack and so on) in **Stack Management → Rules**, then enable them.

### 5. Enabling inference

1. Deploy the models: [docs/inference-models.md](docs/inference-models.md).
2. `extras/setup.sh inference-mapping`.
3. Turn on **Enable ML inference** in the integration policy (and **Prompt classification** if you want it).
4. Optional: `extras/setup.sh inference-monitoring`. Classification takes about 20-45 s of ML time per prompt on CPU, so check that the deployments keep up.

### 6. Verify

```esql
FROM logs-claude_code.transcript-*
| STATS docs = COUNT(*), prompts = COUNT_DISTINCT(event.id) WHERE claude_code.human_prompt == true,
        latest = MAX(@timestamp) BY host.name, user.name
```
```esql
FROM logs-claude_desktop.log-*
| STATS n = COUNT(*), unparsed = COUNT(*) WHERE tags == "claude_desktop_unparsed_line" BY claude_desktop.log_file
```

Then open **[Claude Code Transcripts] Business Analytics** and **[Claude Code Transcripts] Security** from the dashboards list.

---

## Migrating from a Custom Logs setup

If transcripts or Desktop logs already arrive through **Custom Logs (Filestream)** with dataset `claude_code.transcript` or `claude_desktop.log`, Fleet has already created index templates with the same names as this package's. Switch over in this order:

1. Delete the Custom Logs integration policies for those datasets: **Fleet → Agent policies → (policy) → Integrations → Delete**. Agents stop shipping until step 4.
2. Delete the old index templates, so the package can create its own. The existing data stays.
   ```
   DELETE _index_template/logs-claude_code.transcript
   DELETE _index_template/logs-claude_desktop.log
   ```
   Keep `logs-claude_code.transcript@custom`. The package template includes it too, and it holds the dense_vector mapping and any other customisations.
3. Install the package (step 2 above) and add it to the same policies (step 3).
4. Roll the data streams over, so the new template and pipeline apply right away:
   ```
   POST logs-claude_code.transcript-default/_rollover
   POST logs-claude_desktop.log-default/_rollover
   ```
5. The old hand-made pipelines (for example `claude-code-transcript`, `claude-prompt-classify`, `claude-desktop-log`) are no longer referenced, so you can delete them once you're happy with the new ones.

Agents keep their file offsets only within the same input. The new integration policy is a new input, so it re-reads transcripts newer than `ignore_older`. That doesn't create duplicates, because `_id` is the transcript line `uuid` and the rewritten lines replace themselves within the current backing index.

---

## Design notes

- **Inference toggle**: the policy switches add internal tags (`claude_code_embed`, `claude_code_classify`) on the agent side. The transcript pipeline calls its `inference` sub-pipeline only when those tags are present, then removes them. With inference off, the pipeline makes no inference calls.
- **Secrets**: a deterministic scanner covers AWS, GitHub, GitLab, Slack, Stripe, OpenAI/Anthropic keys, JWTs, private keys, passwords, URL credentials and more. It replaces values in `message`, in message content, in tool inputs and in the Desktop MCP payloads. Only type and length are kept.
- **Tokens**: `gen_ai.usage.input_tokens` follows OpenTelemetry and **includes** cache reads and writes. Anthropic's raw split stays in `claude_code.message.usage.*`, and the spend panels use it with the pricing table. One assistant turn can span several lines that repeat the same usage, so deduplicate on `gen_ai.response.id`.
- **Dense vectors**: package-spec 3.x has no `dense_vector` field type, so the embedding mapping comes from `extras/setup.sh inference-mapping` via the `@custom` component template.
- **Known gaps**: the Desktop log line formats and the Cowork folder layout come from public reports and need checking on more machines. Unmatched Desktop lines are kept and tagged `claude_desktop_unparsed_line`. The embedding endpoint ID is fixed in the package pipeline.

## Development

```bash
cd packages/claude_code
elastic-package lint
elastic-package build
elastic-package stack up -d && elastic-package install   # local test stack (Docker)
```
Bump `version` in `manifest.yml` and add an entry to `changelog.yml` for every change.
