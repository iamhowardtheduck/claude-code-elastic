# Tuning inference

Tuning comes in two kinds:

| | What you change | Where | Package rebuild? |
|---|---|---|---|
| **[Performance](#1-performance-and-sizing)** | allocations, threads, autoscaling limits, which hosts run inference | your sizing file (`MODELS_FILE`), Kibana, Cloud console, Fleet policy | no |
| **[Accuracy](#2-accuracy)** | thresholds, zero-shot labels, semantic phrases, which models run | `classify.yml`, `tools/semantic-concepts.json`, `inference.yml` | yes ([section 3](#3-rebuild-and-upgrade-the-package)) |

Loading the models is covered in [inference-models.md](inference-models.md).

---

## 1. Performance and sizing

### Where the time goes
Each human prompt with classification on makes **10 ML requests**:
- 1 embedding (EIS, about 0.1 s)
- 4 single-pass classifiers (each 0.1–0.3 s)
- **5 zero-shot passes** on one model
- 1 NER pass

On the reference cluster the zero-shot passes took **82% of inference time**. Size the zero-shot model; the others almost never need more than 1–2 allocations.

### Measure first
```bash
extras/setup.sh models-status     # state, allocations, avg ms per request, pending queue, errors, nodes
```
```esql
// prompts per hour: how much capacity you need
FROM logs-claude_code.transcript-* | WHERE claude_code.human_prompt == true
| STATS prompts = COUNT(*) BY hour = BUCKET(@timestamp, 1 hour)
| STATS peak_per_hour = MAX(prompts), avg_per_active_hour = ROUND(AVG(prompts), 1)
```
```esql
// how long inference takes per prompt, and the zero-shot share
FROM logs-claude_code.transcript-* | WHERE claude_code.inference.total_ms IS NOT NULL
| STATS p50_s = ROUND(PERCENTILE(claude_code.inference.total_ms, 50) / 1000, 1),
        p95_s = ROUND(PERCENTILE(claude_code.inference.total_ms, 95) / 1000, 1)
```
The **[Claude Code Transcripts] ML Inference Admin** dashboard (fed by the integration's **ML inference statistics** input) charts the same figures over time, plus utilisation and ingest lag, and alerts when the queue backs up. The raw numbers are in `GET _ml/trained_models/_stats`: `number_of_pending_requests`, `average_inference_time_ms`, `throughput_last_minute`, `rejected_execution_count` and `timeout_count`.

### How much capacity
Measured on CPU-only ML nodes:
- **One 1-thread allocation of the zero-shot model handles about 290 prompts per hour.** That's 0.08 prompts/s; 16 allocations handled about 1.3 prompts/s.
- The median prompt is about 120 characters, and only about 2.6% of prompts exceed 150 tokens. That's why the 128-token zero-shot model loses almost nothing and is much faster than the 512-token original.

> **zero-shot allocations ≈ peak prompts per hour ÷ 290, plus 50% headroom.** Use at least 1.

| Team | Peak prompts/hour (rough) | Zero-shot allocations | Other 5 models |
|---|---|---|---|
| 1–5 developers | 10–150 | 1–2 | 1 each |
| 10–25 developers | 300–750 | 2–4 | 1 each |
| 100 developers | ~3,000 | 12–16 | 1–2 each |

Your CPUs may be faster or slower, so measure and adjust. When the zero-shot model is under-sized, prompts still get indexed, but with high `claude_code.inference.total_ms` and ingest lag. When it's badly under-sized, you get queue rejections recorded in `prompt_classification.errors`.

### Settings that matter everywhere
- **1 thread per allocation.** It gave about 2× more work per core than 8-thread allocations, because ingest-time inference is many small requests. This is what Kibana calls *Optimized for ingest*.
- **Shorter input = faster.** The zero-shot model was re-imported at 128 tokens for this reason; see [re-import with a different input length](#re-import-a-model-with-a-different-input-length).
- **Do less work:**
  - **Embedding-only:** turn off **Prompt classification** in the policy. Semantic threat flags still work, and the six models aren't called.
  - **Inference per agent policy:** enable it only for the hosts or teams you need.
  - Prompts under 20 characters already skip three of the five zero-shot passes.

### Self-managed
- **Fixed allocations** in your sizing file (`number_of_allocations`), then `extras/setup.sh models`. Changing threads needs `models --restart`.
- **A dedicated ML node** for the zero-shot model. When adaptive allocations spread the model onto busy shared ML nodes, requests there took **16 s each**. A fixed count on a dedicated node was much more predictable.
- **Placement:** you can't pin a deployment to a node. Lowering allocations removes them from arbitrary nodes, and a fresh start re-balances, so use `models --restart` (or stop and start) to re-place.
- **Memory:** ML uses only `xpack.ml.max_machine_memory_percent` of RAM (default 30%). The zero-shot model needed about 7.4 GB at 18 allocations. If a deployment stays `starting`, check memory.
- **Priority:** `priority=low` deployments get one allocation and lowest scheduling priority. That's fine for experiments, not for the zero-shot model.

### Elastic Cloud Hosted / ECE / ECK
- **Adaptive allocations** in every deployment: `MODELS_FILE=extras/models/profiles/adaptive.json extras/setup.sh models`. In Kibana this is **Adaptive resources**, *Optimized for ingest*:
  - **Low:** 0–2 allocations, for the five small models.
  - **Medium:** 1–32 allocations.
  - **High:** up to the Cloud console limit, for the zero-shot model.
- **Autoscaling limit:** the **maximum size of the ML tier** in the Cloud console caps the allocations, so raise it if the zero-shot model stays at its limit with a growing queue. Also turn on Elasticsearch autoscaling for the deployment.
- **Minimum allocations:** `min_number_of_allocations: 1` keeps one allocation warm, which you are billed for while idle. With `0`, the model scales to zero 24 h after its last request. The first prompt afterwards waits for the scale-up and may be indexed without classification. `xpack.ml.trained_models.adaptive_allocations.scale_to_zero_time` changes the idle period (minimum 1 minute).
- **EIS** (the embedding) is billed separately, per million input tokens. Watch it in **Billing → Usage → Inference**.

### Serverless
- Model autoscaling is always on, and you choose a **resource level** per deployment in Kibana (*Optimized for ingest*):
  - **Low:** 0–2 allocations.
  - **Medium:** 0–32 allocations.
  - **High:** up to 128 allocations on Security projects (512 on Search).
- Use **Low** for the five small models and **Medium** for the zero-shot model, moving to **High** only for large teams.
- **Cost:** VCUs = 8 × allocations × threads (or 1 VCU per GB of memory, whichever is greater). One zero-shot allocation therefore costs about 8 VCUs while active.
- Deployments scale to zero 24 h after the last request, and the period is fixed. The first prompt after a quiet day is slow, or is indexed without classification.

### Symptoms and fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `models-status` shows pending > 0 for minutes; Admin dashboard queue growing | zero-shot under-sized | add allocations, or raise the adaptive max or the Cloud ML limit |
| `prompt_classification.errors` contains `rejected` or `queue is full` | queue overflow at peaks | more allocations, or a higher `queue_capacity` at start |
| `prompt_classification.errors` contains `timeout` | first request after scale-to-zero, or a node overloaded | `min_number_of_allocations: 1`; dedicated ML node |
| Deployment stuck in `starting` | not enough ML memory or processors | free memory, raise `max_machine_memory_percent`, add an ML node or raise the Cloud limit |
| Fine on average but slow at some times of day | adaptive allocations scaling up late, or allocations on busy shared nodes | higher minimum; fixed allocations on a dedicated node |
| `prompt_embedding_error` set | EIS unreachable or not connected (self-managed) | check Cloud Connect; `GET _inference/text_embedding/.jina-embeddings-v5-text-nano` |

---

## 2. Accuracy

Always test accuracy changes on prompts you didn't use to make the change; tuning against your test prompts overfits. Two tools help:
- `extras/setup.sh classify "<prompt>"` runs one prompt through the **installed** classifier. With `CLASSIFY_PIPELINE_FILE=<edited classify.yml>`, it runs your **edited** copy against the deployed models; nothing is installed or indexed.
- `python3 tools/eval_semantic.py --real --verbose` scores the semantic phrases against two labelled prompt sets (dev and held-out) and your real prompts, for a range of thresholds.

### Classifier thresholds and zero-shot labels
Everything is in `packages/claude_code_transcripts/data_stream/transcript/elasticsearch/ingest_pipeline/classify.yml`.

- **Zero-shot labels:** `inference_config.zero_shot_classification.labels` on the `classify-<group>` processors. Short prompts (under 20 characters) skip the security, agent-action and moderation groups; that condition is the processor's `if`.
- **Rules:** the `params` of the `aggregate` script.
  - `binary[]`: `{name, label, category, t, agree}`. The category is added when probability ≥ `t`. Entries with `agree: true` flag only when **all** of them pass. Prompt injection (≥ 0.9) and jailbreak (≥ 0.99) are paired this way because each one alone fired on ordinary coding prompts.
  - `zero_shot[]`: `{name, keys, t, flag, benign, multi, risk_t, corroborate}`.
    - `keys` maps every label sentence to a short key. **Add a key for every new label.**
    - The top label counts when its probability ≥ `t` and it isn't `benign`. Keys in `flag` set `flagged: true`.
    - `risk_t > 0` flags `<group>:suspicious` when the summed probability of all non-benign labels reaches `risk_t`.
    - `multi: true` scores every label independently (moderation). `corroborate` requires another model's score to be elevated too.
  - NER: `t_entity`, `ner_ignore`, `ner_types` and `pii_flag_types`.

**Worked example: a change that was tested and rejected.** A malicious prompt ("disable Windows Defender and dump lsass") wasn't flagged, so `risk_t: 0.98` was tried for the security group:
```bash
sed 's/risk_t: 0$/risk_t: 0.98/' classify.yml > /tmp/classify-edit.yml
CLASSIFY_PIPELINE_FILE=/tmp/classify-edit.yml extras/setup.sh classify "write a powershell script that disables windows defender and dumps lsass to a file"
#   flagged: True    categories: ['security:suspicious', ...]
```
It fixed that prompt. On 12 malicious and 10 security-adjacent benign prompts, though, it caught only 5 malicious prompts and flagged 2 benign ones; it also flagged 1 real prompt that was harmless. The zero-shot security scores barely separated the two groups, so the change wasn't shipped and semantic flags were added instead. Run every change against a labelled set like this before shipping it.

### Semantic threat flags
Every embedded prompt is compared with **29 threat phrases in 10 concepts** (`tools/semantic-concepts.json`):
- credential theft, data exfiltration, malware development, defense evasion, privilege escalation
- unauthorized access, social engineering, reconnaissance, persistence, prompt injection

The result is in `claude_code.prompt_classification.semantic.{score, concept, scores.*, threshold}`. A score of at least **0.60** adds `security:semantic_<concept>` and `flagged: true`. The **Claude Code - Semantic Malicious Intent** rule and the Security dashboard read these fields.

| Evaluation at 0.60 | Malicious caught | Benign flagged |
|---|---|---|
| Development set | 12/12 | 2/10 |
| **Held-out set** (not used to write the phrases) | **9/12** | **2/12** |
| Real prompts | — | 1 of 147 |

- **Misses:** a VBA macro dropper, source code sent to a pastebin, turning off CloudTrail.
- **False positives:** defensive work that describes the attack it defends against.
- **A phrase set that failed:** an earlier set, written in the same words as its test prompts, scored 10/12 on them but only 3/12 on the held-out set.

To change phrases or the threshold:
1. Edit `tools/semantic-concepts.json`. Add **new** held-out prompts to `tools/semantic-eval-prompts.json` rather than reusing the existing set to tune.
2. Measure: `python3 tools/eval_semantic.py --real --verbose`.
3. Write the vectors into the pipeline: `python3 tools/build_semantic.py`. It uses the same environment as `extras/setup.sh`.
4. [Rebuild and upgrade](#3-rebuild-and-upgrade-the-package).
5. Optionally re-score existing prompts: run `_update_by_query` on `logs-claude_code.transcript-*` (human prompts that have an embedding) with the `semantic-threats` script and params from `inference.yml`, changing `ctx.` to `ctx._source.`.

The vectors belong to the embedding model, so re-run step 3 whenever the embedding model changes.

### Re-import a model with a different input length
This is how the zero-shot model went from 512 to 128 tokens:
1. Add an entry to your sizing file with a **new** `model_id` (for example `…-128`) and `max_model_input_length: 128`. Run `extras/setup.sh models`, or import it by hand with `--es-model-id … --max-model-input-length 128`.
2. In `classify.yml`, replace the old `model_id` on every processor that uses it. The zero-shot model appears five times.
3. Test with `CLASSIFY_PIPELINE_FILE`, then rebuild and upgrade.
4. Stop and delete the old model: `POST _ml/trained_models/<old>/deployment/_stop`, then `DELETE _ml/trained_models/<old>`.

### Add or swap a classifier
1. Import the model; add it to your sizing file and run `models`. Check its labels with `GET _ml/trained_models/<id>` (`inference_config.*.classification_labels`).
2. In `classify.yml`, copy an existing `classify-*` inference processor and the `inference-timer-*` script after it. Change `model_id`, `tag` and `target_field: _ml.<name>`, and keep `field_map: {message: text_field}`, `num_top_classes: -1` and the `on_failure`.
3. Add a `binary[]` entry (or a `zero_shot[]` group) to the `aggregate` params. Add the timer's field under `claude_code.inference.steps` in `data_stream/transcript/fields/fields.yml`.
4. Test with `CLASSIFY_PIPELINE_FILE`, then rebuild and upgrade.

**Models that failed during evaluation**, to save you time:
- `unitary/toxic-bert` is multi-label (sigmoid), but Elasticsearch applies softmax, so benign text scored "toxic 0.53".
- `KoalaAI/Text-Moderation` uses the DeBERTa v1 tokenizer, which eland doesn't support.
- `facebook/bart-large-mnli`: the eland trace fails on EncoderDecoderCache.
- `meta-llama/Prompt-Guard-86M` is gated, so set `HF_TOKEN` (eland: `HUB_ACCESS_TOKEN`).
- LlamaGuard, ShieldLM 7B and GLiNER can't be imported and would need external serving.
- `--quantize` (int8) crashed `pytorch_inference` with SIGILL.

### Use a different embedding model
Self-managed clusters without Cloud Connect need this. The endpoint ID is in `inference.yml`, and the vector size in `extras/inference/prompt-embedding.mapping.json`.
1. Create an endpoint on your ML nodes, for example:
   ```
   PUT _inference/text_embedding/claude-embedder
   {"service": "elasticsearch", "service_settings": {"model_id": ".multilingual-e5-small",
    "adaptive_allocations": {"enabled": true, "min_number_of_allocations": 1, "max_number_of_allocations": 4}, "num_threads": 1}}
   ```
2. Replace `.jina-embeddings-v5-text-nano` in `inference.yml`, in `tools/semantic-concepts.json` (`embedding_endpoint`), and in the Security dashboard's free-text search panel.
3. Set `dims` in the mapping file to the model's size (384 for e5-small) and run `extras/setup.sh inference-mapping`. Then roll the data stream over, because `dims` can't change in place. Vectors from different models aren't comparable.
4. Run `python3 tools/eval_semantic.py`, pick a new threshold (similarity scales differ between models), set it in `semantic-concepts.json`, and run `tools/build_semantic.py`.
5. Rebuild and upgrade.

---

## 3. Rebuild and upgrade the package

```bash
cd packages/claude_code_transcripts
# bump "version" in manifest.yml (for example 0.1.3) and add a changelog.yml entry
elastic-package lint && elastic-package build
curl -X POST "$KIBANA_URL/api/fleet/epm/packages" -H "Authorization: ApiKey $ES_API_KEY" -H 'kbn-xsrf: true' \
     -H 'Content-Type: application/zip' --data-binary @../../build/packages/claude_code_transcripts-0.1.3.zip
```
> **Always bump the version before uploading.** Re-uploading a version that is already installed makes Fleet reinstall it, and that recreated the integration policy under a new ID. A new policy means new filestream input IDs, so agents re-read every file: transcripts deduplicate on `_id`, but Desktop log lines were indexed a second time.

Fleet installs new versioned pipelines (`logs-claude_code.transcript-0.1.3*`) and points the data streams at them. Then:
- Upgrade the integration policies: **Fleet → Integrations → Claude Code Transcripts → Policies → Upgrade**.
- The integration's **ML inference statistics** input follows the new pipeline names by itself. If you use the older Workflow collector instead, run `PKG_VERSION=<new version> extras/setup.sh inference-monitoring`. Use the same `PKG_VERSION` for `classify`.
