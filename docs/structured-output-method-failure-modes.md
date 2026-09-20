# Structured-output method: failure modes & provider-aware fix

**Status:** implemented (structured-output method is now provider-aware; Bedrock keeps `function_calling` with client-side mitigations)

## Question

Two completed runs on a separate survey logged structured-output `ValidationError`s that silently dropped
individual question-responses for some personas. gpt-5.4-mini had 8; Haiku 4.5 had 152. Why did
these appear when the earlier `azure/gpt-4.1` run had none, and how do we stop them recurring
without breaking Bedrock?

## Context

Both runs used `run_stateful_survey` with LLM answers elicited via `llm.with_structured_output(...)`
([survey_runner_excel.py](../src/core/survey_runner_excel.py)). The prior model-swap work
(model-temperature-reasoning-constraints.md) flipped
**all** call sites to `method="function_calling"` because the Bedrock schema validator rejects
array `maxItems`. That global switch is what exposed the failures below on soft-validated models.

### The two failure modes

Modes A and B are `ValidationError` under `function_calling`, where tool-call arguments are only
*advisory* and get validated **client-side by Pydantic** (then retried). They cannot occur under
`json_schema`, where the provider **constrained-decodes** the exact schema — but that protection
covers only constraints the schema actually *carries*, which is Mode C below.

**Mode A — list-as-string (Haiku, 151 of 152).** The model serialized the whole `variations`
value as a JSON *string* instead of a native list. Spans every structured type — Q26 open-ended,
grid and multi/single questions, Haiku on Bedrock:

```
1 validation error for OpenEndedResponse
variations
  Input should be a valid list [type=list_type, input_value='[{"answer": "I've had t...}]\n', input_type=str]
```

**Mode B — packed answer (gpt-5.4-mini, all 8).** Q26 only. The prompt's hardcoded closing block
told the model to return `• choice:` / `• explanation:`, but `OpenEndedResponse` needs `answer` +
`explanation`. The model followed the prose and packed both into the single `answer` string,
omitting `explanation`:

```
1 validation error for OpenEndedResponse
variations.0.explanation
  Field required [type=missing, input_value={'answer': 'choice: 1\nexplanation: ...'}, input_type=dict]
```

**Mode C — a length the schema never stated (`azure/gpt-4.1` under `json_schema`, 7 cells).** The
`verbalized_probs` arm asks for one probability per option. `option_probabilities` was declared as a
plain `List[float]`, so the emitted schema was `{"type": "array", "items": {"type": "number"}}` with
**no `minItems`/`maxItems`** — the length lived only in the field `description` prose plus a Pydantic
validator that runs client-side, *after* generation. On the two longest multi lists the model emitted
one number too many (Q30: 24 options, 25 numbers; Q25: 14 → 15) and the validator then rejected the
whole response, discarding a valid `choice` and `explanation` with it.

This is the exception to "Mode A/B cannot occur under `json_schema`": constrained decoding enforces
the schema, not the docstring. Any constraint that matters must be *in* the schema —
`Field(min_length=n, max_length=n)`, which Pydantic emits as `minItems`/`maxItems`. OpenAI's
Structured Outputs keyword list marks those unsupported only for *fine-tuned* models; base models
enforce them under `strict: true`. Bedrock still rejects array `maxItems`, so the declaration is
made per provider from the same `structured_output_method` dispatch (see Resolution), and the
client-side check is now non-fatal: a miscount costs the probability vector, never the answer.

### Root cause

The committed default is LangChain's `method="json_schema"` — the method the July-18 gpt-4.1 run
used — which **hard-enforces** the schema in the provider's decoder, so neither malformed shape can
be emitted. The global switch to `method="function_calling"` (necessary for Bedrock's `maxItems`
limitation) moved enforcement to **client-side Pydantic + retry**, which is only as good as the
model's willingness to follow the schema. gpt-4.1 was immune only because it ran under
`json_schema`; gpt-5.4-mini and Haiku failed because they ran under `function_calling`.

Per the swap-guide table, **gpt-5.4-mini works fine under `json_schema`** — only Bedrock models
can't use it. So the fix is to pick the method per provider, not globally.

## Resolution

**Provider-aware method** ([`structured_output_method`](../src/utils/llm_factory.py)): OpenAI/Azure
→ `json_schema` (hard enforcement — Mode A/B impossible; gpt-4.1 returns to its original
committed behavior); Bedrock/Claude → `function_calling` (unavoidable). All 5 `with_structured_output`
call sites now pass `method=structured_output_method(model)`.

