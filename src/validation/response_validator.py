"""Response validation for comparing synthetic vs ground truth"""

from typing import List, Dict, Any, Optional, Tuple
import math
import numpy as np
from collections import Counter


def classify_metric_bucket(question_type: str, ordered_scale: bool = False) -> str:
    """Map question type to its validation metric bucket."""
    if question_type == "open_ended":
        return "open_ended"
    if question_type == "multi":
        return "multi"
    if ordered_scale:
        return "ordinal"
    return "nominal"


def total_variation_distance(
    pct_a: Dict[str, float], pct_b: Dict[str, float], options: List[str]
) -> float:
    """TVD between two option distributions (0 = identical, 1 = maximally different)."""
    if not options:
        return 0.0
    return 0.5 * sum(abs(pct_a.get(opt, 0.0) - pct_b.get(opt, 0.0)) for opt in options)


def wasserstein_1_scale(
    synthetic_list: List[str], ground_truth_list: List[str], ordered_options: List[str]
) -> float:
    """Wasserstein-1 distance on ordered scale positions (1..n_options)."""
    from scipy.stats import wasserstein_distance

    positions = {opt: i + 1 for i, opt in enumerate(ordered_options)}
    syn_pos = [positions[s] for s in synthetic_list if s in positions]
    gt_pos = [positions[g] for g in ground_truth_list if g in positions]
    if not syn_pos or not gt_pos:
        return 0.0
    return float(wasserstein_distance(syn_pos, gt_pos))


def wasserstein_from_pcts(
    pct_a: Dict[str, float], pct_b: Dict[str, float], ordered_options: List[str]
) -> float:
    """Wasserstein-1 between two ordered *distributions* (sum |CDF_a - CDF_b|).

    The distribution-input sibling of `wasserstein_1_scale`, which takes respondent lists. Both
    compute the same statistic and agree where both apply; this variant exists because a rectified
    estimate (see `src/validation/ppi.py`) is a distribution with no underlying list of people to
    pass, so the list-based function cannot be called on it.
    """
    if not ordered_options:
        return 0.0
    u = np.array([pct_a.get(o, 0.0) for o in ordered_options], dtype=float)
    v = np.array([pct_b.get(o, 0.0) for o in ordered_options], dtype=float)
    if u.sum() <= 0 or v.sum() <= 0:
        return 0.0
    u /= u.sum()
    v /= v.sum()
    return float(np.abs(np.cumsum(u)[:-1] - np.cumsum(v)[:-1]).sum())


def mae_scale_steps(
    synthetic_list: List[str], ground_truth_list: List[str], ordered_options: List[str]
) -> float:
    """Mean absolute error in scale steps for ordinal single-choice pairs."""
    positions = {opt: i + 1 for i, opt in enumerate(ordered_options)}
    errors = [
        abs(positions[s] - positions[g])
        for s, g in zip(synthetic_list, ground_truth_list)
        if s in positions and g in positions
    ]
    return sum(errors) / len(errors) if errors else 0.0


def marginal_prevalence_distance(
    synthetic_list: List[Any], ground_truth_list: List[Any], all_options: List[str]
) -> float:
    """Mean absolute difference in per-option selection rates (multi-select)."""
    n = len(synthetic_list)
    if n == 0 or not all_options:
        return 0.0
    total = 0.0
    for opt in all_options:
        syn_rate = sum(
            1 for s in synthetic_list if isinstance(s, list) and opt in s
        ) / n
        gt_rate = sum(
            1 for g in ground_truth_list if isinstance(g, list) and opt in g
        ) / n
        total += abs(syn_rate - gt_rate)
    return total / len(all_options)


