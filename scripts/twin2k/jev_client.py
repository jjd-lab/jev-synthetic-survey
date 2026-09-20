"""The only place that knows TypeSafe's wire format: one question, one HTTP POST.

Jev is a "System One" model -- it returns a typed answer plus a calibrated probability per option
instead of generating text. That makes it a candidate replacement for the `verbalized_probs`
elicitation measured on an earlier survey, where gpt-4.1 is ASKED to state a distribution and returns
one that does not sum to 1. Here the distribution is the model's native output.

Deliberately `requests` and not the official `typesafe_sdk`, even though the SDK exists and would
hand us retries for free. This repo shares ONE `.venv` across every survey it runs, whose
langchain pins are exact while `pydantic` is `>=2.0.0` and `httpx`/`openai` are transitive and
unpinned -- so `pip install typesafe_sdk` can resolve an upgrade under those surveys and change
their behaviour on the next run, with nothing in this branch's diff to show it. The API is a single
authenticated POST with a JSON body, and the retry/error-classification logic below is wanted
explicitly anyway, so the SDK buys little against that risk. See the plan's "Isolation" section.

PUBLIC DATA ONLY. This is the one code path in the repo that sends prompts outside the company
provider, on a personal key. Twin-2K-500 is CC BY 4.0 and is the ONLY data cleared to reach it.
The caller enforces that (`probe_jev.py`'s config guard) -- this module is the transport.

Wire format, per https://docs.typesafe.ai/api.md and /primitives/choice.md:

    POST https://api.typesafe.ai/v1/systemone
    Authorization: Bearer <key>
    {"state": ..., "model": "jev-1.13.0",
     "questions": {"q": {"type": "choice", "instructions": ..., "criteria": {opt: None, ...}}}}
    -> {"model": ..., "answers": {"q": {"choice": ..., "probabilities": {...}, "confidence": ...}},
        "usage": {"input_tokens": n, "output_tokens": n}}

`criteria` is an OBJECT keyed by option label, not a list -- which is why duplicate option labels
are rejected below rather than silently collapsed into one key by the JSON encoder.

A second primitive, per /primitives/noul.md:

    {"questions": {"q": {"type": "noul", "instructions": "<a yes/no condition>",
                         "criteria": {"true": ..., "false": ...}}}}
    -> {"answers": {"q": {"type": "noul", "noul": 0.87}}}

`noul` is P(yes) on its own -- an ABSOLUTE probability, with no option set to be relative to, no
`choice` and (the docs say so outright) no confidence. It exists here because the vendor documents
yes/no items as exactly where `Choice` and `Noul` disagree: their own example gives 0.22 against
0.01 for the same question asked both ways, and a statement plus its negation summing to 1.19. All
65 of Twin's two-option columns were asked as `Choice` in the JC arm, and those are the columns JC
loses to gpt-4.1 on, so the primitive is the leading suspect. `ask_noul` returns the same shape as
`ask_choice` so that nothing downstream branches -- see its docstring for what is derived, not native.

Reachability check (no survey data, one throwaway sentence):
    .venv\\Scripts\\python.exe scripts/twin2k/jev_client.py
"""

import json
from typing import Optional
import os
import random
import re
import time
import urllib.parse

import requests

ENDPOINT = "https://api.typesafe.ai/v1/systemone"

# Pinned, never an alias. The docs are explicit that "an alias moves when a new release ships, so
# the answers behind it can change without a change on your side", and the plan's verdict
# thresholds are fixed against this version. `jev-latest` and `jev-preview` both resolve here today.
MODEL = "jev-1.13.0"

# Documented limits: 64k tokens/request total, 32k for state + the longest question; 250k tokens/sec
# and 1,200 requests/min account-wide. Input-only billing at $0.042/Mtok -- output tokens are free.
CONTEXT_BUDGET_TOTAL = 64_000
CONTEXT_BUDGET_STATE_AND_QUESTION = 32_000
REQUESTS_PER_MINUTE = 1_200
RATE_IN_PER_TOKEN = 0.042e-6

