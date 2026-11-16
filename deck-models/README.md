# Models deck

The seven ML models behind the redaction and classification pipeline, one slide each, in the elastic-web kit:

- **PDF:** [docs/claude-code-transcripts-models.pdf](../docs/claude-code-transcripts-models.pdf)

1. **Cover** and **where the models sit**: which policy switch turns on which model.
2. **One slide per model**: embedding (`.jina-embeddings-v5-text-nano`), prompt injection, jailbreak, toxicity, offensive, zero-shot and NER. Each gives the model ID, source, labels, threshold, output fields, ML memory and an example inference call.
3. **Loading the models** with Eland or `extras/setup.sh models`.

```bash
cd deck-models
npx fslides serve    # http://localhost:30004
npx fslides pdf      # re-export, then copy the PDF to docs/claude-code-transcripts-models.pdf
```
