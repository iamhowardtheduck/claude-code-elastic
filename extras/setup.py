#!/usr/bin/env python3
"""Optional setup for the Claude Code integration (things an integration package cannot install).

Usage: extras/setup.sh <command> [<command> ...]
  pricing               create/refresh the claude-model-pricing lookup index (spend panels)
  inference-mapping     add the claude_code.prompt_embedding dense_vector mapping (needed before enabling inference)
  rules                 import the detection rules (disabled; enable them in Security > Rules)
  inference-monitoring  stats collector (ILM, template, pipeline, workflow), admin dashboard, alert rules (disabled)
  all                   all of the above

Environment:
  ES_URL, KIBANA_URL           e.g. https://es.example:9200, https://kibana.example:5601
  ES_API_KEY                   base64 API key (preferred), or ES_USER + ES_PASSWORD
  CA_CERT                      optional path to a CA bundle; INSECURE=true skips TLS verification (testing only)
  PKG_VERSION                  installed claude_code package version (default 0.1.0; used for pipeline names)
"""
import base64, json, os, ssl, sys, uuid, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ES, KB = os.environ.get("ES_URL", "").rstrip("/"), os.environ.get("KIBANA_URL", "").rstrip("/")
PKG_VERSION = os.environ.get("PKG_VERSION", "0.1.0")

def _auth():
    if os.environ.get("ES_API_KEY"):
        return "ApiKey " + os.environ["ES_API_KEY"]
    if os.environ.get("ES_USER") and os.environ.get("ES_PASSWORD"):
        return "Basic " + base64.b64encode(f"{os.environ['ES_USER']}:{os.environ['ES_PASSWORD']}".encode()).decode()
    sys.exit("Set ES_API_KEY, or ES_USER and ES_PASSWORD")

def _ctx():
    if os.environ.get("INSECURE") == "true":
        c = ssl.create_default_context(); c.check_hostname = False; c.verify_mode = ssl.CERT_NONE; return c
    return ssl.create_default_context(cafile=os.environ.get("CA_CERT") or None)

def call(base, method, path, body=None, ctype="application/json", ok=(200, 201)):
    if not base:
        sys.exit("ES_URL / KIBANA_URL not set")
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    h = {"Authorization": _auth(), "Content-Type": ctype, "kbn-xsrf": "true"}
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, context=_ctx()) as r:
            txt = r.read().decode(); return r.status, (json.loads(txt) if txt.strip().startswith(("{", "[")) else txt)
    except urllib.error.HTTPError as e:
        txt = e.read().decode()
        if e.code in ok:
            return e.code, txt
        return e.code, (json.loads(txt) if txt.strip().startswith("{") else txt)

def es(m, p, b=None, **k): return call(ES, m, p, b, **k)
def kb(m, p, b=None, **k): return call(KB, m, p, b, **k)
def load(*p): return json.load(open(os.path.join(HERE, *p)))
def report(what, res):
    code, body = res
    print(f"  {'ok ' if code < 300 else 'ERR'} {what} ({code})" + ("" if code < 300 else f": {json.dumps(body)[:300]}"))

def merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict): merge(a[k], v)
        else: a[k] = v
    return a

def pricing():
    print("pricing")
    code, _ = es("HEAD", "/claude-model-pricing", ok=(200, 404))
    if code == 404:
        report("create lookup index claude-model-pricing", es("PUT", "/claude-model-pricing", load("pricing", "claude-model-pricing.index.json")))
    nd = open(os.path.join(HERE, "pricing", "claude-model-pricing.ndjson"), "rb").read()
    code, body = es("POST", "/claude-model-pricing/_bulk?refresh=true", nd, ctype="application/x-ndjson")
    report(f"load {sum(1 for l in nd.splitlines() if b'_id' in l)} model prices" + (" (with item errors)" if isinstance(body, dict) and body.get("errors") else ""), (code, body))

