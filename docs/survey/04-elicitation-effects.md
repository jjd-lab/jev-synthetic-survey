# How you ask changes what the model answers

Two results about the request rather than the model. Asking GPT-4.1 for a probability distribution
moves the answer it then commits to, and the shape of the output contract decides whether an answer
survives at all.

## Question

A survey simulation has to pick an elicitation format before it collects anything: ask the model to
pick one option, or ask it to state a probability for each option and derive the pick. The usual
assumption is that this is a presentation choice, that the underlying judgment is the same either
way and only the reporting differs.

It is not. **Does asking for a distribution change the committed answer, and by how much?**

## Setup

Two arms of the same 300-respondent comparison, `azure/gpt-4.1`, a demographics-only persona, each
simulated respondent walking its own questionnaire statefully so that it sees its own earlier
answers. Same 300 respondents (ids 1 to 300 in loader order), same 108 scored columns, same 16
tasks, same persona cache, **24,596 answered cells in each arm**, with set equality asserted on
respondent ids and cell keys rather than on counts.

| Arm | What was asked | Grids | Run file |
|---|---|---|---|
| **GPT-4.1 hard answer** | pick one option, no probabilities | batched | [`runs/jev_vs_gpt41_n300/gpt41_hard.jsonl.gz`](../../runs/jev_vs_gpt41_n300/gpt41_hard.jsonl.gz) |
| **GPT-4.1 probabilities** | state a probability per option, then name a choice | unbatched, one call per cell | [`runs/jev_vs_gpt41_n300/gpt41_probs.jsonl.gz`](../../runs/jev_vs_gpt41_n300/gpt41_probs.jsonl.gz) |

The probabilities arm was run from
[`configs/twin2k/twin2k_survey_config_probs_chained.yaml`](../../configs/twin2k/twin2k_survey_config_probs_chained.yaml);
the workbooks it was converted from are under
[`runs/jev_vs_gpt41_n300/gpt41_probs_source/`](../../runs/jev_vs_gpt41_n300/gpt41_probs_source/).
The hard-answer arm is the same stateful demographics arm with no probability mode set, and its run
records carry no probability vector at all. [`runs/README.md`](../../runs/README.md) maps both.

The two arms differ in two ways, not one, which is why the result below is a decomposition
rather than an attribution. The probabilities arm also unbatched its grids, asking one call per cell
where the hard-answer arm asked a grid's rows together. Grid batching is in play on exactly one block
of this instrument: the 40 pricing columns.

## Metrics

Accuracy as defined on the [metrics page](02-metrics.md), equal weight across the 16 tasks.

One deviation from the repo default, and it is deliberate. Accuracy elsewhere is computed from each
arm's own probability vector, because that is defined for every arm. **This question is about what
each arm committed**, so it is the one place the arms' stated choice is read instead. Both are
reported below, and they agree.

## Results

Asking for probabilities costs 4.42 points of committed accuracy.

| | GPT-4.1 hard answer | GPT-4.1 probabilities | difference |
|---|---|---|---|
| accuracy, as stated | 69.32% | 64.90% | **−4.42** |
| accuracy, from the vector | 69.32% | 64.78% | −4.54 |

The tolerance fixed in advance for this check was ±2 points, so the gap is outside it either way.

Splitting by whether grid batching is in play separates the two candidate causes:

| | GPT-4.1 hard answer | GPT-4.1 probabilities | difference |
|---|---|---|---|
| Pricing, the **only** 40 columns where grid batching differs | 63.97% | 64.86% | **+0.89** |
| The other 15 tasks, one call per cell in both arms | 69.68% | 64.91% | **−4.77** |

## Interpretation

**The entire loss sits where the grid setting is not in play, and the one block that was unbatched
slightly improved.** So this is the effect of asking for a distribution, not the effect of
unbatching. Unbatching cost nothing measurable and remains the right choice for matching one call
per cell across arms.

The visible mechanism is schema field order. The probability vector is the first dynamic field in
the response schema, so the model writes the whole vector before it writes its choice, and its
choice is then conditioned on what it has already written. The residue of that shows up as
self-contradiction: the probabilities arm named an option strictly below its own maximum in 0.77% of
cells, roughly five times the rate of a model asked for a native vector.

**The practical rule: if you ask a model to verbalize its uncertainty, expect its committed answer
to move.** That applies well beyond this instrument. It also means a pipeline that changes
elicitation format between a pilot and a production run has changed the measurement, not just the
reporting, and an accuracy figure carried across that boundary is not comparable.

## Caveats

- **One model, one instrument, one direction.** GPT-4.1, Twin-2K-500, and the format change in one
  direction only. Nothing here establishes the size or even the sign of the effect for another
  model.
- **The 300 respondents are the first 300 rows of the panel and are not representative of it.**
  They are older and more conservative than the full 2,058. Both arms are the same 300 people and
  the comparison is paired, so the difference holds; the absolute levels describe that slice only.
  See [`runs/README.md`](../../runs/README.md).