def kl_and_blind_spot(
    pct_human: Dict[str, float],
    pct_llm: Dict[str, float],
    options: List[str],
    bucket: str,
    n: int,
    min_n_for_gating: Optional[int] = None,
) -> Dict[str, Any]:
    """KL(human ∥ LLM) with Laplace smoothing + blind-spot flag.

    Returns kl=None when n is below the gating floor — the guardrail is inside this function
    so it applies identically to the overall row and every segment row. `min_n_for_gating`
    defaults to `MIN_N_FOR_GATING`; a survey can raise it via config, and every caller that
    omits it keeps the fixed contract floor.

    nominal: standard KL over the probability simplex (rates renormalized to sum to 1).
    multi:   per-option Bernoulli KL, averaged. Rates are NOT renormalized — each option
             is treated as an independent binary variable, matching MAD's framing.
    ordinal: blind spot only, `kl` stays None. The two halves of this function need different
             things from the scale and only one of them needs ordering. The blind-spot flag asks
             whether the LLM ever produced an answer humans used, which is order-free; KL would
             treat the scale points as unordered labels, which is exactly why W1 is the ordinal
             metric. Excluding the flag along with KL cost the worst bucket its worst diagnostic:
             18 of the reference run's 22 gate-eligible ordinal questions carry a blind spot, and 4
             of G9's 9 failures are ordinal (`Q24::*` importance scales where the LLM never uses
             one end of the scale).
    """
    # Resolved here rather than in the signature: MIN_N_FOR_GATING is defined below, beside the
    # other gate constants, so it is not yet bound when this def is evaluated.
    if min_n_for_gating is None:
        min_n_for_gating = MIN_N_FOR_GATING

    if n < min_n_for_gating or not options:
        return {"kl": None, "blind_spot": None, "blind_spot_worst": None,
                "blind_spot_options": None, "kl_thin": True}

    p_raw = np.array([pct_human.get(o, 0.0) for o in options], dtype=float)
    q_raw = np.array([pct_llm.get(o, 0.0)   for o in options], dtype=float)

    if p_raw.sum() <= 0:
        # No human mass on any option: there is no coverage claim to make either way.
        return {"kl": None, "blind_spot": False, "blind_spot_worst": 0.0,
                "blind_spot_options": [], "kl_thin": False}

    if q_raw.sum() <= 0:
        # The LLM put zero on EVERY option humans used — the maximal coverage gap, so the
        # blind-spot definition is satisfied for all of them. `False` here would read as an
        # all-clear on the one metric built to catch this. KL itself stays None: it is
        # unbounded here and its smoothed value would only measure KL_SMOOTHING_EPS.
        # Reachable on a stateless multi run where every respondent selected nothing
        # (`require_selection=False` makes an empty `choices` list schema-legal).
        # Same filter and same worst-first order as the general path below, not merely "every option
        # with human mass": an option 0.4% of humans chose is not one this function calls missed, and
        # a list in option order would make `missed_options[:3]` show three arbitrary answers.
        return {"kl": None, "blind_spot": True,
                "blind_spot_worst": round(float(p_raw.max()), 4),
                "blind_spot_options": [o for _, o in sorted(
                    ((p_raw[i], options[i]) for i in range(len(options))
                     if p_raw[i] >= KL_BLIND_SPOT_HUMAN_MIN),
                    key=lambda pair: (-pair[0], pair[1]))],
                "kl_thin": False}

    # Names, not just the count: a gate that says only "0.44 missed" is not actionable, and which
    # answer went missing is the whole content of the finding — an abandoned end of an importance
    # scale and an unpicked middle option are different defects with different fixes.
    missed = sorted(((p_raw[i], options[i]) for i in range(len(options))
                     if p_raw[i] >= KL_BLIND_SPOT_HUMAN_MIN and q_raw[i] < KL_BLIND_SPOT_LLM_MAX),
                    key=lambda pair: (-pair[0], pair[1]))
    blind_spot         = len(missed) > 0
    blind_spot_worst   = round(float(missed[0][0]) if missed else 0.0, 4)
    blind_spot_options = [option for _, option in missed]

    if bucket == "ordinal":
        kl = None  # see the docstring: the flag is order-free, KL is not
    elif bucket == "nominal":
        p        = p_raw / p_raw.sum()
        q_smooth = (q_raw + KL_SMOOTHING_EPS) / (q_raw + KL_SMOOTHING_EPS).sum()
        kl = float(sum(p[i] * math.log2(p[i] / q_smooth[i])
                       for i in range(len(p)) if p[i] > 0))
    else:  # multi — per-option Bernoulli KL, averaged
        eps = KL_SMOOTHING_EPS
        kl_terms = []
        for ph, ql in zip(p_raw, q_raw):
            ql_s = min(max(ql + eps, eps), 1.0 - eps)
            ph_s = min(max(ph,  eps), 1.0 - eps)
            kl_terms.append(
                ph_s * math.log2(ph_s / ql_s)
                + (1 - ph_s) * math.log2((1 - ph_s) / (1 - ql_s))
            )
        kl = float(sum(kl_terms) / len(kl_terms)) if kl_terms else 0.0

    return {"kl": None if kl is None else round(kl, 4), "blind_spot": blind_spot,
            "blind_spot_worst": blind_spot_worst, "blind_spot_options": blind_spot_options,
            "kl_thin": False}


