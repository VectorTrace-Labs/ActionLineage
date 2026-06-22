"""Failure minimization helpers for replay promotion."""

from __future__ import annotations

from collections.abc import Callable

from actionlineage_evals.models import ModelTurn, ToolCall


def minimize_tool_calls(
    turns: tuple[ModelTurn, ...],
    *,
    still_fails: Callable[[tuple[ModelTurn, ...]], bool],
) -> tuple[ModelTurn, ...]:
    """Delta-debug tool calls while preserving a caller-defined failure predicate."""

    if not still_fails(turns):
        return turns
    minimized = list(turns)
    changed = True
    while changed:
        changed = False
        for turn_index, turn in enumerate(tuple(minimized)):
            for call_index, _call in enumerate(turn.tool_calls):
                candidate_calls = tuple(
                    call for index, call in enumerate(turn.tool_calls) if index != call_index
                )
                candidate_turns = tuple(
                    item
                    if index != turn_index
                    else ModelTurn(
                        content=item.content,
                        tool_calls=candidate_calls,
                        provider=item.provider,
                        model_id=item.model_id,
                        request_index=item.request_index,
                        raw=item.raw,
                    )
                    for index, item in enumerate(minimized)
                )
                if still_fails(candidate_turns):
                    minimized = list(candidate_turns)
                    changed = True
                    break
            if changed:
                break
    return tuple(minimized)


def tool_call_count(turns: tuple[ModelTurn, ...]) -> int:
    """Return total tool calls in a transcript."""

    return sum(len(turn.tool_calls) for turn in turns)


def transcript_with_calls(calls: tuple[ToolCall, ...]) -> tuple[ModelTurn, ...]:
    """Build a one-turn transcript for minimizer tests and fixtures."""

    return (
        ModelTurn(
            content="synthetic failing transcript",
            tool_calls=calls,
            provider="replay",
            model_id="replay/minimizer",
            request_index=0,
            raw={},
        ),
    )
