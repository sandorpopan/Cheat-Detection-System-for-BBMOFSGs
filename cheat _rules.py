cheat_rules.py

Rule-based (if/else) cheat detection. No ML/AI model is used here by
design - per the project proposal, AI inference was avoided because
it would add too much compute overhead and latency for an online FPS
session. Instead, fixed thresholds are checked directly against the
in-game action logs.

Checked signals:
    - Accuracy: hit-rate that is statistically implausible for human
      reaction/aim (aimbot indicator).
    - Movement speed: player traversal speed exceeding what the game's
      movement system allows (speed hack indicator).
    - Observability distance: a player reacting to / targeting enemies
      that should be outside their normal line of sight or render
      distance (wallhack indicator).

Each check returns a Violation if the threshold is breached. All
violations found in a log batch get bundled into a CheatReport, which
is what gets handed off to the IPFS + smart contract step.

NOTE: thresholds below are placeholders. Calibrate them to your
actual game's movement/weapon stats before relying on this for a
real anti-cheat decision.
"""

from dataclasses import dataclass, field
from typing import List, Optional


# --- thresholds (hardcoded, per project design) -----------------------------

MAX_LEGIT_ACCURACY = 0.65          # hit-rate above this over a sample window is suspicious
MAX_LEGIT_MOVEMENT_SPEED = 7.5     # game units/sec - tune to match character base speed
MAX_LEGIT_VIEW_DISTANCE = 150.0    # game units - max distance a legit target acquisition should occur at


@dataclass
class Violation:
    rule: str
    observed_value: float
    threshold: float
    severity: str  # "low" | "medium" | "high"


@dataclass
class CheatReport:
    player_wallet: str
    session_id: str
    violations: List[Violation] = field(default_factory=list)

    @property
    def is_flagged(self) -> bool:
        return len(self.violations) > 0

    @property
    def severity_score(self) -> int:
        weights = {"low": 1, "medium": 2, "high": 3}
        return sum(weights.get(v.severity, 0) for v in self.violations)


def check_accuracy(shots_fired: int, hits: int) -> Optional[Violation]:
    if shots_fired == 0:
        return None
    accuracy = hits / shots_fired
    if accuracy > MAX_LEGIT_ACCURACY:
        return Violation(
            rule="accuracy_aimbot",
            observed_value=round(accuracy, 3),
            threshold=MAX_LEGIT_ACCURACY,
            severity="high" if accuracy > 0.85 else "medium",
        )
    return None


def check_movement_speed(distance_units: float, time_elapsed_sec: float) -> Optional[Violation]:
    if time_elapsed_sec <= 0:
        return None
    speed = distance_units / time_elapsed_sec
    if speed > MAX_LEGIT_MOVEMENT_SPEED:
        return Violation(
            rule="movement_speedhack",
            observed_value=round(speed, 2),
            threshold=MAX_LEGIT_MOVEMENT_SPEED,
            severity="high" if speed > MAX_LEGIT_MOVEMENT_SPEED * 1.5 else "medium",
        )
    return None


def check_view_distance(target_acquired_distance: float) -> Optional[Violation]:
    if target_acquired_distance > MAX_LEGIT_VIEW_DISTANCE:
        return Violation(
            rule="observability_wallhack",
            observed_value=round(target_acquired_distance, 2),
            threshold=MAX_LEGIT_VIEW_DISTANCE,
            severity="high",
        )
    return None


def evaluate_action_log(player_wallet: str, session_id: str, log: dict) -> CheatReport:
    """
    log is expected to contain aggregated stats for the sampling window, e.g.:
        {
            "shots_fired": int,
            "hits": int,
            "distance_units": float,
            "time_elapsed_sec": float,
            "target_acquired_distance": float,
        }
    """
    report = CheatReport(player_wallet=player_wallet, session_id=session_id)

    checks = [
        check_accuracy(log.get("shots_fired", 0), log.get("hits", 0)),
        check_movement_speed(log.get("distance_units", 0.0), log.get("time_elapsed_sec", 0.0)),
        check_view_distance(log.get("target_acquired_distance", 0.0)),
    ]

    report.violations = [v for v in checks if v is not None]
    return report
