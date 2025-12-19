"""Backtracking helper to assign role candidates without conflicts."""
from __future__ import annotations

from typing import List, Tuple, Optional
import random

Candidate = Tuple[str, list[str]]  # (label, [players])


def plan_assignments(all_candidates_per_role: List[List[Candidate]]) -> Optional[List[str]]:
    """
    all_candidates_per_role: candidates per role as (label, player-list).
    Returns: list of chosen labels in role order, or None if impossible.
    """
    if not all_candidates_per_role:
        return None

    num_roles = len(all_candidates_per_role)
    role_indices = list(range(num_roles))
    random.shuffle(role_indices)

    assigned_for_role: list[Optional[str]] = [None] * num_roles

    def backtrack(pos: int, used_players: set) -> bool:
        if pos == num_roles:
            return True

        idx = role_indices[pos]
        candidates = list(all_candidates_per_role[idx])
        random.shuffle(candidates)

        for label, players in candidates:
            if any(p in used_players for p in players):
                continue
            assigned_for_role[idx] = label
            new_used = set(used_players)
            new_used.update(players)
            if backtrack(pos + 1, new_used):
                return True
            assigned_for_role[idx] = None

        return False

    if backtrack(0, set()):
        # assigned_for_role may be in shuffled order; restore role order via index.
        return assigned_for_role
    return None
