# Models for the optional ML inference

Inference is **off by default**. It runs only for human prompts (`claude_code.human_prompt: true`) and only when **Enable ML inference** is switched on in the integration policy. Failures never block indexing.

## 1. Prompt embedding (switch: Enable ML inference)

| Inference endpoint | Output field | Notes |
|---|---|---|
| `.jina-embeddings-v5-text-nano` | `claude_code.prompt_embedding` (768 dims, cosine) | Preconfigured endpoint served by the **Elastic Inference Service (EIS)**. Available on Elastic Cloud. On self-managed clusters it needs Cloud Connect / EIS. |

Check that the endpoint exists:

```
GET _inference/text_embedding/.jina-embeddings-v5-text-nano
```

Then add the vector mapping once. Integration packages cannot declare `dense_vector` fields, so this step is separate:

```
ES_URL=... ES_API_KEY=... extras/setup.sh inference-mapping
```

The security dashboard's semantic panels and the semantic detection rules call `TEXT_EMBEDDING(..., ".jina-embeddings-v5-text-nano")` at query time, so the same endpoint is needed for searching.

## 2. Prompt classification (switch: Prompt classification)

Import with [eland](https://github.com/elastic/eland) (Docker image `docker.elastic.co/eland/eland`). The Elasticsearch model IDs **must** match the IDs below, because the `classify` ingest pipeline refers to them.

| Elasticsearch model ID | Hugging Face model | Task | eland options |
|---|---|---|---|
| `protectai__deberta-v3-base-prompt-injection-v2` | `protectai/deberta-v3-base-prompt-injection-v2` | text_classification | `--max-model-input-length 512` |
| `jackhhao__jailbreak-classifier` | `jackhhao/jailbreak-classifier` | text_classification | |
| `s-nlp__roberta_toxicity_classifier` | `s-nlp/roberta_toxicity_classifier` | text_classification | `--max-model-input-length 512` |
| `cardiffnlp__twitter-roberta-base-offensive` | `cardiffnlp/twitter-roberta-base-offensive` | text_classification | `--max-model-input-length 512` |
| `cross-encoder__nli-deberta-v3-base-128` | `cross-encoder/nli-deberta-v3-base` | zero_shot_classification | `--es-model-id cross-encoder__nli-deberta-v3-base-128 --max-model-input-length 128` |
| `dslim__bert-base-ner` | `dslim/bert-base-ner` | ner | |

```bash
import() {  # $1 = hub model id, rest = extra options
  docker run --rm docker.elastic.co/eland/eland \
    eland_import_hub_model --url "$ES_URL" --es-api-key "$ES_API_KEY" \
    --hub-model-id "$1" --task-type "$2" "${@:3}"
}
import protectai/deberta-v3-base-prompt-injection-v2 text_classification --max-model-input-length 512
import jackhhao/jailbreak-classifier                 text_classification
import s-nlp/roberta_toxicity_classifier             text_classification --max-model-input-length 512
import cardiffnlp/twitter-roberta-base-offensive     text_classification --max-model-input-length 512
import cross-encoder/nli-deberta-v3-base             zero_shot_classification --es-model-id cross-encoder__nli-deberta-v3-base-128 --max-model-input-length 128
import dslim/bert-base-ner                           ner
```

Add `--ca-certs <file>` (or `--insecure`) for a private CA. **Do not use `--quantize`**: the int8 models crashed Elastic's `pytorch_inference` with SIGILL in testing.

### Starting the deployments

```
POST _ml/trained_models/protectai__deberta-v3-base-prompt-injection-v2/deployment/_start?threads_per_allocation=1&number_of_allocations=1
# repeat for each model; then size the zero-shot model separately
POST _ml/trained_models/cross-encoder__nli-deberta-v3-base-128/deployment/_start?threads_per_allocation=1&number_of_allocations=8
```

Sizing notes from a real deployment:
- The **zero-shot model is the bottleneck**. Every prompt makes five zero-shot requests (security, agent action, task, interaction, moderation). That is about 17 s of a prompt's roughly 19 s classification time on CPU.
- **1-thread allocations** did about 2× more work per core than 8-thread allocations.
- With 16 allocations × 1 thread, throughput was about 1.3 prompts/s (about 110k prompts/day) on a realistic mix of prompt lengths. The median prompt is about 120 characters.
- Single-pass models are fine with adaptive allocations (1-3).
- If ML nodes are shared, adaptive allocations can spill the zero-shot model onto busy nodes. A fixed allocation count on a dedicated node was more predictable.

Watch it with the optional **[ML Inference] Admin** dashboard and alerts (`extras/setup.sh inference-monitoring`).

### What the classifier produces

`claude_code.prompt_classification`:
- `categories`: list such as `prompt_injection`, `jailbreak`, `toxic`, `offensive`, `security:<label>`, `task:<label>`, `pii:<entity>`, `secret:<type>`.
- `flagged`: true when any risky category fired.
- `scores.*`: per-model probabilities, plus per-label zero-shot scores.
- `entities`: NER output.
- `errors`: per-model failures.

`prompt_injection` and `jailbreak` flag only when both models agree (≥ 0.9 and ≥ 0.99), which removes most false positives on ordinary coding prompts.

Timing: `claude_code.inference.total_ms`, `embedding_ms`, `classify_ms`, `classify_calls`, `steps.<model>_ms`.