def inference_mapping():
    print("inference-mapping")
    add = load("inference", "prompt-embedding.mapping.json")
    name = "logs-claude_code.transcript@custom"
    code, body = es("GET", f"/_component_template/{name}", ok=(200, 404))
    tpl = {"template": {"mappings": {}}}
    if code == 200:
        tpl = body["component_templates"][0]["component_template"]
        for k in ("created_date_millis", "modified_date_millis", "created_date", "modified_date"): tpl.pop(k, None)
    merge(tpl.setdefault("template", {}).setdefault("mappings", {}), add)
    report(f"component template {name}", es("PUT", f"/_component_template/{name}", tpl))
    code, body = es("PUT", "/logs-claude_code.transcript-*/_mapping", add, ok=(200, 404))
    report("existing transcript data streams", (code if code != 404 else 200, body))

def rules():
    print("rules")
    path = os.path.join(HERE, "detection-rules", "claude-code-rules.ndjson")
    b = "----claude" + uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"rules.ndjson\"\r\nContent-Type: application/x-ndjson\r\n\r\n").encode() \
        + open(path, "rb").read() + f"\r\n--{b}--\r\n".encode()
    code, res = kb("POST", "/api/detection_engine/rules/_import?overwrite=true", body, ctype=f"multipart/form-data; boundary={b}")
    report(f"import detection rules: {res.get('success_count') if isinstance(res, dict) else '?'} imported, errors {res.get('errors') if isinstance(res, dict) else res}", (code, res))

def inference_monitoring():
    print("inference-monitoring")
    D = "inference-monitoring"
    report("ILM policy ml-inference-stats", es("PUT", "/_ilm/policy/ml-inference-stats", load(D, "stats-ilm.json")))
    report("ingest pipeline ml-inference-stats", es("PUT", "/_ingest/pipeline/ml-inference-stats", load(D, "stats-pipeline.json")))
    report("index template ml-inference-stats", es("PUT", "/_index_template/ml-inference-stats", load(D, "stats-template.json")))
    pipes = f"logs-claude_code.transcript-{PKG_VERSION},logs-claude_code.transcript-{PKG_VERSION}-classify"
    y = open(os.path.join(HERE, D, "collector.yaml")).read().replace("__PIPELINES__", pipes)
    wid = "ml-inference-stats-collector"
    code, body = kb("PUT", f"/api/workflows/workflow/{wid}", {"yaml": y}, ok=(200, 404))
    if code == 404:
        code, body = kb("POST", "/api/workflows", {"workflows": [{"id": wid, "yaml": y}]})
    report(f"workflow {wid} (collects stats every minute)", (code, body))
    nd = open(os.path.join(HERE, D, "ml-inference-admin.ndjson"), "rb").read()
    b = "----claude" + uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"dash.ndjson\"\r\nContent-Type: application/x-ndjson\r\n\r\n").encode() + nd + f"\r\n--{b}--\r\n".encode()
    report("dashboard [ML Inference] Admin", kb("POST", "/api/saved_objects/_import?overwrite=true", body, ctype=f"multipart/form-data; boundary={b}"))
    for r in load(D, "alert-rules.json"):
        rid = r.pop("id"); r["enabled"] = False
        code, res = kb("POST", f"/api/alerting/rule/{rid}", r, ok=(200, 409))
        if code == 409:
            upd = {k: r[k] for k in ("name", "schedule", "tags", "actions", "params")}
            code, res = kb("PUT", f"/api/alerting/rule/{rid}", upd)
        report(f"alert rule {rid} (disabled; add a connector action, then enable)", (code, res))

CMDS = {"pricing": pricing, "inference-mapping": inference_mapping, "rules": rules, "inference-monitoring": inference_monitoring}
if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or any(a not in CMDS and a != "all" for a in args):
        sys.exit(__doc__)
    for a in (list(CMDS) if "all" in args else args):
        CMDS[a]()
