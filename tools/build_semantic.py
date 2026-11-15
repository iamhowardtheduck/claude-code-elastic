#!/usr/bin/env python3
"""Embed the threat concepts in tools/semantic-concepts.json and write them into the transcript
inference pipeline (processor tag 'semantic-threats'). Re-run after editing the phrases or changing
the embedding model, then bump the package version and rebuild.

Needs the same environment as extras/setup.sh (ES_URL, ES_API_KEY or ES_USER/ES_PASSWORD, CA_CERT)
and PyYAML. Usage: python3 tools/build_semantic.py
"""
import json, math, os, sys
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "extras"))
import setup  # noqa: E402  (HTTP helpers and auth)

PIPE = os.path.join(ROOT, "packages/claude_code_transcripts/data_stream/transcript/elasticsearch/ingest_pipeline/inference.yml")
TAG = "semantic-threats"

SOURCE = r"""
// Cosine similarity of the prompt embedding to the threat concepts (unit vectors in params).
def raw = ctx.claude_code?.prompt_embedding;
if (raw == null) { return; }
List v;
if (raw instanceof List) { v = raw; } else { v = new ArrayList(); for (def x : raw) { v.add(x); } }   // inference output may be a primitive array
if (v.isEmpty()) { return; }
double n = 0;
for (def x : v) { double d = ((Number) x).doubleValue(); n += d * d; }
if (n == 0) { return; }
n = Math.sqrt(n);
double best = -1; String bestConcept = null; Map per = new HashMap();
for (def c : params.concepts) {
  double cb = -1;
  for (def u : c.vectors) {
    double s = 0;
    int len = u.size() < v.size() ? u.size() : v.size();
    for (int i = 0; i < len; i++) { s += ((Number) v.get(i)).doubleValue() * ((Number) u.get(i)).doubleValue(); }
    s = s / n;
    if (s > cb) { cb = s; }
  }
  per[c.name] = Math.round(cb * 1000) / 1000.0;
  if (cb > best) { best = cb; bestConcept = c.name; }
}
def pc = ctx.claude_code.prompt_classification;
if (pc == null) { pc = new HashMap(); ctx.claude_code.prompt_classification = pc; }
Map sem = new HashMap();
sem.score = Math.round(best * 1000) / 1000.0;
sem.concept = bestConcept;
sem.scores = per;
sem.threshold = params.threshold;
pc.semantic = sem;
if (best >= params.threshold) {
  if (pc.categories == null) { pc.categories = new ArrayList(); }
  String cat = 'security:semantic_' + bestConcept;
  if (!pc.categories.contains(cat)) { pc.categories.add(cat); }
  pc.flagged = true;
}
"""

def main():
    cfg = json.load(open(os.path.join(HERE, "semantic-concepts.json")))
    names, phrases = [], []
    for c, ps in cfg["concepts"].items():
        for p in ps:
            names.append(c); phrases.append(p)
    vecs = []
    for i in range(0, len(phrases), 16):
        code, body = setup.es("POST", f"/_inference/text_embedding/{cfg['embedding_endpoint']}", {"input": phrases[i:i + 16]})
        if code >= 300:
            sys.exit(f"embedding failed ({code}): {json.dumps(body)[:300]}")
        vecs += [e["embedding"] for e in body["text_embedding"]]
    concepts = {}
    for name, v in zip(names, vecs):
        norm = math.sqrt(sum(x * x for x in v))
        concepts.setdefault(name, []).append([round(x / norm, 5) for x in v])
    proc = {"script": {
        "tag": TAG, "lang": "painless",
        "description": f"Semantic threat flags: best cosine similarity of the prompt embedding to {len(phrases)} threat phrases "
                       f"in {len(concepts)} concepts (tools/semantic-concepts.json); >= threshold adds security:semantic_<concept> and flagged",
        "if": "ctx.claude_code?.prompt_embedding != null",
        "source": SOURCE,
        "params": {"threshold": cfg["threshold"], "concepts": [{"name": k, "vectors": v} for k, v in concepts.items()]},
        "on_failure": [{"append": {"field": "claude_code.prompt_classification.errors", "value": "semantic: {{{_ingest.on_failure_message}}}"}}],
    }}
    text = open(PIPE).read()
    p = yaml.safe_load(text)
    procs = [x for x in p["processors"] if list(x.values())[0].get("tag") != TAG]
    at = next(i for i, x in enumerate(procs) if list(x.values())[0].get("tag") == "inference-timer-finish")
    procs.insert(at, proc)
    p["processors"] = procs

    class D(yaml.SafeDumper):
        pass
    def s(d, v):
        if "\n" in v:
            return d.represent_scalar("tag:yaml.org,2002:str", "\n".join(l.rstrip() for l in v.strip("\n").split("\n")) + "\n", style="|")
        return d.represent_scalar("tag:yaml.org,2002:str", v)
    D.add_representer(str, s)
    def flow_vectors(d, v):   # keep each vector on one line
        return d.represent_sequence("tag:yaml.org,2002:seq", v, flow_style=all(isinstance(x, float) for x in v) and len(v) > 16)
    D.add_representer(list, flow_vectors)
    with open(PIPE, "w") as f:
        f.write("---\n")
        yaml.dump(p, f, Dumper=D, sort_keys=False, width=100000, allow_unicode=True)
    print(f"wrote {len(phrases)} phrase vectors ({len(concepts)} concepts, dims {len(vecs[0])}, threshold {cfg['threshold']}) into {os.path.relpath(PIPE, ROOT)}")

if __name__ == "__main__":
    main()
