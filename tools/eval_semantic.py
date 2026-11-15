#!/usr/bin/env python3
"""Evaluate tools/semantic-concepts.json: embeds the phrases and the labelled prompts in
tools/semantic-eval-prompts.json and, with --real, the stored embeddings of real prompts, then
prints catches and false positives per threshold. Same environment as extras/setup.sh.
Usage: python3 tools/eval_semantic.py [--real] [--verbose]"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "extras"))
import setup  # noqa: E402

def embed(endpoint, xs):
    out = []
    for i in range(0, len(xs), 16):
        code, body = setup.es("POST", f"/_inference/text_embedding/{endpoint}", {"input": xs[i:i + 16]})
        if code >= 300: sys.exit(f"embedding failed ({code}): {json.dumps(body)[:300]}")
        out += [e["embedding"] for e in body["text_embedding"]]
    return out
unit = lambda v: (lambda n: [x / n for x in v])(math.sqrt(sum(x * x for x in v)))

def main():
    cfg = json.load(open(os.path.join(HERE, "semantic-concepts.json")))
    sets = json.load(open(os.path.join(HERE, "semantic-eval-prompts.json")))
    phr = [(c, p) for c, ps in cfg["concepts"].items() for p in ps]
    P = [unit(v) for v in embed(cfg["embedding_endpoint"], [p for _, p in phr])]
    best = lambda v: max((sum(a * b for a, b in zip(v, e)), c) for (c, _), e in zip(phr, P))
    scored = {}
    for name in ("dev", "heldout"):
        items = [(1, t) for t in sets[name]["malicious"]] + [(0, t) for t in sets[name]["benign"]]
        scored[name] = [(y, t, best(unit(v))) for (y, t), v in zip(items, embed(cfg["embedding_endpoint"], [t for _, t in items]))]
    real = []
    if "--real" in sys.argv:
        code, r = setup.es("POST", "/logs-claude_code.transcript-*/_search", {"size": 5000, "_source": ["message"], "fields": ["claude_code.prompt_embedding"],
            "query": {"bool": {"filter": [{"term": {"claude_code.human_prompt": True}}, {"exists": {"field": "claude_code.prompt_embedding"}}]}}})
        real = [(best(unit(h["fields"]["claude_code.prompt_embedding"])), h["_source"].get("message", "")[:80]) for h in r["hits"]["hits"] if h.get("fields")]
    print(f"{len(phr)} phrases, {len(cfg['concepts'])} concepts, configured threshold {cfg['threshold']}")
    for th in (0.50, 0.55, 0.58, 0.60, 0.62, 0.65):
        row = [f"{n}: {sum(1 for y, _, b in s if y and b[0] >= th)}/{sum(1 for y, _, _ in s if y)} malicious, "
               f"{sum(1 for y, _, b in s if not y and b[0] >= th)}/{sum(1 for y, _, _ in s if not y)} benign" for n, s in scored.items()]
        if real: row.append(f"real: {sum(1 for b, _ in real if b[0] >= th)}/{len(real)}")
        print(f"  t={th:.2f}  " + " | ".join(row))
    if "--verbose" in sys.argv:
        for n, s in scored.items():
            print(f"== {n}")
            for y, t, b in sorted(s, key=lambda x: -x[2][0]): print(f"  {'MAL' if y else 'ben'} {b[0]:.3f} {b[1]:20} {t[:70]}")
        for b, t in sorted(real, reverse=True)[:10]: print(f"  real {b[0]:.3f} {b[1]:20} {t}")

if __name__ == "__main__":
    main()
