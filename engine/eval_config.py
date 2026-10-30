from __future__ import annotations

from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True, slots=True)
class EvalWeights:
    piece_value: int = 1_200
    mobility: int = 8
    capture_opportunity: int = 140
    capture_attack_boost: int = 3
    enemy_capture_threat: int = 170
    enemy_capture_attack_boost: int = 1
    target_diversity: int = 120
    target_attack_boost: int = 2
    enemy_target_threat: int = 150
    inner_ring_control: int = 28
    outer_ring_control: int = 22
    center_control: int = 35
    own_piece_under_threat: int = 250
    enemy_piece_under_threat: int = 210
    endgame_material: int = 220
    endgame_capture_delta: int = 90
    long_no_capture_mobility: int = 4
    long_no_capture_target: int = 60
    repetition_penalty: int = 650
    # Experimental blend with the position matrix on p.124 of Li et al. 2022.
    # Zero preserves every existing profile; 100 uses twice the paper matrix.
    paper_position_blend: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


DEFAULT_EVAL_WEIGHTS = EvalWeights()

# B_tuning.rar / 20260712_run01. This remains a named candidate rather than
# replacing the baseline, so cross-seed validation can compare both settings.
CANDIDATE_015_EVAL_WEIGHTS = EvalWeights(
    piece_value=1_024,
    mobility=8,
    capture_opportunity=139,
    capture_attack_boost=3,
    enemy_capture_threat=172,
    enemy_capture_attack_boost=1,
    target_diversity=132,
    target_attack_boost=2,
    enemy_target_threat=171,
    inner_ring_control=24,
    outer_ring_control=21,
    center_control=41,
    own_piece_under_threat=216,
    enemy_piece_under_threat=226,
    endgame_material=217,
    endgame_capture_delta=89,
    long_no_capture_mobility=4,
    long_no_capture_target=70,
    repetition_penalty=605,
)

# First post-integration candidate selected from the 20260717 tuning screen.
# The source run is retained under benchmarks/tuning/20260717_screen.
CANDIDATE_016_EVAL_WEIGHTS = EvalWeights(
    piece_value=1_238,
    mobility=7,
    capture_opportunity=151,
    capture_attack_boost=3,
    enemy_capture_threat=167,
    enemy_capture_attack_boost=1,
    target_diversity=134,
    target_attack_boost=2,
    enemy_target_threat=145,
    inner_ring_control=29,
    outer_ring_control=20,
    center_control=33,
    own_piece_under_threat=214,
    enemy_piece_under_threat=203,
    endgame_material=236,
    endgame_capture_delta=78,
    long_no_capture_mobility=4,
    long_no_capture_target=66,
    repetition_penalty=653,
)

# Post-TT, no-opening screen (20260717_post_tt_screen).  This candidate is
# intentionally kept separate until cross-seed and 15+0 validation completes.
CANDIDATE_017_EVAL_WEIGHTS = EvalWeights(
    piece_value=1_217,
    mobility=7,
    capture_opportunity=128,
    capture_attack_boost=3,
    enemy_capture_threat=140,
    enemy_capture_attack_boost=1,
    target_diversity=108,
    target_attack_boost=2,
    enemy_target_threat=166,
    inner_ring_control=29,
    outer_ring_control=20,
    center_control=35,
    own_piece_under_threat=260,
    enemy_piece_under_threat=228,
    endgame_material=210,
    endgame_capture_delta=77,
    long_no_capture_mobility=4,
    long_no_capture_target=50,
    repetition_penalty=738,
)

# Explicit role experiment for the second player.  It is intentionally named
# and reproducible so the UI adapter and headless tournament use the same
# configuration rather than maintaining separate ad-hoc replacements.
SOLID_EVAL_WEIGHTS = EvalWeights(
    piece_value=1_300,
    mobility=8,
    capture_opportunity=140,
    capture_attack_boost=3,
    enemy_capture_threat=220,
    enemy_capture_attack_boost=1,
    target_diversity=120,
    target_attack_boost=2,
    enemy_target_threat=150,
    inner_ring_control=28,
    outer_ring_control=22,
    center_control=35,
    own_piece_under_threat=330,
    enemy_piece_under_threat=210,
    endgame_material=220,
    endgame_capture_delta=90,
    long_no_capture_mobility=4,
    long_no_capture_target=60,
    repetition_penalty=850,
)

# Phase-2 candidate: repetition & anti-aimless-wandering fix.
# Based on candidate_016; only repetition/long-no-capture parameters changed.
CANDIDATE_018_EVAL_WEIGHTS = EvalWeights(
    piece_value=1_238,
    mobility=7,
    capture_opportunity=151,
    capture_attack_boost=3,
    enemy_capture_threat=167,
    enemy_capture_attack_boost=1,
    target_diversity=134,
    target_attack_boost=2,
    enemy_target_threat=145,
    inner_ring_control=29,
    outer_ring_control=20,
    center_control=33,
    own_piece_under_threat=214,
    enemy_piece_under_threat=203,
    endgame_material=236,
    endgame_capture_delta=78,
    long_no_capture_mobility=8,       # was 4: encourage mobility in stale positions
    long_no_capture_target=90,        # was 66: stronger incentive to find captures
    repetition_penalty=850,           # was 653: stronger penalty for revisiting positions
)


PAPER_2022_EVAL_WEIGHTS = replace(CANDIDATE_016_EVAL_WEIGHTS, paper_position_blend=50)


EVAL_PROFILES: dict[str, EvalWeights] = {
    "baseline": DEFAULT_EVAL_WEIGHTS,
    "candidate_015": CANDIDATE_015_EVAL_WEIGHTS,
    "candidate_016": CANDIDATE_016_EVAL_WEIGHTS,
    "candidate_017": CANDIDATE_017_EVAL_WEIGHTS,
    "candidate_018": CANDIDATE_018_EVAL_WEIGHTS,
    "solid": SOLID_EVAL_WEIGHTS,
    "paper_2022": PAPER_2022_EVAL_WEIGHTS,
}


def get_eval_weights(profile: str = "baseline") -> EvalWeights:
    """Return a named, immutable evaluation profile for a reproducible run."""
    try:
        return EVAL_PROFILES[profile]
    except KeyError as error:
        available = ", ".join(sorted(EVAL_PROFILES))
        raise ValueError(f"unknown evaluation profile {profile!r}; choose one of: {available}") from error