# Entropy diagnostics
# Diagnostic the distributional metric is structurally blind to: a run can match the human option
# distribution well while every persona gives the same answer. One home for the formulas because
# two separate scorers in the predecessor project both needed them, and when each kept its own copy
# the two DIVERGED: one normalized multi by `2 ** len(lists[0])`, the first respondent's answer
# length, making `normalized_h` row-order dependent and > 1.

# Collapse cut for H_syn/H_hum. A ratio gate, not a raw-gap gate: a raw threshold selects on "wide
# scale," not "collapsed," and misses a three-option question with 77% human mass (gap -1.00, TVD
# 0.227, 8th best of 40, every one of 1500 personas answering "Yes") at any cut tight enough to be
# selective, because such a question has little entropy available to lose. Measured over the 5
# total-collapse questions: raw <= -1.0 catches 4/5, raw <= -1.4 catches 3/5, ratio <= 0.3 catches
# 5/5, flagging 10 of 40.
#
# Fixed at 0.30 on a calibration fold of a private predecessor survey, where the value is not
# knife-edge: over the 56 gate-eligible questions the ratios have a gap from 0.2989 to 0.3477, so
# ANY cut in (0.299, 0.347] flags the same 9 questions. Only lowering it moves the set (0.25 and
# 0.20 both flag 7). Calibrated on that fold only, deliberately: tuning a gate on the held-out fold
# would stop it being held out. Not re-derived for Twin-2K.
COLLAPSE_RATIO_MAX = 0.30

KL_SMOOTHING_EPS        = 1e-4   # added to LLM probs before KL to keep it finite
KL_BLIND_SPOT_HUMAN_MIN = 0.05   # human rate >= this = "option humans use"
KL_BLIND_SPOT_LLM_MAX   = 0.01   # LLM rate < this = "LLM doesn't know it"

# The cut on `blind_spot_worst`: the SEVERITY of the worst missed option, not the boolean flag.
# The boolean cannot gate: at the 5%/1% definition above it fires on 36 of the reference run's 56
# gate-eligible questions (multi 7/16, nominal 11/18, ordinal 18/22), and a gate that fails 64% of
# its own reference run is a gate the loop learns to skip. The severities separate where the flag
# does not: sorted descending they run 0.4419, 0.3910, 0.3541, 0.3448, 0.3200, 0.3190, 0.3171,
# 0.3030, 0.3010, then GAP 0.046, then 0.2551, 0.2542, 0.2464 … so any cut in (0.2551, 0.3010]
# flags the same 9 questions (5 nominal, 4 ordinal, 0 multi; multi's worst is 0.2551).
# Read it as: an answer more than 30% of humans gave that the LLM essentially never produces.
# Not redundant with the collapse cut: only 4 of those 9 also collapse, and one question collapses at
# ratio 0.2989 with no blind spot at all. Calibrated on that same fold only, same reason.
BLIND_SPOT_WORST_MAX = 0.30

# Below this many valid respondents a question is REPORTED but never GATED.
# Routing thins the panel unevenly: measured on that fold (1050 respondents), two routing-thinned
# questions scored on 3 and 6 rows, while a typical question scored on ~1050. The one at n=6 was
# flagged as collapsed, where zero synthetic entropy over 6 draws is sampling noise, not
# diversity collapse. 50 was that survey's reporting floor, and independently the
# smallest round cut that clears the routing-thinned grid on every fold. Unlike the collapse
# ratio it is not revisited when the reference run is scored.
MIN_N_FOR_GATING = 50

# Guard on the combinatorial ceiling: 2**K explodes for large option counts and log2 n binds long
# before it does (log2(1500) = 10.55, so any K >= 11 is already irrelevant).
_MAX_CEILING_OPTIONS = 20


def _shannon(probabilities) -> float:
    """H = -sum(p log2 p) in bits. Zero-probability terms contribute 0, by convention.

    The `+ 0.0` is not decoration: a fully collapsed distribution (single p=1.0) gives -(1.0*0.0)
    = **-0.0**, which then prints as `-0.000` and makes a total collapse look like a negative
    entropy. Normalizing here keeps every downstream ratio and gap signed correctly.

    Private: callers pass responses or a distribution, never a hand-built probability vector.
    """
    return -sum(p * math.log2(p) for p in probabilities if p > 0) + 0.0


