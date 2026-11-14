# Claude Code Transcripts Integration

Collects **Claude Code session transcripts** and **Claude Desktop app/MCP logs** with Elastic Agent, maps them to ECS and the `gen_ai.*` fields, redacts secrets at ingest, and can optionally run ML inference (prompt embeddings + NLP classification) on every human prompt.

## Data streams

| Data stream | Dataset | Source |
|---|---|---|
| `transcript` | `claude_code.transcript` | `~/.claude/projects/**/*.jsonl` (Claude Code CLI, IDE extensions, Desktop "Code" tab, Desktop Cowork sessions) |
| `desktop_log` | `claude_desktop.log` | Claude Desktop `main.log`, `mcp.log`, `mcp-server-*.log` (Windows, macOS) |

### Transcripts
One document per conversation line. `event.action` is one of `user-prompt`, `assistant-response`, `tool-use`, `tool-result`, `assistant-thinking`, `subagent-prompt`, `local-command`, `system-notification`; `claude_code.human_prompt: true` marks what a person actually typed.

- ECS: `@timestamp`, `event.id` (also `_id`, so resumed sessions do not duplicate lines), `message`, `user.name`, `related.user`, `process.working_directory`, `service.name/version`.
- `gen_ai.*` (ECS + OpenTelemetry GenAI names): `provider.name`/`system`, `conversation.id`, `operation.name`, `request.model`, `response.model/id/finish_reasons`, `tool.name`, `tool.call.id`, `usage.input_tokens` (**includes cached tokens**, per OTel), `usage.output_tokens`, `usage.cache_read.input_tokens`, `usage.cache_creation.input_tokens`.
  For cost, use Anthropic's raw split under `claude_code.message.usage.*` (uncached `input_tokens`, cache reads and cache writes are priced differently).
- One assistant turn can span several lines sharing `gen_ai.response.id`, each repeating usage: deduplicate on it before summing tokens.
- Secrets (cloud keys, tokens, private keys, passwords, credentials in URLs, ...) are replaced with `[REDACTED:<type>]` in `message`, `claude_code.message.content` and tool inputs; `claude_code.secrets.*` records type and length only.
- Tool inputs are extracted into `claude_code.tool_input.{command,file_path,url,skill,description}`.

### Desktop logs
- `log.logger` holds the app component (`[oauth-v2]`, `[RemotePluginManager]`, …) or the MCP server name. `claude_desktop.log_file` is the file name (`main`, `mcp`, `mcp-server-<name>`, `chrome-native-host`, …).
- `event.action`: `log`, `mcp-request`, `mcp-response`, `mcp-notification`, `mcp-server-request`, with `claude_desktop.mcp.{server,method,id,direction,result_blocks}`. `event.outcome` is set on responses.
- Current Claude Desktop builds log only a **summary** of each MCP message (`method="tools/call" id=10 params`, `id=10 result(1 blocks)`), so tool names and arguments are not in these logs. `tools/call` sets `gen_ai.operation.name: execute_tool` and `gen_ai.tool.call.id`.
- Older builds logged the full JSON-RPC message. The pipeline parses it, adds `gen_ai.tool.name` and `error.*`, and keeps the payload unindexed in `claude_desktop.mcp.payload` after secret redaction.
- Each MCP message is written to both `mcp.log` and `mcp-server-<name>.log`. Filter on one `claude_desktop.log_file` when counting.
- `main.log` uses local time, so the agent adds `event.timezone` for it. Lines that match no known format are kept and tagged `claude_desktop_unparsed_line`.

## ML inference (optional, off by default)

The **Enable ML inference** switch on the transcript stream turns on, for human prompts only:

1. **Prompt embedding** with the `.jina-embeddings-v5-text-nano` inference endpoint (Elastic Inference Service) into `claude_code.prompt_embedding` (768 dims, cosine). Used by the semantic panels on the Security dashboard and by the semantic detection rules.
2. **Prompt classification** (switch **Prompt classification**, on by default once inference is enabled) into `claude_code.prompt_classification.*`: prompt injection, jailbreak, toxicity, offensive language, five zero-shot groups (security, agent action, task, interaction, moderation) and NER.

Timing is recorded in `claude_code.inference.{total_ms,embedding_ms,classify_ms,steps.*}`. Inference failures never block indexing; they are recorded in `claude_code.prompt_embedding_error` and `claude_code.prompt_classification.errors`.

Before enabling it:
- Run `extras/setup.sh inference-mapping` from the repository (adds the `dense_vector` mapping, which integration packages cannot declare).
- Deploy the models (repository `docs/inference-models.md`). Classification is ML-heavy: the zero-shot model runs five passes per prompt.

## Dashboards
- **[Claude Code Transcripts] Business Analytics**: activity, users, projects, models, tokens, estimated spend (needs the `claude-model-pricing` lookup index: `extras/setup.sh pricing`), topics.
- **[Claude Code Transcripts] Security**: risky commands, secrets, file and network access, auto-mode blocks and, with inference enabled, classification and semantic threat search.

## Requirements
Elastic Stack 9.4+ and Elastic Agent 9.4+ on the hosts where Claude Code or Claude Desktop run. Claude Code deletes transcripts after `cleanupPeriodDays` (default 30) in `~/.claude/settings.json`.
