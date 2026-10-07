# Benoit Saint-Moulin
# Traktor Bridge : undo and redo of the cue edits, shared by the player and the cue timeline

"""Timing snapshots shared by the player and Cue Editor for undo/redo."""

from __future__ import annotations

from ..model import Cue, Track

DEPTH = 100          # steps kept per track
TRACKS = 32          # tracks whose history is kept

_hist: dict[int, tuple[Track, list, list]] = {}      # id(track) -> (track, undo, redo)
_edits: dict[int, int] = {}                           # id(track) -> edits recorded so far


def edits(t: Track) -> int:
    """Edit counter, unchanged by undo/redo so windows can distinguish new edits."""
    return _edits.get(id(t), 0)


def snap(t: Track) -> tuple:
    cues = tuple((c.name, c.kind, c.start, c.length, c.hotcue, c.color) for c in t.cues)
    return cues, t.bpm, t.grid


def _entry(t: Track):
    e = _hist.pop(id(t), None) or (t, [], [])
    _hist[id(t)] = e  # Reinsertion keeps the most recently used track last.
    while len(_hist) > TRACKS:
        _edits.pop(id(_hist.pop(next(iter(_hist)))[0]), None)
    return e


def record(t: Track, before: tuple):
    """Call with snap(t) taken before an edit; unchanged timing states are ignored."""
    if before == snap(t):
        return
    _, undo, redo = _entry(t)
    undo.append(before)
    del undo[:-DEPTH]
    redo.clear()
    _edits[id(t)] = edits(t) + 1


def mark(t: Track):
    """Call right before an edit, when the whole edit happens after it."""
    _, undo, redo = _entry(t)
    now = snap(t)
    if not undo or undo[-1] != now:
        undo.append(now)
        del undo[:-DEPTH]
        _edits[id(t)] = edits(t) + 1
    redo.clear()


def _restore(t: Track, state: tuple):
    cues, t.bpm, t.grid = state
    if cues != snap(t)[0]:
        t.cues[:] = [Cue(name=n, kind=k, start=s, length=ln, hotcue=h, color=c)
                     for n, k, s, ln, h, c in cues]


def undo(t: Track) -> bool:
    _, u, r = _entry(t)
    if not u:
        return False
    r.append(snap(t))
    _restore(t, u.pop())
    return True


def redo(t: Track) -> bool:
    _, u, r = _entry(t)
    if not r:
        return False
    u.append(snap(t))
    _restore(t, r.pop())
    return True