# Only these two are worth retrying: 429 is our own pacing, 529 is theirs. 401 and 422 are
# deterministic -- retrying either just burns the rate-limit budget on a request that cannot succeed.
RETRYABLE = frozenset({"rate_limit", "transient"})
MAX_ATTEMPTS = 5

# The question key is ours alone; the docs state "the key is not sent to the underlying model and is
# not used in inference", so a constant is safe and keeps the request byte-identical across cells.
QUESTION_KEY = "q"

# A Noul takes a yes/no condition, not an option set, so the survey's stem cannot be sent alone --
# nothing in it says WHICH answer is being asked about. One line, appended after the stem verbatim:
# everything before it is byte-identical to what the Choice arm sent, so the two arms differ in the
# primitive and nothing else. Phrased so that a high probability means yes, as the docs advise.
NOUL_CONDITION = '{question}\n\nDoes this respondent answer "{target}"?'


class JevError(RuntimeError):
    """A classified failure. `kind` decides whether the caller retries, aborts, or stops the run.

    kinds: rate_limit | transient | auth | context_length | bad_response | network
    """

    def __init__(self, kind: str, message: str, status: int | None = None) -> None:
        super().__init__(f"[{kind}] {message}")
        self.kind = kind
        self.status = status


def approx_tokens(text: str) -> int:
    """Chars/4, a rough estimate used for pacing and cost.

    Only ever used to PREDICT whether a request fits or what it costs. The billed figure comes back
    in `usage.input_tokens`, so nothing downstream depends on this being exact.
    """
    return len(text) // 4


def classify_status(status: int, body: str) -> str:
    """Map an HTTP status onto a retry decision.

    422 is the interesting one: the docs describe it as generic body validation, and do not give
    over-length its own status. An over-long state is a run-design problem (the plan says STOP
    rather than truncate history, because truncating changes the arm) while a malformed body is a
    bug here, so they must not collapse into one kind.
    """
    if status == 429:
        return "rate_limit"
    if status == 529 or status >= 500:
        return "transient"
    if status in (401, 403):
        return "auth"
    if status == 422:
        lowered = body.lower()
        if any(word in lowered for word in ("token", "context", "too long", "too large", "length")):
            return "context_length"
        return "bad_response"
    return "bad_response"



def derive_description(label: str) -> Optional[str]:
    """One option label restated as a claim about this respondent, or None.

    The manipulation of the described-`Choice` arm, in full, and a pure function of the label so
    that no description is ever written by hand. The rule is fixed in
    docs/jev/06-option-descriptions-plan.md and was committed before this code existed:

      1. strip a leading "Yes, " or "No, ";
      2. require what remains to be a first-person clause ("I would ...");
      3. restate it in the third person, as a claim about the question just asked.

    Anything that does not match returns None, which `build_payload` sends as a null description,
    exactly as the undescribed arms did. Falling through is the point: a fallback that invented
    wording would be a second, unstated manipulation. On the shipped instrument this derives both
    labels of the 40 pricing columns and nothing else -- the other 25 two-option columns carry bare
    tokens ("more", "the small tray") that cannot be restated without adding meaning.
    """
    stripped = re.sub(r"^(Yes|No),\s*", "", label.strip())
    match = re.match(r"^I\s+(\S.*)$", stripped)
    if not match:
        return None
    return (
        f"This respondent {match.group(1)}, for the situation described in the question."
    )