**Array lengths declared per provider** (Mode C): `run_stateful_survey` derives
`enforce_prob_length = structured_output_method(model) == "json_schema"` from that same dispatch and
threads it into the response-model factories, which add `min_length`/`max_length` to
`option_probabilities` only when it is true. The Bedrock path keeps a schema with no `maxItems`; on
it a wrong-length vector is dropped by `_extract_option_probabilities` and the answer survives.

**Bedrock mitigations** (inert on the `json_schema` path, so OpenAI/Azure are unaffected):
- **Lenient `variations` parser** — a `_LenientVariationsBase` (`field_validator(mode="before")`)
  shared by all three response-model factories json-decodes a stringified `variations` before
  validation (recovers Mode A). Malformed JSON falls through and still raises.
- **Per-type `{response_format}`** — the prompt's closing block is now a placeholder the runner
  fills with `answer:`/`explanation:` for open-ended vs `choice:`/`explanation:` for choice/grid
  (recovers Mode B). The choice text is byte-identical to the old hardcoded block.

**Repairing the residue** — a `ValidationError` is retryable, so re-running the same command with
`--resume` re-asks exactly the failed work: whole personas on a stateful checkpoint, single
(question, respid) cells on a stateless one, one call per cell. Neither flavour marks failed work
complete ([repairing a run that reported
errors by re-running with `--resume`).
A standalone repair script is optional — use
`--dry-run` to report what failed, or the full run for a checkpoint written before 2026-09-04, whose
manifest still lists failed work as complete. One caveat it carries: an error record with no respid
means that question failed wholesale, and because `main.py` checkpoints a question *before*
validating it, dropping the question discards good rows when the fault was in validation — fix the
code and resume instead of pruning.

## Verification snippets

These small checks confirmed the fix before any live run.

**1. Provider-aware selector — truth table**
```python
from src.utils.llm_factory import structured_output_method as som
som("azure/gpt-4.1")                          # -> "json_schema"
som("azure/gpt-5.4-mini")                     # -> "json_schema"
som("bedrock/us.anthropic.claude-haiku-4-5")  # -> "function_calling"
som(None)                                     # -> "function_calling" (MODEL_NAME env default is Bedrock)
```

**2. Lenient parser — recover / passthrough / raise**
```python
import json
from src.core.survey_runner_excel import create_open_ended_response_model
OE = create_open_ended_response_model(n_variations=1)
# Mode A recovered: JSON string -> native list
OE.model_validate({"variations": json.dumps([{"answer": "a", "explanation": "e"}])})
# native list unchanged (json_schema / gpt-4.1 path)
OE.model_validate({"variations": [{"answer": "native", "explanation": "e"}]})
# malformed JSON still raises (no worse than today)
OE.model_validate({"variations": '[{"answer":"x","explanation":"e"},]}]'})  # ValidationError
# Mode B still raises without the prompt fix (packed answer, missing explanation)
OE.model_validate({"variations": [{"answer": "choice: 1\nexplanation: ..."}]})  # ValidationError
```

**3. Prompt `{response_format}` — byte-identical choice render, correct open-ended render**
```python
from langchain_core.prompts import ChatPromptTemplate
from src.core.survey_runner_excel import _CHOICE_RESPONSE_FORMAT, _OPEN_ENDED_RESPONSE_FORMAT
before = ChatPromptTemplate.from_template(
    "  Return your answer with:\n"
    "  • choice: Option number(s) you select based on your persona and prior answers\n"
    "  • explanation: Brief reasoning for this response\n").format()
after = ChatPromptTemplate.from_template(
    "  Return your answer with:\n  {response_format}\n").format(response_format=_CHOICE_RESPONSE_FORMAT)
assert before == after                          # choice/grid + gpt-4.1 prompt unchanged
# open-ended now asks for answer:, not choice:
```

## Notes

- The `maxItems`/Bedrock background and the `json_schema` vs `function_calling` distinction live in
  model-temperature-reasoning-constraints.md.
- gpt-4.1 is routed back to `json_schema`, matching its
  committed behavior; the parser is a passthrough for it and the prompt renders identically.
- A few Haiku payloads are *malformed* JSON (trailing commas); the parser can't recover those —
  they still fail and are logged, same as before.

## Next steps

- Live `--sample 2` on the haiku config to confirm Mode A recovery end-to-end; re-run both configs
  with `--resume` to refresh the affected respids' outputs.
