# Load-test deck (Claude Code and Gemini CLI)

> Covers Claude Code and Gemini CLI together. `../claude/deck-performance/` covers Claude Code only, and [`deck-performance/` in gemini-cli-elastic](https://github.com/iamhowardtheduck/gemini-cli-elastic/tree/main/deck-performance) covers Gemini CLI only.

A 13-slide [fslides](https://fslides.dev) presentation of two throughput tests. First, the 2026-11-15 Claude Code test: the Claude Code Transcripts integration on a fresh Elastic Cloud Hosted 9.5.6 deployment, driven by `tools/loadgen.py` toward a customer peak of 25,000 prompts an hour (100,000 a day), covering embedding-only ingest, classification on adaptive and fixed allocations, why ML autoscaling did not scale and the inference-cache caveat. Second, the 2026-11-17 head-to-head: Claude Code and Gemini CLI back to back on one self-managed Elasticsearch 9.5.6 cluster with the same generator (`--product claude|gemini`), which measured the same ML cost per prompt for both (zero-shot 83.7% vs 82.7% of classifier time). The ML sizing for the peak follows, applied to the combined prompt rate.

- **Watch it:** https://iamhowardtheduck.github.io/claude-code-elastic/load-test/
- **PDF:** [docs/claude-code-transcripts-load-test.pdf](../docs/claude-code-transcripts-load-test.pdf)

## Edit it

The deck uses the `elastic-web` fslides kit (`style: 'elastic-web'` in `fslides.config.js`; tokens and the isometric engine in `slides/style/`).

```bash
cd deck-performance
fslides serve        # player with live reload
fslides pdf          # re-export, then copy the PDF to docs/claude-code-transcripts-load-test.pdf
```

On Ubuntu 24.04 headless Chrome may refuse to start ("No usable sandbox"); point `PUPPETEER_EXECUTABLE_PATH` at a Chrome you trust.

## Reproduce the numbers

```bash
export CLOUD_ID=... ES_USER=... ES_PASSWORD=...        # or ES_URL + ES_API_KEY
# Claude Code on Elastic Cloud (2026-11-15)
python3 tools/loadgen.py run --no-classify --ramp 1:300,3:300,7:300,10:300 --lines-per-prompt 60   # phase 1
python3 tools/loadgen.py run --ramp 0.5:300,1:300,2:300 --lines-per-prompt 20                       # phase 2 / 3
python3 tools/loadgen.py report --since 60m
python3 tools/loadgen.py cleanup
```

The Cloud test ran with repeating task prompts (about 70% inference-cache hits); `--repeatable-prompts` reproduces that, and the default now generates unique prompts.

```bash
# head-to-head on one cluster (2026-11-17): run for --product claude, then --product gemini
for p in claude gemini; do
  python3 tools/loadgen.py --product $p run --ramp 0.15:240,0.25:240,0.35:240,0.45:240 --lines-per-prompt 20 --timeout 300
  python3 tools/loadgen.py --product $p run --no-classify --ramp 1:180,3:180 --lines-per-prompt 20
done
python3 tools/loadgen.py --product gemini report --since 60m
python3 tools/loadgen.py --product claude cleanup; python3 tools/loadgen.py --product gemini cleanup
```

Wait for the zero-shot queue to drain between runs.
