# Overview deck

A 12-slide [fslides](https://github.com/fslides/fslides) presentation on this integration: what it collects, why it's built the way it is, and what it solves for security, leadership and compliance teams.

- **Watch it:** https://iamhowardtheduck.github.io/claude-code-elastic/
- **PDF:** [docs/claude-code-transcripts-deck.pdf](../docs/claude-code-transcripts-deck.pdf)

## Edit it

```bash
cd deck
npm install
npm run serve        # full player with live reload
npm run pdf          # re-export, then copy the PDF to docs/claude-code-transcripts-deck.pdf
```

Every slide is an HTML file in `slides/`; order and labels live in `fslides.config.js`. Pushes to `main` that touch `deck/` or the PDF redeploy GitHub Pages.