def optionwise_entropy(
    distribution: Dict[str, Any], n_options: int
) -> Tuple[float, float]:
    """(H, ceiling) over an option distribution, from the `percentages` dict already built.

    Fed straight from `calculate_response_distribution`, so no distribution is computed here.
    Ceiling is log2(K) for K options — 1.585 bits for a 3-option question, 2.585 for a 6-point
    scale. Returned alongside H rather than exposed separately so no caller can pair an
    option-wise entropy with a set-wise ceiling.
    """
    h = _shannon(list((distribution or {}).get("percentages", {}).values()))
    ceiling = math.log2(n_options) if n_options and n_options > 1 else 1.0
    return h, ceiling


def setwise_entropy(
    responses: List[Any], n_options: int
) -> Tuple[float, float, int, float]:
    """(H, ceiling, n_distinct, top_share) over frozen answer *sets*, for multi-select.

    Marginal prevalences sum to mean-k (~2.8 on Q19), not to 1, so -sum(p log p) over them is not
    an entropy of anything — never feed this a `percentages` dict. Over answer sets it is
    well-defined, and it measures exactly the joint structure marginal MAD is structurally blind
    to: Q19 scores MAD 0.090 (near the top of its bucket) while 1500 personas produced only 5
    distinct answer sets.

    Ceiling is min(log2 n, log2(2^K - 1)) — the sample limit or the combinatorial one, whichever
    binds — never log2 K, and never anything derived from an individual response. It depends only
    on (n, K), so it is invariant to row order; `2 ** len(responses[0])` is the bug this replaces
    (4 people / 3 options, maximal diversity: that form yields normalized_h = 2.0 in one row order
    and 1.0 in another).

    So set-wise and option-wise entropies sit on different scales and are never averaged together;
    they stay in separate rollup keys, tagged by `entropy_kind`.
    """
    n = len(responses)
    if n == 0:
        return 0.0, 1.0, 0, 0.0
    sets = Counter(
        tuple(sorted(r)) if isinstance(r, list) else (str(r),) for r in responses
    )
    probabilities = [count / n for count in sets.values()]
    max_sets = 2 ** min(max(int(n_options or 0), 1), _MAX_CEILING_OPTIONS) - 1
    ceiling = min(math.log2(max(n, 2)), math.log2(max(max_sets, 2)))
    return _shannon(probabilities), ceiling, len(sets), max(sets.values()) / n


def entropy_pair_for_bucket(
    synthetic_list: List[Any],
    ground_truth_list: List[Any],
    metric_bucket: str,
    n_options: int,
    all_options: Optional[List[str]] = None,
    min_n_for_gating: Optional[int] = None,
) -> Dict[str, Any]:
    """H(synthetic) vs H(human) for one set of pairs, dispatched on the bucket.

    The single place that decides set-wise vs option-wise, so the overall row and the per-segment
    rows cannot disagree about which entropy a question gets — two copies drifting apart is the bug
    this module exists to have fixed once.

    Returns {} for `open_ended`: entropy over free text is log2(n) by construction, measuring string
    uniqueness rather than response diversity.
    """
    if metric_bucket == "open_ended":
        return {}

    if metric_bucket == "multi":
        h_syn, ceiling, n_sets_syn, top_share = setwise_entropy(synthetic_list, n_options)
        h_hum, _, n_sets_hum, _ = setwise_entropy(ground_truth_list, n_options)
        extra = {
            "entropy_kind": "setwise",
            "n_sets_syn": n_sets_syn,
            "n_sets_hum": n_sets_hum,
            "top_set_share": round(top_share, 4),
        }
    else:
        qtype = _bucket_to_qtype(metric_bucket)
        h_syn, ceiling = optionwise_entropy(
            calculate_response_distribution(synthetic_list, qtype), n_options
        )
        h_hum, _ = optionwise_entropy(
            calculate_response_distribution(ground_truth_list, qtype), n_options
        )
        extra = {"entropy_kind": "optionwise"}

    h_syn = round(h_syn, 4)
    h_hum = round(h_hum, 4)
    # A question whose humans have no entropy cannot lose any, so the ratio is undefined rather
    # than 0 — reporting 0.0 there would flag a collapse it cannot be.
    ratio = round(h_syn / h_hum, 4) if h_hum > 0 else None

    kl_fields: Dict[str, Any] = {"kl": None, "blind_spot": None, "blind_spot_worst": None,
                                  "blind_spot_options": None, "kl_thin": False}
    # Ordinal is in for the blind-spot flag and out for KL — the split is inside
    # `kl_and_blind_spot`, which returns kl=None for it. `open_ended` returned above.
    if metric_bucket in ("nominal", "multi", "ordinal") and all_options:
        qtype = _bucket_to_qtype(metric_bucket)
        syn_pct = calculate_response_distribution(synthetic_list, qtype).get("percentages", {})
        gt_pct  = calculate_response_distribution(ground_truth_list, qtype).get("percentages", {})
        kl_fields = kl_and_blind_spot(gt_pct, syn_pct, all_options,
                                      bucket=metric_bucket, n=len(synthetic_list),
                                      min_n_for_gating=min_n_for_gating)

    return {
        "h_syn": h_syn,
        "h_hum": h_hum,
        "h_ceiling": round(ceiling, 4),
        "entropy_gap": round(h_syn - h_hum, 4),
        "entropy_ratio": ratio,
        **extra,
        **kl_fields,
    }


