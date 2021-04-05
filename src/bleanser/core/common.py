from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import NamedTuple, Sequence, Set, List, Iterator, Tuple, Dict

from .utils import assert_never

from more_itertools import pairwise


# meh. get rid of this...
from kython.klogging2 import LazyLogger
logger = LazyLogger(__name__, level='debug')


class CmpResult(Enum):
    DIFFERENT = 'different'
    SAME      = 'same'
    DOMINATES = 'dominates'
    ERROR     = 'error'


class Diff(NamedTuple):
    cmp: CmpResult
    diff: bytes


class Relation(NamedTuple):
    before: Path
    diff: Diff
    after: Path


@dataclass
class Group:
    items: Sequence[Path]
    """
    All items in group are tied via 'domination' relationship
    Which might be either exact equality, or some sort of 'inclusion' relationship
    """

    pivots: Sequence[Path]
    """
    Pivots are the elements that 'define' group.
    In general the pivots contain all other elements in the group
    Sometimes pivots might be redundant, e.g. if we want to keep both boundaries of the group
    """

    # TODO attach diff or something
    # cmp: CmpResult

    def __post_init__(self) -> None:
        sp = set(self.pivots)
        si = set(self.items)
        if len(self.items) != len(si):
            raise RuntimeError(f'duplicate items: {self}')
        if len(self.pivots) != len(sp):
            raise RuntimeError(f'duplicate pivots: {self}')
        # in theory could have more pivots, but shouldn't happen for now
        assert 1 <= len(sp) <= 2, sp
        if not (sp <= si):
            raise RuntimeError(f"pivots aren't fully contained in items: {self}")


@dataclass
class Instruction:
    path: Path
    group: Group
    """
    'Reason' why the path got a certain instruction
    """


@dataclass
class Delete(Instruction):
    pass

@dataclass
class Keep(Instruction):
    pass


class Config(NamedTuple):
    delete_dominated: bool = False
    multiway: bool = False


# TODO config is unused here?? not sure
def groups_to_instructions(groups: Sequence[Group], *, config: Config) -> Sequence[Instruction]:
    assert len(groups) > 0  # not sure...
    # NOTE: using Sequence, not Iterator to ensure more atomic behaviour/earlier sanity checks

    def it() -> Iterator[Instruction]:
        done: Dict[Path, Instruction] = {}

        for group in groups:
            # TODO groups can overlap on their pivots.. but nothing else

            # TODO add split method??
            for i in group.items:
                if i in group.pivots:
                    # pivots might be already emitted py the previous groups
                    pi = done.get(i)
                    if pi is None:
                        keep = Keep(path=i, group=group)
                        yield keep
                        done[i] = keep
                    else:
                        if not isinstance(pi, Keep):
                            raise RuntimeError('{i}: used both as pivot and non-pivot')
                else:
                    if i in done:
                        raise RuntimeError(f'{i}: occurs in multiple groups: {group} AND {done[i]}')
                    assert i not in done, (i, done)
                    deli = Delete(path=i, group=group)
                    yield deli
                    done[i] = deli

    return list(it())


def test_groups_to_instructions() -> None:
    def do(*pp: Sequence[str], config=Config()):
        ppp = [list(map(Path, s)) for s in pp]
        # for this test we assume pivots are just at the edges
        grit = (
            Group(
                items=p,
                pivots=(p[0], p[-1]),
            ) for p in ppp
        )
        res = groups_to_instructions(list(grit), config=config)
        return [(str(p.path), {Keep: 'keep', Delete: 'delete'}[type(p)]) for p in res]

    CR = CmpResult

    assert do(
        ('a', 'b'),
    ) == [
        ('a', 'keep'),
        ('b', 'keep'),
    ]

    assert do(
        ('0', 'a'          ),
        ('a', 'b', 'c', 'd'),
    ) == [
        ('0', 'keep'  ),
        ('a', 'keep'  ),
        ('b', 'delete'),
        ('c', 'delete'),
        ('d', 'keep'  ),
    ]


    # TODO shit. how to test this now?
    # maybe it's the config -- delete both pivots or not? not sure
   #inputs = [
   #    ('a', 'b', CR.SAME     ),
   #    ('b', 'c', CR.DIFFERENT),
   #    ('c', 'd', CR.DOMINATES),
   #    ('d', 'e', CR.SAME     ),
   #    ('e', 'f', CR.DOMINATES),
   #    ('f', 'g', CR.DIFFERENT),
   #    ('g', 'h', CR.SAME     ),
   #]
   #
   #assert do(*inputs) == [
   #    ('a', 'keep'  ),
   #    ('b', 'keep'  ),
   #    ('c', 'keep'  ),
   #    ('d', 'keep'  ),
   #    ('e', 'keep'  ),
   #    ('f', 'keep'  ),
   #    ('g', 'keep'  ),
   #    ('h', 'keep'  ),
   #]
   #
   #assert do(*inputs, config=Config(delete_dominated=True)) == [
   #    ('a', 'keep'  ),
   #    ('b', 'keep'  ),
   #    ('c', 'keep'  ),
   #    ('d', 'delete'),
   #    ('e', 'delete'),
   #    ('f', 'keep'  ),
   #    ('g', 'keep'  ),
   #    ('h', 'keep'  ),
   #]

    import pytest  # type: ignore

    with pytest.raises(RuntimeError, match='duplicate items'):
        # x appears twice in the same group
        do(
            ('a', 'b'),
            ('b', 'x', 'y', 'x', 'd'),
            ('d', 'e'),
        )

    with pytest.raises(RuntimeError, match='multiple groups'):
        # b is duplicate
        do(
            ('a', 'b', 'c'),
            ('c', 'x', 'y', 'b', 'e'),
        )

    with pytest.raises(RuntimeError, match='pivot and non-pivot'):
        # b is uses both a pivot and non-pivot
        do(
            ('x', 'y', 'a'),
            ('a', 'b', 'c'),
            ('b', 'a'),
        )


    # # TODO not sure if should raise... no pivot overlap?
    # with pytest.raises(AssertionError):
    #     do(
    #         ('a', 'b'),
    #         ('c', 'd'),
    #     )