class JevClient:
    """One HTTP session, reused. Thread-safe enough for the probe's use: `requests.Session` is
    documented as not guaranteed thread-safe, so the probe gives each worker thread its own client
    rather than sharing one across its persona pool.
    """

    def __init__(self, api_key: str, model: str = MODEL, endpoint: str = ENDPOINT,
                 timeout: float = 60.0, max_attempts: int = MAX_ATTEMPTS) -> None:
        if not api_key:
            raise JevError("auth", "no API key given")
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_attempts = max_attempts
        self._session = requests.Session()
        # Set once on the session, so no call site can accidentally build a request without it --
        # and so the key never appears in a per-call argument that might land in a traceback.
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def build_payload(self, state: str, question: str, options: list[str],
                      descriptions: Optional[dict[str, Optional[str]]] = None) -> dict:
        """The exact JSON body. Separated from `ask_choice` so tests can assert on it offline.

        `descriptions` maps an option label to its `criteria` value. Omitted, every option gets
        `None`, which is what the shipped Jev arms sent -- so the default payload is byte-identical
        to theirs and adding this parameter cannot disturb them. A label absent from the map, or
        mapped to None, also gets `None`.
        """
        if not options:
            raise JevError("bad_response", "no options given")
        if len(set(options)) != len(options):
            # `criteria` is a JSON object keyed by label: two identical labels would silently
            # become one key, and the response would then be missing an option we think we asked
            # about. Loud here beats a quietly shortened distribution.
            raise JevError("bad_response", f"duplicate option labels: {options}")
        if len(options) > 255:
            raise JevError("bad_response", f"{len(options)} options exceeds the documented 255")
        return {
            "state": state,
            "model": self.model,
            "questions": {
                QUESTION_KEY: {
                    "type": "choice",
                    "instructions": question,
                    # None by default: the survey's own option text IS the label, and the docs
                    # sanction null "because the option names are clear on their own". A non-null
                    # description is a deliberate manipulation, derived from the instrument by
                    # `derive_description` and switched on per arm, never invented here.
                    "criteria": {
                        option: (descriptions or {}).get(option) for option in options
                    },
                },
            },
        }

    def ask_choice(self, state: str, question: str, options: list[str],
                   descriptions: Optional[dict[str, Optional[str]]] = None) -> dict:
        """One Choice question against one state.

        Returns {"probs": {label: float}, "choice": label, "confidence": float, "model": str,
                 "input_tokens": int, "latency_ms": int}. `probs` is RAW as returned -- how far a
        source's vector is from summing to 1 is a finding the scorer reports, not something to
        quietly normalise here.
        """
        payload = self.build_payload(state, question, options, descriptions)
        return self._request(
            payload, lambda response, elapsed: self._parse(response, options, elapsed)
        )

    def build_noul_payload(self, state: str, question: str, target: str, other: str) -> dict:
        """The exact JSON body for one Noul. Separated from `ask_noul` for offline assertions."""
        if target == other:
            raise JevError("bad_response", f"noul target equals other: {target!r}")
        return {
            "state": state,
            "model": self.model,
            "questions": {
                QUESTION_KEY: {
                    "type": "noul",
                    "instructions": NOUL_CONDITION.format(question=question, target=target),
                    # The `true`/`false` slots carry the survey's OWN option text -- the same two
                    # strings `build_payload` uses as `criteria` KEYS, moved to the slot this
                    # primitive provides. No invented rubric text, matching the null descriptions
                    # the Choice arm sent; without it a Noul would never name the other side.
                    "criteria": {"true": target, "false": other},
                },
            },
        }

    def ask_noul(self, state: str, question: str, target: str, other: str) -> dict:
        """One Noul on a two-option column: P(this respondent answers `target`).

        Returns the SAME shape as `ask_choice`, so neither the probe's row nor the scorer needs a
        branch. Two of those fields are DERIVED rather than native, and the difference matters when
        reading the results:

          * `probs` is {target: p, other: 1 - p}. It sums to 1 by construction, so the scorer's
            raw-sum diagnostic says nothing about this arm -- and the complement is an assumption
            the vendor explicitly does not guarantee (their statement-plus-negation example sums
            to 1.19). Asking both directions would cost a second call per cell; instead the probe
            randomises which side is the target per respondent, so the asymmetry is measurable
            across a column rather than baked into every cell of it.
          * `choice` is the 0.5 threshold, because Noul returns no choice. The Choice arm chained
            the MODEL's own stated label; this arm can only chain one we compute. That is inherent
            to the primitive, not a shortcut.
        """
        payload = self.build_noul_payload(state, question, target, other)
        return self._request(
            payload, lambda response, elapsed: self._parse_noul(response, target, other, elapsed)
        )

    def _request(self, payload: dict, parse) -> dict:
        """POST one question body, retry only what is worth retrying, parse the 200.

        Shared by both primitives: the retry policy belongs to the transport, not to the question
        type, and a second copy of this loop would be a second chance for the two to drift apart.
        """
        body = json.dumps(payload)
        last: JevError | None = None

        for attempt in range(1, self.max_attempts + 1):
            started = time.monotonic()
            try:
                response = self._session.post(self.endpoint, data=body, timeout=self.timeout)
            except requests.RequestException as exc:
                # Connection-level: transport failed, so the request may never have been seen.
                last = JevError("network", f"{type(exc).__name__}: {exc}")
            else:
                if response.status_code == 200:
                    return parse(response, time.monotonic() - started)
                kind = classify_status(response.status_code, response.text[:2000])
                last = JevError(kind, response.text[:500].strip(), response.status_code)

            if last.kind not in RETRYABLE and last.kind != "network":
                raise last
            if attempt == self.max_attempts:
                break
            # Full jitter: a survey run fires thousands of these from a fixed worker pool, and a
            # synchronised retry after a shared 429 would just reproduce the burst that caused it.
            time.sleep(random.uniform(0, min(2 ** attempt, 32)))

        raise last

    def _answer(self, response) -> tuple[dict, dict]:
        """The envelope's one answer object, or a classified failure. Shared by both parsers."""
        try:
            data = response.json()
        except ValueError as exc:
            raise JevError("bad_response", f"body is not JSON: {exc}") from exc
        answer = (data.get("answers") or {}).get(QUESTION_KEY)
        if not isinstance(answer, dict):
            raise JevError("bad_response", f"no answer under {QUESTION_KEY!r}: {data}")
        return data, answer

    def _meta(self, data: dict, elapsed: float) -> dict:
        """Per-cell provenance every row carries, whichever primitive produced it."""
        usage = data.get("usage") or {}
        return {
            # The version that actually answered, per response -- not the string we asked for.
            # An alias silently moving is exactly what this records.
            "model": data.get("model") or self.model,
            "input_tokens": usage.get("input_tokens"),
            "latency_ms": int(elapsed * 1000),
        }

    def _parse(self, response, options: list[str], elapsed: float) -> dict:
        """Validate the answer against the options we actually sent, then flatten it."""
        data, answer = self._answer(response)
        probs = answer.get("probabilities")
        if not isinstance(probs, dict):
            raise JevError("bad_response", f"probabilities is not an object: {answer}")
        # Exact set equality, both directions. A missing option means a silently truncated
        # distribution; an extra one means the model answered about something we did not ask.
        # Never repair either -- a repaired vector is indistinguishable from a real one downstream.
        if set(probs) != set(options):
            raise JevError(
                "bad_response",
                f"probability keys {sorted(probs)} != options sent {sorted(options)}",
            )
        try:
            probs = {label: float(value) for label, value in probs.items()}
        except (TypeError, ValueError) as exc:
            raise JevError("bad_response", f"non-numeric probability: {probs}") from exc
        choice = answer.get("choice")
        if choice not in probs:
            raise JevError("bad_response", f"choice {choice!r} is not one of the options sent")

        return {
            "probs": probs,
            "choice": choice,
            "confidence": answer.get("confidence"),
            **self._meta(data, elapsed),
        }

    def _parse_noul(self, response, target: str, other: str, elapsed: float) -> dict:
        """One number into the two-option vector the scorer reads. See `ask_noul`."""
        data, answer = self._answer(response)
        if "noul" not in answer:
            raise JevError("bad_response", f"no `noul` value in the answer: {answer}")
        try:
            probability = float(answer["noul"])
        except (TypeError, ValueError) as exc:
            raise JevError("bad_response", f"non-numeric noul: {answer['noul']!r}") from exc
        if not 0.0 <= probability <= 1.0:
            # Documented as P(yes) in [0, 1]. Out of range means the field does not mean what the
            # complement below assumes, so clamping it would manufacture a plausible-looking
            # vector out of a response nobody understands.
            raise JevError("bad_response", f"noul {probability} is outside [0, 1]")
        return {
            "probs": {target: probability, other: 1.0 - probability},
            # `>=` so an exact 0.5 resolves deterministically instead of by dict order -- the same
            # tie-break trap that made the choice-vs-argmax count unstable across runs.
            "choice": target if probability >= 0.5 else other,
            # Noul has none: "Noul does not return a separate confidence value".
            "confidence": None,
            "noul": probability,
            "noul_target": target,
            **self._meta(data, elapsed),
        }


