# Inference and redaction deck (Claude Code only)

> Claude Code only: a copy of the original `deck-inference/` deck. `../../deck-inference/` covers Claude Code and Gemini CLI together, and [`deck-inference/` in gemini-cli-elastic](https://github.com/iamhowardtheduck/gemini-cli-elastic/tree/main/deck-inference) covers Gemini CLI only.

A 12-slide [fslides](https://github.com/fslides/fslides) deck, in the elastic-web kit, on everything the integration's ingest pipelines do to a prompt before it is stored. It covers secret redaction (19 detector types), the EIS embedding, semantic threat flags, the five single-pass classifiers, the five zero-shot passes, the classified document and where the inference time goes.

## Edit it

```bash
cd claude/deck-inference
npm install
npx fslides serve    # http://localhost:30002
npx fslides pdf
```

Sources: `packages/claude_code_transcripts/data_stream/transcript/elasticsearch/ingest_pipeline/` (`default.yml`, `inference.yml`, `classify.yml`), `docs/inference-models.md` and `docs/inference-tuning.md`. Example prompts and documents are synthetic, from `tools/loadgen.py` on the Elastic Cloud test deployment.
