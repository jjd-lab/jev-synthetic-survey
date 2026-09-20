# Does describing the options close the gap?

**Status: run. Both criteria failed; the control passed.** Describing the options changes
essentially nothing.

The plan below was committed before the data existed and before the code that implements it, so
the rule is timestamped by this repository rather than asserted afterwards. That is the thing the
[original comparison](01-question-and-criteria.md) could not offer. It is left unedited; the result
is reported above it.

## Result

| Criterion, fixed in advance | Threshold | Measured | |
|---|---|---|---|
| Moves the boundary | pricing signed bias below +0.10 | +0.185 to **+0.183** | fail |
| Closes the gap | pricing distribution gap at or below 0.1074 | unchanged, Wilcoxon p=1.0000 | fail |
| Controls hold | untouched columns within the 0.0055 floor | **-0.0042** | pass |

The control passing is what makes the two failures readable: the 43 multi-option columns received a
byte-identical payload and stayed put, so the run is clean.

Paired against Jev Choice on the same 300 respondents, the two-option distribution gap moved
**+0.0001**, CI [-0.0025, +0.0025]. Brier moved +0.0003. Against GPT-4.1 probabilities the gap is
+0.0196 at p=1.0000, which is Jev Choice's own figure to four decimal places.

24,596 cells, 300 respondents, zero errors, zero aborted walks, $4.03.

### The descriptions were read, and did nothing directional

Per-cell movement on the 40 described columns was 0.062 TVD against 0.011 on the untouched
two-option controls, so the model did respond to them, about five times above noise. But of 12,000
pricing cells, 5,743 moved up and 4,605 moved down, median exactly zero, standard deviation 0.144.
The perturbation is real and symmetric, so the marginal does not shift.

For scale, switching the primitive moves the same cells 0.142, more than twice as far and in one
direction.

### Saturation is untouched, which explains the null

Cells putting a probability of exactly zero on an option:

| Arm | Rate over the 15,896 two-option cells |
|---|---|
| Jev Choice | 16.6% |
| Jev Choice described | 17.2% |
| Jev Noul | 0.0% |

A zero on the human's actual answer costs the full 2 in Brier and is unbounded in log loss, and
that is what drove the original gap. `Noul` removes those zeros by construction. A description
cannot, and did not.

### What it settles

The strongest objection to "never ask Jev a yes/no as a `Choice`" was that `Choice` had been
under-specified: bare labels, with TypeSafe's own documented lever unpulled. That objection is now
tested and dead. The recommendation survives its best challenge.

It also weakens the framing hypothesis for pricing. The +0.185 offset survived a description that
names the boundary in words, so "a framing problem a description can fix" is unlikely and a
calibration-layer problem is the better reading.

### A measurement worth keeping

The 68 undescribed columns receive a byte-identical payload, so their movement is a clean estimate
of Jev's run-to-run nondeterminism in a paired design. Per cell it is 0.011, against the 0.055 from
`order_probe` that [the planned comparison](02-planned-comparison.md) already flags as inflated by
accidental chaining.

The column-level floor matters more, since that is the level an arm comparison is read at, and it
is 0.0010 over the 25 two-option columns and 0.0058 over the 43 multi-option ones. The second
nearly matches the 0.006 those pages already use, so no earlier conclusion moves. Only the per-cell
figure was loose.

### Reproduce

```bash
python scripts/twin2k/prob_scoring.py score \
    --arm jev_described=runs/jev_vs_gpt41_n300/jev_choice_described.jsonl \
    --arm jev=runs/jev_vs_gpt41_n300/jev_choice.jsonl \
    --arm bc=runs/jev_vs_gpt41_n300/gpt41_probs.jsonl \
    --bootstrap 1000 --seed 20260919 --ece-bins 10 \
    --out /tmp/check.json
```

Writes the equivalent of [`reports/score_with_described.json`](../../reports/score_with_described.json).
The boundary figures come from `price_sensitivity.py` with the same four arms.

## The question

Jev was given the same input GPT-4.1 got: the option labels bare, with no descriptions
(`criteria: {option: None}` in `jev_client.build_payload`,
[`jev_client.py`](../../scripts/twin2k/jev_client.py)). That
matching is what made the comparison a test of models rather than of prompting, and it is why
every lever in TypeSafe's own guidance was left untouched.

One of those levers lands on the half Jev lost. TypeSafe documents option descriptions as existing
to "separate the options from each other", and the measured failure on the pricing block is a
near-constant +0.185 offset in *where "yes" begins*, not an arithmetic error
([price sensitivity](04-price-sensitivity.md)). A description is the mechanism that could move a
boundary; a calculator is not.

So: **asked TypeSafe's way rather than GPT-4.1's way, does Jev still lose the yes/no half?**

## The rule, fixed in advance

Descriptions are **derived by code from the instrument**, never written by hand. Nobody types
description text, so nobody can tune it against a result they have already seen. The derivation is
committed before the run and is the experimental manipulation in full.

