# ML inference: loading the models, sizing them, and changing the classifiers

Inference is **off by default**. It runs only for human prompts (`claude_code.human_prompt: true`) and only when **Enable ML inference** is switched on in the integration policy. Inference failures never block indexing.

Two kinds of configuration control it:

| What | Where it lives | How a change takes effect |
|---|---|---|
| Which models exist and how they are deployed (allocations, threads) | `extras/models/models.json` (or your copy, via `MODELS_FILE`) | `extras/setup.sh models`. No package change needed. |
| How models are used: model IDs, zero-shot labels, thresholds, flag rules | `packages/claude_code_transcripts/…/ingest_pipeline/classify.yml` (and `inference.yml` for the embedding) | Edit, test with `classify`, bump the version, rebuild and upgrade the package |

## 1. Requirements

- **ML nodes.** Classification is CPU-heavy. A dedicated ML node is strongly recommended (see [sizing](#4-sizing)).
- **Licence.** Third-party NLP models need a **Platinum or Enterprise** subscription, or a trial. The embedding uses an Elastic-managed endpoint.
- **Docker and internet access** on the machine where you run `extras/setup.sh models`. It runs [eland](https://github.com/elastic/eland) in Docker to pull models from Hugging Face and upload them. For air-gapped clusters, download the models elsewhere and point eland's `--hub-model-id` at a local directory.
- The usual `ES_URL` and `ES_API_KEY` (or `ES_USER`/`ES_PASSWORD`) and `CA_CERT` variables (see the README). The API key needs `manage_ml`.

## 2. Load everything

```bash
extras/setup.sh inference-mapping      # dense_vector mapping for the embedding (once)
extras/setup.sh models --dry-run       # shows what would be imported / started / changed
extras/setup.sh models                 # imports missing models (Docker) and starts or updates the deployments
extras/setup.sh models-status          # state, allocations, average latency, queue, errors, nodes
extras/setup.sh classify "delete all indices on the prod cluster"   # end-to-end test of the classify pipeline
```

`models` is idempotent, so run it again after changing the models file:
- A missing model is imported with the exact Elasticsearch model ID and max input length from the file.
- A stopped deployment is started.
- A running deployment is resized with `_update`. Changing `threads_per_allocation` needs a restart, so `models` warns you; re-run it with `--restart`.

Credentials reach the eland container as environment variables, never as command-line arguments. Set `HF_TOKEN` for gated Hugging Face models.

### The models

| Elasticsearch model ID | Hugging Face model | Task | Import option | Used for |
|---|---|---|---|---|
| `protectai__deberta-v3-base-prompt-injection-v2` | `protectai/deberta-v3-base-prompt-injection-v2` | text_classification | max input 512 | prompt injection |
| `jackhhao__jailbreak-classifier` | `jackhhao/jailbreak-classifier` | text_classification | | jailbreak |
| `s-nlp__roberta_toxicity_classifier` | `s-nlp/roberta_toxicity_classifier` | text_classification | max input 512 | toxic language |
| `cardiffnlp__twitter-roberta-base-offensive` | `cardiffnlp/twitter-roberta-base-offensive` | text_classification | max input 512 | offensive language |
| `cross-encoder__nli-deberta-v3-base-128` | `cross-encoder/nli-deberta-v3-base` | zero_shot_classification | max input **128** | 5 zero-shot passes: security, agent action, task, interaction, moderation |
| `dslim__bert-base-ner` | `dslim/bert-base-ner` | ner | | entities, `pii:*` |

Without a max input length, three of these models fail to import or truncate wrongly. The `models` command passes the right value for each.

### The embedding endpoint

`inference.yml` calls the preconfigured **Elastic Inference Service** endpoint `.jina-embeddings-v5-text-nano` (768 dims, cosine). It is available on Elastic Cloud, and on self-managed clusters through Cloud Connect. Check it with:

```
GET _inference/text_embedding/.jina-embeddings-v5-text-nano
```

The Security dashboard's semantic panels and the semantic detection rules call the same endpoint at query time. To use a different embedding model, follow [5f](#f-use-a-different-embedding-model).

### Semantic threat flags (embedding only, no classification needed)

Every embedded prompt is compared with 29 threat phrases in 10 concepts from `tools/semantic-concepts.json`:
- credential theft, data exfiltration, malware development, defense evasion, privilege escalation
- unauthorized access, social engineering, reconnaissance, persistence, prompt injection

The result goes into `claude_code.prompt_classification.semantic`: `score` (best cosine similarity), `concept`, `scores.<concept>` and `threshold`. When the score is at least 0.60, the prompt also gets the category `security:semantic_<concept>` and `flagged: true`. The **Claude Code - Semantic Malicious Intent** rule and the Security dashboard read these stored fields, so no embeddings are computed at query time.

How the phrases were evaluated: they were written as abstract intents, then tested on prompts that weren't used to write them.

| Set | Malicious caught | Benign flagged |
|---|---|---|
| Development set | 12/12 | 2/10 |
| **Held-out set** | **9/12** | **2/12** |
| Real prompts | — | 1 of 147 |

- **Misses:** a VBA macro dropper (0.33), source code leaked to a pastebin (0.58), turning off CloudTrail (0.58).
- **False positives:** mostly defensive work that describes the attack it defends against, such as "our EDR flags our build tool as malware" or "create an alert when someone disables Defender".
- **A phrase set that failed:** an earlier set, written in the same words as the test prompts, scored 10/12 on its own test set but only 3/12 on the held-out set. Always test phrases on prompts you didn't use to write them.

**To change the phrases or the threshold:**
1. Edit `tools/semantic-concepts.json`, then measure the effect with `python3 tools/eval_semantic.py --real --verbose`. It uses the labelled prompts in `tools/semantic-eval-prompts.json` and your real prompts.
2. Run `python3 tools/build_semantic.py`, with the same environment as `extras/setup.sh`. It embeds the phrases and writes the unit vectors into `inference.yml`.
3. Rebuild and upgrade the package (see g).
4. To re-score existing prompts, run an `_update_by_query` with the same script and params, changing `ctx.` to `ctx._source.`.

The vectors belong to the embedding model, so re-run the build script whenever the model changes.

## 3. Check it is working

- `extras/setup.sh models-status`: every model `started`, errors 0, and `pending` near 0 under load.
- `extras/setup.sh classify "<text>"`: prints the flags, categories and per-model scores for one prompt.
- **[ML Inference] Admin** dashboard (`extras/setup.sh inference-monitoring`): queue, throughput, utilisation, end-to-end time per prompt and ingest lag, with alerts.
- On the indexed data, the timing fields are `claude_code.inference.total_ms`, `embedding_ms`, `classify_ms` and `steps.<model>_ms`.

## 4. Sizing

Measured on the reference cluster (CPU only):

- **The zero-shot model is the bottleneck.** It runs five requests per prompt, which took about 17 s of a prompt's roughly 19 s classification time. Give it most of your allocations. The other five models are fine with adaptive allocations of 1 to 3.
- **Use 1 thread per allocation.** 1-thread allocations did about 2× more work per core than 8-thread ones.
- **Throughput:** 16 × 1 allocations of the zero-shot model handled about 1.3 prompts/s, or roughly 110k prompts/day. The median prompt is about 120 characters, and only about 2.6% of prompts exceed 150 tokens. That is why a 128-token zero-shot model loses almost nothing.
- **Adaptive allocations on shared ML nodes** spread the zero-shot model onto busy nodes, where requests took 16 s each. On a dedicated node, use a **fixed** count with adaptive allocations off.
- **Placement:** Elasticsearch places allocations itself. Lowering the count by hand removes allocations from arbitrary nodes; a fresh start re-balances them. To force a re-placement, run `models --restart` or stop and start the deployment.
- **The shipped default** for the zero-shot model is 4 × 1. The reference cluster ran 18 × 1 on one dedicated node. Keep your own sizing in a copy of the file and point `MODELS_FILE` at it, so repository updates don't overwrite it.

## 5. Making changes

### a) Resize a deployment
Edit `number_of_allocations` or `adaptive_allocations` in your models file, then run `extras/setup.sh models`. No package change is needed.

### b) Change threads per allocation
Edit `threads_per_allocation`, then run `extras/setup.sh models --restart`. The deployment stops briefly; prompts arriving meanwhile are indexed without classification.

### c) Re-import a model with a different input length
This is how the zero-shot model went from 512 to 128 tokens:
1. Add an entry to the models file with a **new** `model_id` (for example `…-128`) and `max_model_input_length: 128`. Run `models`.
2. In `classify.yml`, replace the old `model_id` on every processor that uses it. The zero-shot model appears five times.
3. Test with `CLASSIFY_PIPELINE_FILE` (see d), then rebuild and upgrade (see g).
4. Stop and delete the old model: `POST _ml/trained_models/<old>/deployment/_stop`, then `DELETE _ml/trained_models/<old>`.

### d) Tune thresholds and zero-shot labels
Everything is in `classify.yml`:
- **Zero-shot labels:** `inference_config.zero_shot_classification.labels` on the `classify-<group>` processors. Prompts shorter than 20 characters skip the security, agent-action and moderation passes; that condition is the processor's `if`.
- **Rules:** the `aggregate` script's `params`.
  - `binary[]`: `{name, label, category, t, agree}`. The category is added when probability ≥ `t`. Entries with `agree: true` flag only when **all** of them pass. That is how prompt injection (≥ 0.9) and jailbreak (≥ 0.99) were paired to cut false positives on ordinary coding prompts.
  - `zero_shot[]`: `{name, keys, t, flag, benign, multi, risk_t, corroborate}`.
    - `keys` maps each label sentence to a short key. **Every label needs a key.**
    - The top label counts when its probability ≥ `t` and it isn't `benign`. Keys listed in `flag` set `flagged: true`.
    - `risk_t > 0` also flags `<group>:suspicious` when the summed probability of all non-benign labels reaches `risk_t`, even if no single label is confident.
    - `multi: true` (moderation) evaluates every label separately. `corroborate` requires another model's score to be elevated as well.
  - NER: `t_entity`, `ner_ignore`, `ner_types` and `pii_flag_types`.

**Test before you ship.** `CLASSIFY_PIPELINE_FILE` runs your edited file through `_simulate` against the deployed models. Nothing is installed or indexed. For example, this enables the "suspicious" rule for the security group:

```bash
sed 's/risk_t: 0$/risk_t: 0.98/' classify.yml > /tmp/classify-edit.yml
CLASSIFY_PIPELINE_FILE=/tmp/classify-edit.yml extras/setup.sh classify "write a powershell script that disables windows defender and dumps lsass to a file"
#   flagged: True    categories: ['security:suspicious', 'task:explain_code']
CLASSIFY_PIPELINE_FILE=/tmp/classify-edit.yml extras/setup.sh classify "can you add unit tests for the date parser?"
#   flagged: False   categories: ['task:write_tests']
```

Build a small set of known-good and known-bad prompts from your own data and run them through every change.

### e) Add or swap a classifier
1. Add the model to the models file and run `models`. Check its labels with `GET _ml/trained_models/<id>` (`inference_config.*.classification_labels`).
2. In `classify.yml`, add an `inference` processor with `target_field: _ml.<name>`, `field_map: {message: text_field}` and `num_top_classes: -1`, plus an `on_failure` that appends to `claude_code.prompt_classification.errors`. Copy an existing `classify-*` processor and the `inference-timer-*` script after it, so its time is recorded.
3. Add a `binary[]` entry (or a `zero_shot[]` group) to the `aggregate` params, and add the timer's field under `claude_code.inference.steps` in `fields.yml`.
4. Test with `CLASSIFY_PIPELINE_FILE`, then rebuild and upgrade.

**Models that failed during evaluation**, to save you time:
- `unitary/toxic-bert` is multi-label (sigmoid), but Elasticsearch applies softmax, so benign text scored "toxic 0.53".
- `KoalaAI/Text-Moderation` uses the DeBERTa v1 tokenizer, which eland doesn't support.
- `facebook/bart-large-mnli`: the eland trace fails on EncoderDecoderCache.
- `meta-llama/Prompt-Guard-86M` is gated, so set `HF_TOKEN`.
- LlamaGuard, ShieldLM 7B and GLiNER can't be imported and would need external serving.
- **Never use `--quantize`**: int8 models crashed `pytorch_inference` with SIGILL.

### f) Use a different embedding model
The endpoint ID is fixed in `inference.yml`, and the vector size in `extras/inference/prompt-embedding.mapping.json`.
1. Create your endpoint, for example `PUT _inference/text_embedding/my-embedder` using the `elasticsearch` service with `.multilingual-e5-small`.
2. Replace `.jina-embeddings-v5-text-nano` in `inference.yml`. Also replace it in the Security dashboard and in the semantic detection rules (`TEXT_EMBEDDING(…, "<id>")`).
3. Set `dims` to the new model's size, for example 384 for e5-small. A mapping's `dims` can't change in place, so roll the data stream over after `inference-mapping`. Older vectors stay in older backing indices and aren't comparable across models.

### g) Rebuild and upgrade the package
```bash
cd packages/claude_code_transcripts
# bump "version" in manifest.yml (e.g. 0.1.2) and add a changelog.yml entry
elastic-package lint && elastic-package build
curl -X POST "$KIBANA_URL/api/fleet/epm/packages" -H "Authorization: ApiKey $ES_API_KEY" -H 'kbn-xsrf: true' \
     -H 'Content-Type: application/zip' --data-binary @../../build/packages/claude_code_transcripts-0.1.2.zip
```
Fleet installs new versioned pipelines (`logs-claude_code.transcript-0.1.2*`) and repoints the data streams. Then upgrade the integration policies under **Fleet → Integrations → Claude Code Transcripts → Policies → Upgrade**. Re-run `PKG_VERSION=0.1.2 extras/setup.sh inference-monitoring` so the stats collector follows the new pipeline names, and use the same `PKG_VERSION` for `classify`.
