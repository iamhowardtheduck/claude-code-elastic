# Gemini CLI Transcripts

Collects **Gemini CLI chat transcripts** with Elastic Agent, maps them to ECS and the `gen_ai.*` fields, and redacts secrets at ingest.

## Data streams

| Data stream | Dataset | Source |
|---|---|---|
| `transcript` | `gemini_cli.transcript` | `~/.gemini/tmp/<project>/chats/**/*.jsonl` (Gemini CLI, including subagent chats; Windows, Linux, macOS) |

### Where Gemini CLI writes chats

| OS | Path |
|---|---|
| Linux | `/home/<user>/.gemini/tmp/<project>/chats/` (and `/root/.gemini/tmp/<project>/chats/`) |
| Windows | `C:\Users\<user>\.gemini\tmp\<project>\chats\` |
| macOS | `/Users/<user>/.gemini/tmp/<project>/chats/` |

`<project>` is a SHA-256 hash of the project root in older releases and a short project name in newer ones. The default paths match both. Subagent chats are written to `chats/<parent session>/<session>.jsonl`, which `**` picks up. If `GEMINI_CLI_HOME` is set on a host, add `<that dir>/.gemini/tmp/*/chats/**/*.jsonl`.

Older Gemini CLI releases wrote each chat as a single `.json` file that is rewritten on every turn. Those files are not collected, and the CLI converts them to `.jsonl` when a session is resumed. Gemini CLI deletes old chats if `general.sessionRetention` is set in `~/.gemini/settings.json`.

### Transcripts

One document per chat record.

- `event.action` is one of `user-prompt`, `assistant-response`, `tool-use`, `tool-result`, `assistant-thinking`, `subagent-prompt`, `local-command`, `system-notification`. These are the same values as the Claude Code Transcripts integration, so the two can be queried together.
  - User records: `user-prompt`, `tool-result` (a `functionResponse` part, with `event.outcome` set), `subagent-prompt` (first prompt of a subagent chat), `local-command` (`/command`) and `system-notification` (the injected `<session_context>`).
  - Model records: `assistant-response`, `assistant-thinking` (thoughts only) and `tool-use` (with `event.outcome` from the tool call status).
  - `gemini_cli.human_prompt: true` marks what a person typed.
- ECS: `@timestamp`, `event.id`, `message`, `user.name`, `related.user`, `service.name: gemini-cli`.
- `gen_ai.*` (ECS and OpenTelemetry GenAI names):
  - `provider.name` and `system` are `gcp.gemini`. `conversation.id` is the chat file name.
  - Also set: `operation.name`, `response.model/id`, `tool.name`, `tool.call.id`.
  - `usage.input_tokens` includes cached tokens, as OTel expects. `usage.output_tokens` is response plus thinking tokens, both billed as output. `usage.cache_read.input_tokens` is the cached share.
  - The raw counts are under `gemini_cli.tokens.*`.
- Each time the CLI attaches tokens or tool calls to a model message, it appends the whole message to the file again.
  - Every version is indexed as its own document. `_id` is a hash of host, file, message ID and version, so resumed sessions do not duplicate records.
  - Only the version without tool calls carries token usage. You can sum `gen_ai.usage.*` directly, without deduplicating.
  - If the CLI ever writes a message's tokens only on a tool-call version, that turn's tokens are not counted.
- Session headers, `$set`/`$patch`/`$rewindTo` bookkeeping and `info`/`warning`/`error` display records are dropped on the agent. Records do not carry the working directory or the CLI version. `user.name`, `gemini_cli.project` and `gemini_cli.parent_session_id` come from the file path.
- `toolCalls[].result` and `resultDisplay` are removed, because the tool output is indexed as its own `tool-result` document.
- Secrets are replaced with `[REDACTED:<type>]` in `message`, `gemini_cli.content`, `gemini_cli.toolCalls` and `gemini_cli.thoughts`. Covered: cloud keys, tokens, private keys, passwords, credentials in URLs and more. `gemini_cli.secrets.*` records only their type and length.
- Tool arguments are extracted into `gemini_cli.tool_input.{command,file_path,url,query,description}`.

## Requirements

Elastic Agent on each workstation or server that runs Gemini CLI, and Kibana 9.4 or later.

## Verify

```esql
FROM logs-gemini_cli.transcript-*
| STATS docs = COUNT(*), prompts = COUNT(*) WHERE gemini_cli.human_prompt == true,
        tokens = SUM(gen_ai.usage.input_tokens) + SUM(gen_ai.usage.output_tokens),
        latest = MAX(@timestamp) BY host.name, user.name
```

## Reference

### Transcripts

{{fields "transcript"}}