**Where descriptions are supplied.** On two-option columns, wherever the rule below derives one
from the label, and nowhere else. Run against the shipped mapping before writing any run code, that
is **exactly the 40 pricing columns**: their labels are first-person clauses ("Yes, I would purchase
the product"), and every other two-option column's labels are bare tokens the rule cannot restate
without inventing text ("more"/"fewer", "the small tray"/"the large tray").

The two-option restriction is part of the rule, not an accident of it. Checked against the
instrument, the derivation also fires on three ordered scales, `QID157`, `QID158` and `QID291`,
whose options read "I favor program A" and "I would probably take the vaccine". Describing those
would widen the manipulation past the question being asked, which is where a yes/no boundary sits,
and would shrink the control set the criteria below are read against. So the arm describes only
columns that have a boundary to move.

So the manipulation lands precisely on the block where the diagnosed failure is, and the instrument
decided that, not a preference. The other 68 columns keep `None`, exactly as the Jev Choice arm sent
them, and split into two controls: 25 two-option columns and 43 multi-option ones.

**How each description is derived.** For an option label on a two-option column, the description is
that label restated as a claim about this respondent under this stem, using only words already
present in the label:

1. strip a leading affirmation or negation and its comma (`"Yes, "`, `"No, "`);
2. rewrite the remaining first-person clause in the third person (`"I would"` becomes
   `"this respondent would"`);
3. wrap it as a claim about the question just asked:
   `"This respondent {clause}, for the situation described in the question."`

On a pricing column, `"Yes, I would purchase the product"` becomes
`"This respondent would purchase the product, for the situation described in the question."`

Labels that do not match the pattern in step 1 or 2 fall through **unchanged to `None`**, and the
count of such columns is reported. A fallback that invented text would be a second, unstated
manipulation.

## What is compared

The same 300 respondents, the same persona cache, the same walk, the same option-order seeds, the
same pinned `jev-1.13.0`. One factor changes.

| Arm | Descriptions | Elicitation |
|---|---|---|
| Jev Choice (existing) | none | `Choice` on all 108 |
| Jev Noul (existing) | none | `Noul` on the 65, `Choice` on the 43 |
| **Jev Choice described** (new) | on the 40 pricing columns | `Choice` on all 108 |

## Why the comparison is against Choice, not Noul

`Noul` already uses the description slot. Its schema offers only `true` and `false` keys, so the
survey's own option text goes in the **value** position, which is where a description lives
([`jev_client.py:207`](../../scripts/twin2k/jev_client.py)). `Choice` does the opposite: the option
text is the **key** and the value is `None`.

So Jev sees the option text under both primitives today; what differs is which slot carries it.
The Choice-versus-Noul result was never about whether Jev could read the options.

That is why this arm is paired against Jev Choice, which differs from it in one factor. Pairing it
against Jev Noul would differ in two, the primitive and the descriptions, and would answer nothing
cleanly. Jev Noul stays in the table above as a reference point.

A described `Noul` is possible, since its value slot exists, but is not run here: that slot is
already occupied by the option text, so replacing it would be a different manipulation and would
break comparability with the shipped Noul arm.

What this sharpens is the headline. "Never ask Jev a yes/no as a `Choice`" is the strongest
actionable claim in this work. If descriptions close the pricing gap, it narrows to "never ask a
*bare* `Choice`", and a described one may be fine. If they do not, the Noul recommendation gets
stronger, because it survives the obvious objection that `Choice` was simply under-specified.

## What decides it, fixed now

Read against **Jev Choice**, paired by respondent and column, on the 40 pricing columns where the
manipulation applies:

- **Moves the boundary**: the pricing signed bias falls below +0.10, from +0.185.
- **Closes the gap**: the pricing distribution gap falls at or below GPT-4.1 probabilities' 0.1074,
  from 0.2246, on the per-column Wilcoxon the original test used, not on the task-weighted mean.
- **Controls hold**: the 25 undescribed two-option columns and the 43 multi-option columns each move
  by less than the measured reproducibility floor, 0.0055 on the ordinal gap. They receive a
  byte-identical prompt, so if they move more, the run is not clean and nothing else is read.

Because the controls are byte-identical rather than merely similar, they are a sharper check than
the original comparison had.

Any other outcome is reported as the partial result it is. In particular, moving the boundary
without closing the gap is a real and interesting answer, not a failure to be re-cut.

## What this cannot show

It is **not** a model comparison. GPT-4.1's prompt is unchanged, so a described Jev arm beating it
would say that Jev prompted well beats GPT-4.1 prompted plainly. The original verdict is not
reopened by it, in either direction.

It is also **one lever of several**. A structured `state` object and TypeSafe's other documented
guidance remain untried.

## Cost

About $4, on the same basis as the existing Jev arms: input-only billing at $0.042 per million
tokens, output free. Descriptions add tokens to the 40 pricing columns only. `--dry-run`
reports the exact figure before anything is sent.

## Reproduce

See the Reproduce block under Result, above. The arm ships as
`runs/jev_vs_gpt41_n300/jev_choice_described.jsonl`.
