# Full deck (Claude Code only)

> Claude Code only: a copy of the original `deck-full/` deck. `../../deck-full/` covers Claude Code and Gemini CLI together, and `../../gemini/deck-full/` covers Gemini CLI only.

The overview, inference and load-test decks in one 32-slide [fslides](https://fslides.dev) presentation, all in the elastic-web kit:

1. **Overview** (`o*`): the `deck/` slides, re-drawn for this deck. `deck/` now uses elastic-web too, but its slides are a separate copy and are not synced here.
2. **Inference and redaction** (`i*`): copied from `deck-inference/`, in place of the overview's redaction and ML slides.
3. **Overview, continued:** dashboards, detections, why it works, what it solves.
4. **Load test** (`p*`): copied from `deck-performance/`.
5. **Get started.**

The overview slides are edited here. The `i*` and `p*` slides are copies: edit them in their own deck, then run `./sync.sh`.

```bash
cd claude/deck-full
./sync.sh            # refresh the inference and load-test copies
npx fslides serve    # http://localhost:30003
npx fslides pdf
```
