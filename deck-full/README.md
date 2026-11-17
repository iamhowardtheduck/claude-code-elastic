# Full deck (Claude Code and Gemini CLI)

The overview, inference and load-test decks in one 36-slide [fslides](https://fslides.dev) presentation, in the elastic-web kit, covering both integrations:

1. **Overview** (`o*`, from `deck/`): cover, problem, how it works, data streams, every line structured, shared and different.
2. **Inference and redaction** (`i*`, from `deck-inference/`, without its closing slide), in place of the overview's redaction and ML slides.
3. **Overview, continued:** dashboards, detection rules, why it works, what it solves.
4. **Load test** (`p*`, from `deck-performance/`): the Claude Code test on Elastic Cloud and the Claude Code vs Gemini CLI head-to-head.
5. **Get started.**

- **Watch it:** https://iamhowardtheduck.github.io/claude-code-elastic/full/
- **PDF:** [docs/claude-code-transcripts-full.pdf](../docs/claude-code-transcripts-full.pdf)

The same deck exists for Claude Code only (`../claude/deck-full/`) and Gemini CLI only ([`deck-full/` in gemini-cli-elastic](https://github.com/iamhowardtheduck/gemini-cli-elastic/tree/main/deck-full)).

## Edit it

Edit the source decks, not the copies here, then re-sync and re-export:

```bash
cd deck-full
./sync.sh            # copy o*/i*/p* from deck/, deck-inference/ and deck-performance/; drops slides the config does not use
fslides serve        # player with live reload (port 30003)
fslides pdf          # re-export, then copy the PDF to docs/claude-code-transcripts-full.pdf
```

The slide order is in `fslides.config.js`. On Ubuntu 24.04 headless Chrome may refuse to start ("No usable sandbox"); point `PUPPETEER_EXECUTABLE_PATH` at a Chrome you trust.