- **The two arms were not otherwise identical.** Grid batching is the second difference, which is
  why it is decomposed rather than assumed away. The decomposition rests on the fact that batching
  applies to exactly one of the 16 tasks.
- **Accuracy is the only metric this reads.** The hard-answer arm has no probability vector, so
  every distributional and calibration comparison against it measures "has a distribution at all"
  rather than the quality of one.
- **No individual-level claim.** Both arms sit below the persona-blind leave-one-out floor of 73.59%
  on these 300 respondents.

## Reproduce

```bash
python scripts/twin2k/prob_scoring.py score \
    --arm jev_chained=runs/jev_vs_gpt41_n300/jev_choice.jsonl.gz \
    --arm gpt41_probs_chained=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl.gz \
    --arm gpt41_hard_chained=runs/jev_vs_gpt41_n300/gpt41_hard.jsonl.gz \
    --bootstrap 1000 --seed 20260919 --ece-bins 10 --out /tmp/check.json
```

That reproduces [`reports/score_all_arms.json`](../../reports/score_all_arms.json), which holds both
accuracy readings for all three arms and the per-task breakdown the pricing split above is taken
from. The `--arm` labels become the keys in the output, so the labels above are the ones the shipped
report was scored with. [`reports/README.md`](../../reports/README.md) maps every report back to its
run.

## Part two: the same mechanism in structured-output failures

**Scope note.** This part is not about Twin-2K-500 and not about GPT-4.1: it concerns gpt-5.4-mini
and Haiku 4.5 on a separate survey, in this same engine. It is kept here because it is the same
mechanism seen from the other side, where the shape of the output contract decides not just what the
model answers but whether the answer survives at all.

Two completed runs on that survey logged schema-validation errors that silently dropped individual
question responses for some personas: gpt-5.4-mini had 8, Haiku 4.5 had 152. An earlier
`azure/gpt-4.1` run on the same code had none.

### Three failure modes

**A: the list arrives as a string.** 151 of Haiku's 152. The model serialized a whole list-valued
field as a JSON *string* instead of a native list. It spans every structured question type, so it is
a serialization habit rather than a property of one question.

**B: the answer arrives packed into one field.** All 8 of gpt-5.4-mini's, on one question type. The
prompt's hardcoded closing block told the model to return a choice and an explanation, while the
response model for that question type needed an answer and an explanation. The model followed the
prose and packed both into the single answer string, omitting the explanation field entirely. The
prompt and the schema disagreed, and the model obeyed the prompt.

C: a length the schema never stated. `azure/gpt-4.1`, 7 cells. The probability-vector field was
declared as a plain list of numbers, so the emitted schema carried no minimum or maximum item count.
The required length lived only in the field's description prose plus a validator that runs on the
client, after generation. On the two longest option lists the model emitted one number too many, 25
for 24 options and 15 for 14, and the validator then rejected the whole response, discarding a
perfectly good choice and explanation with it.

### Root cause

Two enforcement modes look interchangeable and are not.

- Under **`json_schema`**, the provider constrained-decodes the exact schema. Modes A and B cannot be
  emitted.
- Under **`function_calling`**, the arguments are advisory and are validated on the client, then
  retried. Enforcement is only as good as the model's willingness to follow the schema.

Earlier model-swap work flipped **all** call sites to `function_calling`, because one provider's
schema validator rejects array length limits. That global switch moved enforcement to the client and
is what exposed A and B on soft-validating models. GPT-4.1 was immune only because it had run under
`json_schema`.

Mode C is the exception that states the rule: **constrained decoding enforces the schema, not the
docstring.** Any constraint that matters has to be *in* the schema, as an actual minimum and maximum
item count, not in prose the decoder never sees and not in a validator that runs after the tokens
are spent.

### The fix, and what generalizes

The repair was to choose the enforcement method per provider rather than globally, and to declare
array lengths only where the provider accepts them. Where hard enforcement is unavailable, the
client-side check was made non-fatal, so a miscounted vector costs the probability vector and never
the answer. Two client-side mitigations back that up on the soft path: a lenient parser that decodes
a stringified list before validation (recovering mode A), and a per-question-type response-format
block in the prompt, so the prompt asks for exactly the fields the schema declares (recovering mode
B). On the hard-enforcement path both are inert.

Residue is repaired by re-running the same command with `--resume`, which re-asks exactly the failed
work and nothing else: whole personas on a stateful checkpoint, single cells on a stateless one.
Neither flavor marks failed work complete. One caveat carries: an error record with no respondent id
means the question failed wholesale, and because a question is checkpointed *before* its answers are
validated, dropping that question discards good rows when the fault was in validation. Fix the code
and resume rather than pruning.

Three things generalize from this to any structured-output survey pipeline:

1. **A constraint that is not in the schema is not enforced.** Prose in a field description is a
   hint; a client-side validator is a post-mortem.
2. **The prompt and the schema must ask for the same fields.** Where they disagree, expect the model
   to follow the prose and fail validation.
3. **A validation failure should cost the smallest possible thing.** Mode C threw away a valid
   answer because one optional vector was the wrong length. Partial extraction is worth the code.
