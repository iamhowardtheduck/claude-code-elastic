# Load-test deck (Claude Code only)

> Claude Code only: a copy of the original `deck-performance/` deck. `../../deck-performance/` covers Claude Code and Gemini CLI together, and [`deck-performance/` in gemini-cli-elastic](https://github.com/iamhowardtheduck/gemini-cli-elastic/tree/main/deck-performance) covers Gemini CLI only.

An 11-slide [fslides](https://fslides.dev) presentation of the 2026-11-15 throughput test: the integration on a fresh Elastic Cloud Hosted 9.5.6 deployment, driven by `tools/loadgen.py` toward a customer peak of 25,000 prompts an hour (100,000 a day). It covers embedding-only ingest, classification on adaptive and fixed allocations, why ML autoscaling did not scale, the inference-cache caveat, and the ML sizing for that peak.

- **Watch it:** https://iamhowardtheduck.github.io/claude-code-elastic/claude/load-test/
- **PDF:** [docs/claude/claude-code-transcripts-load-test.pdf](../../docs/claude/claude-code-transcripts-load-test.pdf)

## Edit it

The deck uses the `elastic-web` fslides kit (`style: 'elastic-web'` in `fslides.config.js`; tokens and the isometric engine in `slides/style/`).

```bash
cd claude/deck-performance
fslides serve        # player with live reload
fslides pdf          # re-export, then copy the PDF to docs/claude/claude-code-transcripts-load-test.pdf
```

On Ubuntu 24.04 headless Chrome may refuse to start ("No usable sandbox"); point `PUPPETEER_EXECUTABLE_PATH` at a Chrome you trust.

## Reproduce the numbers

```bash
export CLOUD_ID=... ES_USER=... ES_PASSWORD=...        # or ES_URL + ES_API_KEY
python3 tools/loadgen.py run --no-classify --ramp 1:300,3:300,7:300,10:300 --lines-per-prompt 60   # phase 1
python3 tools/loadgen.py run --ramp 0.5:300,1:300,2:300 --lines-per-prompt 20                       # phase 2 / 3
python3 tools/loadgen.py report --since 60m
python3 tools/loadgen.py cleanup
```

The test ran with repeating task prompts (about 70% inference-cache hits); `--repeatable-prompts` reproduces that, and the default now generates unique prompts.
