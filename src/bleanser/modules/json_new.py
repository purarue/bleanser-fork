#!/usr/bin/env python3
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


from bleanser.core.processor import BaseNormaliser
from bleanser.core.utils import Json, delkeys # for convenience...
from bleanser.core.utils import mime


class JsonNormaliser(BaseNormaliser):
    PRUNE_DOMINATED = False

    def cleanup(self, j: Json) -> Json:
        return j

    @contextmanager
    def do_cleanup(self, path: Path, *, wdir: Path) -> Iterator[Path]:
        with self.unpacked(path=path, wdir=wdir) as upath:
            pass
        del path # just to prevent from using by accident

        # TODO maybe, later implement some sort of class variable instead of hardcoding
        # note: deliberately keeping mime check inside do_cleanup, since it's executed in a parallel process
        # otherwise it essentially blocks waiting for all mimes to compute..
        # TODO crap. annoying, sometimes mime determines as text/plain for no reason
        # I guess doesn't matter as much, json.loads is the ultimate check it's ineed json
        # mp = mime(upath)
        # assert mp in {
        #         'application/json',
        # }, mp

        j = json.loads(upath.read_text())
        j = self.cleanup(j)

        # todo copy paste from SqliteNormaliser
        jpath = upath.absolute().resolve()
        cleaned = wdir / Path(*jpath.parts[1:]) / (jpath.name + '-cleaned')
        cleaned.parent.mkdir(parents=True, exist_ok=True)

        with cleaned.open('w') as fo:
            if isinstance(j, list):
                j = {'<toplevel>': j} # meh

            assert isinstance(j, dict), j
            for k, v in j.items():
                if not isinstance(v, list):
                    # something like 'profile' data in hypothesis could be a dict
                    # something like 'notes' in rescuetime could be a scalar (str)
                    v = [v] # meh
                assert isinstance(v, list), (k, v)
                for i in v:
                    print(f'{k} ::: {json.dumps(i, sort_keys=True)}', file=fo)

        # todo meh... see Fileset._union
        # this gives it a bit of a speedup
        from subprocess import check_call
        check_call(['sort', '-o', cleaned, cleaned])

        yield cleaned


if __name__ == '__main__':
    JsonNormaliser.main()


# TODO actually implement some artificial json test
#
def test_nonidempotence(tmp_path: Path) -> None:
    from bleanser.tests.common import hack_attribute, actions
    '''
    Just demonstrates that multiway processing might be
    It's probably going to be very hard to fix, likely finding 'minimal' cover (at least in terms of partial ordering) is NP hard?
    '''

    sets = [
        [],
        ['a'],
        ['a', 'b'],
        [     'b', 'c'],
        ['a', 'b', 'c'],
    ]
    for i, s in enumerate(sets):
        p = tmp_path / f'{i}.json'
        p.write_text(json.dumps(s))

    with hack_attribute(JsonNormaliser, 'MULTIWAY', True), hack_attribute(JsonNormaliser, 'PRUNE_DOMINATED', True):
        paths = list(sorted(tmp_path.glob('*.json')))
        res = actions(paths=paths, Normaliser=JsonNormaliser)

        assert [p.name for p in res.remaining] == [
            '0.json', # keeping as boundary
            '2.json', # keeping because item a has rolled over
            '4.json', # keeping as boundary
        ]

        paths = list(res.remaining)
        res = actions(paths=paths, Normaliser=JsonNormaliser)
        assert [p.name for p in res.remaining] == [
            '0.json',
            # note: 2.json is removed because fully contained in 4.json
            '4.json',
        ]