def _distributional_metric_for_pairs(
    synthetic_list: List[Any],
    ground_truth_list: List[Any],
    metric_bucket: str,
    all_options: List[str],
) -> Tuple[float, str]:
    """Return (metric_value, metric_name)."""
    syn_dist = calculate_response_distribution(synthetic_list, _bucket_to_qtype(metric_bucket))
    gt_dist = calculate_response_distribution(ground_truth_list, _bucket_to_qtype(metric_bucket))
    syn_pct = syn_dist.get("percentages", {})
    gt_pct = gt_dist.get("percentages", {})

    if metric_bucket == "ordinal":
        return wasserstein_1_scale(synthetic_list, ground_truth_list, all_options), "wasserstein_1"
    if metric_bucket == "multi":
        return marginal_prevalence_distance(synthetic_list, ground_truth_list, all_options), "marginal_prevalence_mad"
    return total_variation_distance(syn_pct, gt_pct, all_options), "tvd"


def _bucket_to_qtype(metric_bucket: str) -> str:
    return "multi" if metric_bucket == "multi" else "single"


def _individual_baseline_for_pairs(
    synthetic_list: List[Any],
    ground_truth_list: List[Any],
    metric_bucket: str,
    all_options: List[str],
) -> float:
    if metric_bucket == "ordinal":
        return mae_scale_steps(synthetic_list, ground_truth_list, all_options)
    if metric_bucket == "multi":
        return _agreement_rate_multi(synthetic_list, ground_truth_list)
    return _agreement_rate_single(synthetic_list, ground_truth_list)


def individual_baseline_name(metric_bucket: str) -> str:
    """Name the metric `_individual_baseline_for_pairs` returns for this bucket.

    A bare `individual_baseline=0.914` is ambiguous in a way the distributional half is not:
    on `nominal`/`multi` it is an exact-match rate where higher is better, on `ordinal` it is
    a mean error in scale steps where LOWER is better. Reading one as the other inverts the
    result. Kept as a function of `metric_bucket` rather than a field beside the value,
    because it is derivable from a column the summary sheet already carries — the rule
    `excel_exporter.py` states where it omits `entropy_kind` for the same reason. Mirrors the
    dispatch above; keep the two in step.
    """
    if metric_bucket == "ordinal":
        return "individual_mae_steps"
    return "individual_exact_match"


def _is_error_response(synthetic: Any) -> bool:
    """Return True if synthetic response represents an LLM/processing failure."""
    if synthetic == "Error":
        return True
    if isinstance(synthetic, list) and synthetic == ["Error"]:
        return True
    return False


def _filter_valid_pairs(synthetic_list: List[Any], ground_truth_list: List[Any]):
    """Exclude Error responses from validation pairs."""
    valid_synthetic = []
    valid_ground_truth = []
    n_failed = 0
    for synthetic, ground_truth in zip(synthetic_list, ground_truth_list):
        if _is_error_response(synthetic):
            n_failed += 1
            continue
        valid_synthetic.append(synthetic)
        valid_ground_truth.append(ground_truth)
    return valid_synthetic, valid_ground_truth, n_failed


def validate_single_choice(synthetic: str, ground_truth: str) -> bool:
    """Validate single choice response (exact match)"""
    if synthetic == "Error" or ground_truth is None:
        return False
    return synthetic == ground_truth


def validate_multi_choice(synthetic: List[str], ground_truth: List[str]) -> float:
    """Validate multi-choice response using Jaccard similarity"""
    if not synthetic or not ground_truth:
        return 0.0

    synthetic_set = set(synthetic)
    ground_truth_set = set(ground_truth)
    intersection = len(synthetic_set & ground_truth_set)
    union = len(synthetic_set | ground_truth_set)
    return intersection / union if union > 0 else 0.0


