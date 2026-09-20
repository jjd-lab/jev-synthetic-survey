"""Persona cache management for reusing generated personas across questions"""

import pandas as pd
from typing import List, Optional
from pathlib import Path


def save_personas_to_excel(personas: List[dict], output_path: str):
    """Save generated personas to Excel for later reuse"""
    print(f"\nSaving {len(personas)} personas to cache: {output_path}")
    # SECURITY-REVIEW: The configured cache path controls a local filesystem write; survey
    # configs are trusted operator input and must not be accepted from untrusted users.
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for persona in personas:
        row = {
            'respid': persona['respid'],
            'response_id': persona['response_id'],
            'screener_summary': persona['screener_summary'],
        }
        for demo_key, demo_value in persona['demographics'].items():
            row[f'demo_{demo_key}'] = demo_value
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_excel(output_path, sheet_name='Personas', index=False)
    print(f"[OK] Personas saved to: {output_path}")


def load_personas_from_excel(
    cache_path: str,
    respondents: List,
) -> Optional[List[dict]]:
    """Load previously generated personas from Excel cache"""
    try:
        if not Path(cache_path).exists():
            print(f"[INFO] No persona cache found at: {cache_path}")
            return None

        print(f"\nLoading personas from cache: {cache_path}")
        df = pd.read_excel(cache_path, sheet_name='Personas')

        required_cols = ['respid', 'response_id', 'screener_summary']
        if not all(col in df.columns for col in required_cols):
            print(f"[WARN] Cache missing required columns, will regenerate personas")
            return None

        respondent_map = {r.respid: r for r in respondents}
        cached_respids = set(df['respid'].values)
        current_respids = set(respondent_map.keys())

        if not current_respids.issubset(cached_respids):
            missing_in_cache = current_respids - cached_respids
            print(f"[WARN] Cache missing {len(missing_in_cache)} requested respondents, will regenerate")
            print(f"  Requested: {len(current_respids)} respondents")
            print(f"  Cached: {len(cached_respids)} respondents")
            return None

        if len(current_respids) < len(cached_respids):
            print(f"[INFO] Using subset of cache: {len(current_respids)} of {len(cached_respids)} personas")

        # Build lookup by respid, then iterate respondents in load order
        cache_by_respid = {}
        for _, row in df.iterrows():
            respid = row['respid']
            if respid not in respondent_map:
                continue

            demographics = {
                col[5:]: row[col]
                for col in df.columns
                if col.startswith('demo_')
            }

            cache_by_respid[respid] = {
                'respid': respid,
                'response_id': row['response_id'],
                'demographics': demographics,
                # Round-trip repair: a persona with no summary is saved as "", which Excel
                # stores as a blank cell and pandas reads back as NaN — a float, and a truthy
                # one, so every `or ""` guard downstream passes it through.
                'screener_summary': '' if pd.isna(row['screener_summary']) else row['screener_summary'],
            }

        personas = []
        for respondent in respondents:
            cached = cache_by_respid.get(respondent.respid)
            if cached is None:
                print(f"[WARN] Cache missing respondent {respondent.respid}, will regenerate personas")
                return None

            personas.append({
                **cached,
                'screener_profile': respondent.screener_profile,
                'ground_truth': respondent.ground_truth,
                # Read from the live respondent, not the cache: the cached sheet holds only
                # demographics and the summary, so piped text and arm assignments can never go
                # stale here. Omitting either would make a cache hit silently drop it.
                'stem_values': respondent.stem_values,
                'condition_assignments': respondent.condition_assignments,
            })

        if len(personas) != len(respondents):
            print(f"[WARN] Persona count ({len(personas)}) != respondent count ({len(respondents)}), will regenerate")
            return None

        print(f"[OK] Loaded {len(personas)} personas from cache")
        return personas

    except Exception as e:
        print(f"[WARN] Failed to load persona cache: {e}")
        print("Will regenerate personas from scratch")
        return None


def get_persona_cache_path(output_dir: str, configured_path: Optional[str] = None) -> str:
    """Resolve an explicit shared cache or the output-local default."""
    return configured_path or f"{output_dir}/persona_cache.xlsx"
