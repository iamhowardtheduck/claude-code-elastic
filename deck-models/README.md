# Models deck (Claude Code and Gemini CLI)

> Covers both integrations. `../claude/deck-models/` covers Claude Code only, and [`deck-models/` in gemini-cli-elastic](https://github.com/iamhowardtheduck/gemini-cli-elastic/tree/main/deck-models) covers Gemini CLI only.

The seven ML models behind the redaction and classification pipelines, one slide each, in the elastic-web kit. One set of deployments serves both Claude Code Transcripts and Gemini CLI Transcripts:

- **Slides:** https://iamhowardtheduck.github.io/claude-code-elastic/models/
- **PDF:** [docs/claude-code-transcripts-models.pdf](../docs/claude-code-transcripts-models.pdf)

1. **Cover** and **where the models sit**: which policy switch turns on which model (the same two switches on both integrations).
2. **One model set, two integrations**: both pipelines call the same deployments and write `claude_code.*` or `gemini_cli.*`; the only wording differences are the zero-shot interaction label ("a question about Claude itself" / "Gemini itself") and the NER ignore list; sizing must cover prompts from both.
3. **One slide per model**: embedding (`.jina-embeddings-v5-text-nano`), prompt injection, jailbreak, toxicity, offensive, zero-shot and NER. Each gives the model ID, source, labels, threshold, output fields, ML memory and an example inference call.
4. **Loading the models** once with Eland or `extras/setup.sh models`, plus the embedding mapping for each integration (`extras/setup.sh inference-mapping`, `extras/setup.sh inference-mapping` in gemini-cli-elastic).

```bash
cd deck-models
npx fslides serve    # http://localhost:30004
npx fslides pdf      # re-export, then copy the PDF to docs/claude-code-transcripts-models.pdf
```
