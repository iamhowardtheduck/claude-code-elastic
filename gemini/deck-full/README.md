# Full deck (Gemini CLI only)

> Gemini CLI only. `../../deck-full/` covers Claude Code and Gemini CLI together, and `../../claude/deck-full/` covers Claude Code only.

The Gemini CLI overview, inference and load-test decks in one 31-slide [fslides](https://fslides.dev) presentation, in the elastic-web kit:

1. **Overview** (`o*`, from `../deck/`): cover, problem, how it works, data stream, every record structured.
2. **Inference and redaction** (`i*`, from `../deck-inference/`, without its closing slide).
3. **Overview, continued:** dashboards, detection rules, why it works, what it solves.
4. **Load test** (`p*`, from `../deck-performance/`): Gemini CLI vs Claude Code on the same self-managed cluster.
5. **Get started.**

- **Watch it:** https://iamhowardtheduck.github.io/claude-code-elastic/gemini/full/
- **PDF:** [docs/gemini/gemini-cli-transcripts-full.pdf](../../docs/gemini/gemini-cli-transcripts-full.pdf)

## Edit it

Edit the source decks in `gemini/`, then re-sync and re-export:

```bash
cd gemini/deck-full
./sync.sh            # copy o*/i*/p* from ../deck/, ../deck-inference/ and ../deck-performance/
fslides serve        # player with live reload (port 30023)
fslides pdf          # re-export, then copy the PDF to docs/gemini/gemini-cli-transcripts-full.pdf
```