def load_key(env: str | None = None) -> str:
    """The key, from `.env` only. Never returned to a log, a config, a checkpoint or a JSONL row.

    `TYPESAFE_API_KEY` is the SDK's own default name and is checked first; `JEV_KEY` is what this
    machine's `.env` actually holds, so both are accepted rather than making the operator rename it.
    """
    from dotenv import load_dotenv

    load_dotenv()
    names = [env] if env else ["TYPESAFE_API_KEY", "JEV_KEY"]
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    raise SystemExit(f"None of {names} is set in the environment/.env")


def check_endpoint_is_typesafe(endpoint: str) -> None:
    """Refuse a non-TypeSafe host, so `--endpoint` cannot become a data-exfiltration flag."""
    host = urllib.parse.urlparse(endpoint).hostname or ""
    if host != "api.typesafe.ai":
        raise SystemExit(f"endpoint host {host!r} is not api.typesafe.ai — refusing")


def main() -> int:
    """Phase 0 reachability: one authenticated Choice on a throwaway sentence. No survey data.

    A TLS or proxy failure here is a corporate-network matter -- report the exact error and stop;
    do not disable certificate verification or tunnel around it.
    """
    client = JevClient(load_key())
    check_endpoint_is_typesafe(client.endpoint)
    print(f"POST {client.endpoint}  model={client.model}")
    try:
        answer = client.ask_choice(
            state="The parcel arrived two weeks late and the box was crushed.",
            question="Is the customer in this message satisfied or dissatisfied?",
            options=["satisfied", "dissatisfied"],
        )
    except JevError as exc:
        print(f"FAILED  kind={exc.kind}  status={exc.status}\n{exc}")
        return 1
    print(f"OK  choice={answer['choice']!r}  probs={answer['probs']}  "
          f"confidence={answer['confidence']}")
    print(f"    answered by {answer['model']}  input_tokens={answer['input_tokens']}  "
          f"{answer['latency_ms']} ms  sum(probs)={sum(answer['probs'].values()):.6f}")

    # The same question as a Noul, on the same state. This is the vendor's own divergence claim in
    # one line: if these two disagree here, they will disagree on Twin's 65 two-option columns.
    try:
        noul = client.ask_noul(
            state="The parcel arrived two weeks late and the box was crushed.",
            question="Is the customer in this message satisfied or dissatisfied?",
            target="satisfied", other="dissatisfied",
        )
    except JevError as exc:
        print(f"FAILED (noul)  kind={exc.kind}  status={exc.status}\n{exc}")
        return 1
    print(f"OK  noul P({noul['noul_target']!r})={noul['noul']}  -> choice={noul['choice']!r}")
    print(f"    Choice said P({noul['noul_target']!r})="
          f"{answer['probs'].get(noul['noul_target'])}  "
          f"gap={abs((answer['probs'].get(noul['noul_target']) or 0) - noul['noul']):.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
