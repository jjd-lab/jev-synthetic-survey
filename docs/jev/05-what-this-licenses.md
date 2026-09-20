# What this result licenses, and what it does not

## What you can take from it

- **Do not switch to Jev for distributional fidelity on yes/no items on the strength of this
  test.** GPT-4.1 beats Jev Choice there on every measure that addresses it, and beats Jev Noul on
  the per-column rule that was fixed in advance.
- **Never ask Jev a yes/no question as a `Choice`.** That single substitution is worth more on the
  two-option half than the entire gap the comparison was measuring, at the same cost and with no
  accuracy penalty. It is the strongest actionable result here and the one to carry into any future
  Jev work. See [the Noul follow-up](03-noul-follow-up.md).
- **Jev is the better multi-option forecaster in this setting**, and the cheapest by a wide margin,
  about 34 times cheaper. If a use case is ordinal-scale marginals under cost pressure, this result
  argues for it. That is a narrower claim than the test was making, and it has not been tested on
  its own.
- **Do not use this Jev arm for crosstabs.** It reproduces a fifth of the real difference between
  demographic groups on the median task, and essentially none on four of them, while GPT-4.1 tracks
  the same variables about as far as the humans do. This is the one dimension measured here where
  Jev is the worse instrument. See [segment diversity](07-segment-diversity.md).
- **Keep pricing broken out in any future work.** The 9.18 point accuracy gap on the piped-price
  block is the single largest effect measured here, and its cause is a boundary offset rather than
  arithmetic. See [price sensitivity](04-price-sensitivity.md).

## What it does not license

- **No individual-level claim, for any arm.** Every arm sits below the persona-blind leave-one-out
  majority of 73.59% (Jev Choice by 6.00 points, GPT-4.1 probabilities by 8.80, GPT-4.1 hard answer
  by 4.27), and all of them fail the calibration test. That is a statement about demographics-only
  grounding, not about any one model.
- **This is not a verdict on Jev prompted TypeSafe's way.** The comparison deliberately gave Jev
  the input GPT-4.1 got, which is what makes it a comparison of models. Described option labels and
  a structured state object remain untested, and the one lever that was pulled afterwards moved the
  losing half a long way. Expect any re-run to need its criteria re-registered around them.
- **No absolute number should be read as a population estimate.** The 300 respondents are the first
  300 rows of the panel and are older, whiter and more conservative than it; see
  [runs/README.md](../../runs/README.md). Twin-2K-500 has also been public since 2025 and its tasks
  are classic replications, so contamination applies to every arm equally. Between-arm comparisons
  are fair; levels are not.
- **Scope.** 300 respondents, one instrument, one model version (`jev-1.13.0`, recorded per cell),
  two-option and ordinal columns only. Multi-select is untested and would need one `Noul` per
  option: the client now has the primitive, the scorer has no multi-select path. Whether to run
  company survey data through a third-party model is a governance decision this experiment cannot
  make; everything here ran on Twin-2K-500 (CC BY 4.0) only.

## What to run next

Not run, and deliberately so.

1. **A re-run with `Noul` registered in advance as the elicitation.** The follow-up arm is post hoc
   and cannot carry the criterion, but it has moved the interesting question. A properly registered
   arm using `Noul` for yes/no *and* described option labels is now the fair test against GPT-4.1,
   and it needs its aggregation rule fixed beforehand. That is the whole distance between the two
   answers the follow-up gives.
2. **The unchained Jev arm that was supposed to exist.** Now that the flag gates the walk rather
   than only cross-checking the config, an unchained run is a genuine second arm rather than a
   duplicate. It answers two questions at once: whether statefulness earns its cost for Jev, and
   whether accuracy falls as the state grows. It is also the prerequisite for packing many
   questions into one shared state, which only makes sense unchained.
3. **Does Jev read the individual?** Prior-answers grounding against the leave-one-out floor. Bring
   it back with question packing: unchained, all 108 questions on one shared state billed once,
   roughly $0.45 instead of roughly $25. TypeSafe warns that this arm's 20,000-token state is where
   accuracy starts falling with state size, so validate packed against solo vectors on about 200
   cells first, and settle item 2 before relying on the packing saving.
4. **A multi-option-only re-test**, since that is the half Jev won. The `Score` primitive is the
   obvious instrument, but TypeSafe states that thresholds do not transfer between primitive types,
   so its numbers could not be compared to these.
5. **Probability elicitation on an unchained arm**, wanted independently of this result and now
   reachable: every arm runs the per-persona walk, so setting `chain_own_answers: false` gives an
   arm that never sees its own earlier answers and can still be asked for a vector. Worth doing
   with a measured warning attached: asking for probabilities cost 4.4 accuracy points on a
   chained arm, and that should be re-measured here rather than assumed. See
   [elicitation effects](../survey/04-elicitation-effects.md).
6. **A walk that commits sampled draws into the history** rather than the model's own stated
   answer. Untestable offline, and the natural follow-up if soft aggregation proves
   under-dispersed.