def _agreement_rate_single(synthetic_list: List[str],
                           ground_truth_list: List[str]) -> float:
    """Mean exact-match rate for single-choice pairs (caller filters errors)."""
    if len(synthetic_list) != len(ground_truth_list):
        raise ValueError("Synthetic and ground truth lists must have same length")

    if not synthetic_list:
        return 0.0

    matches = sum(1 for s, g in zip(synthetic_list, ground_truth_list)
                  if validate_single_choice(s, g))
    return matches / len(synthetic_list)


def _agreement_rate_multi(synthetic_list: List[List[str]],
                          ground_truth_list: List[List[str]]) -> float:
    """Mean Jaccard similarity for multi-choice pairs (caller filters errors)."""
    if len(synthetic_list) != len(ground_truth_list):
        raise ValueError("Synthetic and ground truth lists must have same length")

    if not synthetic_list:
        return 0.0

    similarities = [validate_multi_choice(s, g)
                    for s, g in zip(synthetic_list, ground_truth_list)]
    return sum(similarities) / len(similarities)


def validate_by_segment(synthetic_list: List[Any],
                        ground_truth_list: List[Any],
                        segment_values: List[str],
                        metric_bucket: str = "nominal",
                        all_options: Optional[List[str]] = None,
                        min_n_for_gating: Optional[int] = None) -> Dict[str, Dict[str, float]]:
    """Distributional metric + entropy pair by segment (individual baseline is aggregate-only).

    Entropy belongs here precisely because the distributional metric is blind to it: a segment can
    match its humans' option distribution while every persona in it gave the same answer. It is
    also the paper's finding 10 — alignment to a subgroup is close to linear in that subgroup's own
    entropy, so `h_hum` per segment is what makes a fidelity ordering interpretable.

    No `collapse` flag and no normalized column here. Segment n is usually below MIN_N_FOR_GATING,
    so a flag would be suppressed on nearly every row; and set-wise ceilings depend on n, which
    varies by segment, so a normalized value would not be comparable across segments. `entropy_ratio`
    is — it compares synthetic against human at the same n.
    """
    segments = {}

    for synthetic, ground_truth, segment in zip(synthetic_list, ground_truth_list, segment_values):
        if segment not in segments:
            segments[segment] = {"synthetic": [], "ground_truth": []}
        segments[segment]["synthetic"].append(synthetic)
        segments[segment]["ground_truth"].append(ground_truth)

    segment_results = {}
    for segment, data in segments.items():
        syn, gt, _ = _filter_valid_pairs(data["synthetic"], data["ground_truth"])
        n = len(syn)
        if n == 0:
            continue

        options = all_options or []
        dist_value, dist_name = _distributional_metric_for_pairs(
            syn, gt, metric_bucket, options
        )

        entropy = entropy_pair_for_bucket(syn, gt, metric_bucket, len(options), all_options=options,
                                          min_n_for_gating=min_n_for_gating)
        segment_results[segment] = {
            "n": n,
            "distributional_metric": dist_value,
            "distributional_metric_name": dist_name,
            "h_syn": entropy.get("h_syn"),
            "h_hum": entropy.get("h_hum"),
            "entropy_ratio": entropy.get("entropy_ratio"),
            "kl":               entropy.get("kl"),
            "blind_spot":       entropy.get("blind_spot"),
            "blind_spot_worst": entropy.get("blind_spot_worst"),
            "kl_thin":          entropy.get("kl_thin"),
        }

    return segment_results


def calculate_response_distribution(responses: List[Any], question_type: str = "single") -> Dict[str, Dict[str, float]]:
    """Calculate distribution of responses (% selecting each option)"""
    if not responses:
        return {'counts': {}, 'percentages': {}, 'n': 0}

    n = len(responses)

    if question_type in ("single", "open_ended"):
        counter = Counter(responses)
        counts = dict(counter)
        percentages = {option: count / n for option, count in counts.items()}
    else:
        all_options = []
        for response in responses:
            if isinstance(response, list):
                all_options.extend(response)
            elif response:
                all_options.append(response)
        counter = Counter(all_options)
        counts = dict(counter)
        percentages = {option: count / n for option, count in counts.items()}

    return {'counts': counts, 'percentages': percentages, 'n': n}


