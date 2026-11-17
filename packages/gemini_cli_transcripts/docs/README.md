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

**Exported fields**

| Field | Description | Type |
|---|---|---|
| @timestamp | Event timestamp. | date |
| data_stream.dataset | Data stream dataset. | constant_keyword |
| data_stream.namespace | Data stream namespace. | constant_keyword |
| data_stream.type | Data stream type. | constant_keyword |
| event.dataset | Event dataset. | constant_keyword |
| event.module | Event module. | constant_keyword |
| gemini_cli.content.functionResponse.id | Tool call ID this result answers. | keyword |
| gemini_cli.content.functionResponse.name | Tool name. | keyword |
| gemini_cli.content.functionResponse.response.error | Tool error. | match_only_text |
| gemini_cli.content.functionResponse.response.output | Tool output. | match_only_text |
| gemini_cli.content.inlineData.mimeType | Media type. | keyword |
| gemini_cli.content.text | Text part. | match_only_text |
| gemini_cli.content.thought | True for a thought (reasoning) part. | boolean |
| gemini_cli.human_prompt | True when the record is a prompt typed by a human (event.action user-prompt). | boolean |
| gemini_cli.id | Message ID. A model message is re-appended under the same ID as it grows (tokens, then toolCalls). | keyword |
| gemini_cli.model | Model that produced the response. | keyword |
| gemini_cli.parent_session_id | Subagent chats only. Session ID of the parent session (the `chats/\<parent session\>/` directory). A main session file name ends in the first 8 characters of this ID. | keyword |
| gemini_cli.project | Project directory under ~/.gemini/tmp. A SHA-256 hash of the project root in older releases, a short project name in newer ones. | keyword |
| gemini_cli.secrets.count | Number of distinct secret values found. | long |
| gemini_cli.secrets.errors | Patterns that could not be evaluated. | keyword |
| gemini_cli.secrets.findings.length | Length of the secret value. | long |
| gemini_cli.secrets.findings.type | Secret type (password, github_token, google_api_key, and so on). | keyword |
| gemini_cli.secrets.redacted | True when values were replaced with `[REDACTED:\<type\>]`. | boolean |
| gemini_cli.secrets.types | Distinct secret types found. | keyword |
| gemini_cli.session_kind | main or subagent, from the file location. | keyword |
| gemini_cli.thoughts.description | Thought summary. | match_only_text |
| gemini_cli.thoughts.subject | Thought subject. | match_only_text |
| gemini_cli.thoughts.timestamp | When the thought was recorded. | date |
| gemini_cli.tokens.cached | Cached prompt tokens (included in input). | long |
| gemini_cli.tokens.input | Prompt tokens, including cached tokens. | long |
| gemini_cli.tokens.output | Response tokens, excluding thoughts. | long |
| gemini_cli.tokens.thoughts | Thinking tokens. | long |
| gemini_cli.tokens.tool | Tool-use prompt tokens. | long |
| gemini_cli.tokens.total | Total tokens. | long |
| gemini_cli.toolCalls.args | Tool arguments. | flattened |
| gemini_cli.toolCalls.description | Tool call description. | match_only_text |
| gemini_cli.toolCalls.displayName | Tool display name. | keyword |
| gemini_cli.toolCalls.id | Tool call ID. | keyword |
| gemini_cli.toolCalls.name | Tool name. | keyword |
| gemini_cli.toolCalls.renderOutputAsMarkdown | Whether the CLI renders the output as Markdown. | boolean |
| gemini_cli.toolCalls.status | Tool call status (success, error, cancelled). | keyword |
| gemini_cli.toolCalls.timestamp | When the tool call completed. | date |
| gemini_cli.tool_input.command | Shell commands. Commands over 8000 characters are split into overlapping chunks. | wildcard |
| gemini_cli.tool_input.description | Tool call descriptions. | match_only_text |
| gemini_cli.tool_input.file_path | Files and directories (file_path, absolute_path, path, dir_path, paths). | keyword |
| gemini_cli.tool_input.query | Search queries and glob or grep patterns. | keyword |
| gemini_cli.tool_input.url | URLs. | keyword |
| gemini_cli.tool_names | Names of the tools called in this record. | keyword |
| gemini_cli.type | Record type (user or gemini). | keyword |
| gen_ai.conversation.id |  | keyword |
| gen_ai.operation.name |  | keyword |
| gen_ai.provider.name |  | keyword |
| gen_ai.request.model |  | keyword |
| gen_ai.response.finish_reasons |  | keyword |
| gen_ai.response.id |  | keyword |
| gen_ai.response.model |  | keyword |
| gen_ai.system |  | keyword |
| gen_ai.tool.call.id |  | keyword |
| gen_ai.tool.name |  | keyword |
| gen_ai.usage.cache_read.input_tokens |  | long |
| gen_ai.usage.input_tokens |  | long |
| gen_ai.usage.output_tokens |  | long |

