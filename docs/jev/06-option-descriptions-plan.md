# Plan: does describing the options close the gap?

**Status: not yet run.** This page is written before the data exists, and is committed before the
code that implements it, so the rule below is timestamped by this repository rather than asserted
afterwards. That is the thing the [original comparison](01-question-and-criteria.md) could not
offer.

## The question

Jev was given the same input GPT-4.1 got: the option labels bare, with no descriptions
(`criteria: {option: None}`, [`jev_client.py:174`](../../scripts/twin2k/jev_client.py)). That
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

To be filled in when the run exists, alongside the arm's file under `runs/jev_vs_gpt41_n300/`.