def calculate_phi_correlation(synthetic_list: List[Any],
                               ground_truth_list: List[Any],
                               all_options: List[str],
                               question_type: str = "single") -> Dict[str, Dict[str, Any]]:
    """Calculate phi (Pearson) correlation for each option vs human/LLM selection.

    The margin is **across respondents within one option** — the loop below zips over people
    with the question and option held fixed. That cancels the option's base rate, leaving only
    between-person variance, so these values are directly comparable to published
    across-participants figures (Peng r=0.20) and *not* to across-questions-within-participant
    ones (Park 0.83). Measured on a separate panel, the latter margin scores 0.263 on row-shuffled
    personas versus 0.327 real, i.e. 80% of it is base-rate profile rather than individual
    fidelity.
    """
    n = len(synthetic_list)
    correlations = {}

    for option in all_options:
        human_binary = []
        llm_binary = []

        for synthetic, ground_truth in zip(synthetic_list, ground_truth_list):
            if question_type in ("single", "open_ended"):
                human_binary.append(1 if ground_truth == option else 0)
                llm_binary.append(1 if synthetic == option else 0)
            else:
                human_selected = option in ground_truth if isinstance(ground_truth, list) else False
                llm_selected = option in synthetic if isinstance(synthetic, list) else False
                human_binary.append(1 if human_selected else 0)
                llm_binary.append(1 if llm_selected else 0)

        n_human_selected = sum(human_binary)
        n_llm_selected = sum(llm_binary)
        pct_human = n_human_selected / n if n > 0 else 0
        pct_llm = n_llm_selected / n if n > 0 else 0

        correlation = None
        interpretation = "N/A"

        try:
            if len(set(human_binary)) <= 1 or len(set(llm_binary)) <= 1:
                correlation = None
                interpretation = "Insufficient variance"
            elif n_human_selected == 0 and n_llm_selected == 0:
                correlation = 1.0
                interpretation = "Perfect agreement (both never select)"
            elif n_human_selected == n and n_llm_selected == n:
                correlation = 1.0
                interpretation = "Perfect agreement (both always select)"
            else:
                correlation = np.corrcoef(human_binary, llm_binary)[0, 1]
                if correlation >= 0.7:
                    interpretation = "Strong agreement"
                elif correlation >= 0.4:
                    interpretation = "Moderate agreement"
                elif correlation >= 0.1:
                    interpretation = "Weak agreement"
                elif correlation >= -0.1:
                    interpretation = "No correlation"
                elif correlation >= -0.4:
                    interpretation = "Weak disagreement"
                else:
                    interpretation = "Strong disagreement"
        except Exception as e:
            correlation = None
            interpretation = f"Calculation error: {str(e)}"

        correlations[option] = {
            'correlation': correlation,
            'n_human_selected': n_human_selected,
            'n_llm_selected': n_llm_selected,
            'pct_human': pct_human,
            'pct_llm': pct_llm,
            'interpretation': interpretation
        }

    return correlations


class ValidationResult:
    """Container for validation results"""

    def __init__(self, question_id: str, question_type: str,
                 min_n_for_gating: int = MIN_N_FOR_GATING):
        self.question_id = question_id
        self.question_type = question_type
        # Held on the instance so the overall row and every segment row cannot use different
        # floors -- the same reason the entropy formulas live in one shared function.
        self.min_n_for_gating = min_n_for_gating
        self.metric_bucket = classify_metric_bucket(question_type)
        self.synthetic = []
        self.ground_truth = []
        self.agreement_rate = None
        self.individual_baseline = None
        self.distributional_metric = None
        self.distributional_metric_name = None
        self.n = 0
        self.n_valid = 0
        self.n_failed = 0
        self.segment_results = {}
        self.synthetic_distribution = {}
        self.ground_truth_distribution = {}
        self.all_options = []
        # Entropy diagnostic (see `_calculate_entropy`). Defined here so a result that never ran
        # `calculate_overall` still has readable attributes — the Excel exporter reads them
        # unconditionally.
        self.h_syn = None
        self.h_hum = None
        self.h_ceiling = None
        self.entropy_gap = None
        self.entropy_ratio = None
        self.entropy_kind = None
        self.entropy_thin = None
        self.collapse = None
        self.n_sets_syn = None
        self.n_sets_hum = None
        self.top_set_share = None
        self.kl = None
        self.blind_spot = None
        self.blind_spot_worst = None
        self.blind_spot_options = None
        self.kl_thin = False

    def calculate_overall(self, all_options: List[str] = None, ordered_scale: bool = False):
        """Calculate aggregate distributional + individual-baseline metrics."""
        self.metric_bucket = classify_metric_bucket(self.question_type, ordered_scale)
        valid_synthetic, valid_ground_truth, self.n_failed = _filter_valid_pairs(
            self.synthetic, self.ground_truth
        )
        self.n_valid = len(valid_synthetic)
        self.n = self.n_valid

        if all_options:
            self.all_options = all_options

        if self.n_valid == 0:
            self.agreement_rate = 0.0
            self.individual_baseline = 0.0
            self.distributional_metric = 0.0
            self._calculate_entropy([], [])
            return

        options = self.all_options or []
        self.distributional_metric, self.distributional_metric_name = (
            _distributional_metric_for_pairs(
                valid_synthetic, valid_ground_truth, self.metric_bucket, options
            )
        )
        self.individual_baseline = _individual_baseline_for_pairs(
            valid_synthetic, valid_ground_truth, self.metric_bucket, options
        )

        # Legacy field: exact-match / Jaccard (ordinal uses MAE in individual_baseline).
        if self.metric_bucket == "ordinal":
            self.agreement_rate = _agreement_rate_single(valid_synthetic, valid_ground_truth)
        else:
            self.agreement_rate = self.individual_baseline

        self.synthetic_distribution = calculate_response_distribution(
            valid_synthetic, self.question_type
        )
        self.ground_truth_distribution = calculate_response_distribution(
            valid_ground_truth, self.question_type
        )

        self._calculate_entropy(valid_synthetic, valid_ground_truth)

    def _calculate_entropy(
        self, valid_synthetic: List[Any], valid_ground_truth: List[Any]
    ) -> None:
        """Entropy of the synthetic answers against the humans', for this question.

        Catches what the distributional metric cannot: a run can match the human option
        distribution well while every persona answers identically. The bucket dispatch and the
        formulas live in `entropy_pair_for_bucket`, shared with the per-segment path; only the
        gating decision below is specific to the overall row.
        """
        fields = entropy_pair_for_bucket(
            valid_synthetic,
            valid_ground_truth,
            self.metric_bucket,
            len(self.all_options),
            all_options=self.all_options,
            min_n_for_gating=self.min_n_for_gating,
        )
        if not fields:  # open_ended — the attributes stay None
            return

        for name, value in fields.items():
            setattr(self, name, value)

        # Thin questions are still REPORTED; only the flag is suppressed, because an entropy ratio
        # over a handful of draws cannot distinguish collapse from sampling noise.
        self.entropy_thin = int(self.n_valid) < self.min_n_for_gating
        self.collapse = (
            not self.entropy_thin
            and self.entropy_ratio is not None
            and self.entropy_ratio <= COLLAPSE_RATIO_MAX
        )

    def calculate_segments(self, demographic_key: str, segment_values: List[str]):
        """Calculate distributional metrics by demographic segment."""
        if len(segment_values) != len(self.synthetic):
            raise ValueError(
                f"segment_values length ({len(segment_values)}) must match "
                f"synthetic length ({len(self.synthetic)})"
            )

        self.segment_results[demographic_key] = validate_by_segment(
            self.synthetic,
            self.ground_truth,
            segment_values,
            metric_bucket=self.metric_bucket,
            all_options=self.all_options,
            min_n_for_gating=self.min_n_for_gating,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "question_id": self.question_id,
            "question_type": self.question_type,
            "metric_bucket": self.metric_bucket,
            "distributional_metric": self.distributional_metric,
            "distributional_metric_name": self.distributional_metric_name,
            "individual_baseline": self.individual_baseline,
            "agreement_rate": self.agreement_rate,
            "n": self.n,
            "n_valid": self.n_valid,
            "n_failed": self.n_failed,
            "segment_results": self.segment_results,
            "synthetic_distribution": self.synthetic_distribution,
            "ground_truth_distribution": self.ground_truth_distribution,
            "all_options": self.all_options,
            "h_syn": self.h_syn,
            "h_hum": self.h_hum,
            "h_ceiling": self.h_ceiling,
            "entropy_gap": self.entropy_gap,
            "entropy_ratio": self.entropy_ratio,
            "entropy_kind": self.entropy_kind,
            "entropy_thin": self.entropy_thin,
            "collapse": self.collapse,
            "n_sets_syn": self.n_sets_syn,
            "n_sets_hum": self.n_sets_hum,
            "top_set_share": self.top_set_share,
        }
