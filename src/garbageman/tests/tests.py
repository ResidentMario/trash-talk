import unittest
from shapely.geometry import LineString

import sys; sys.path.append("../")
import garbageman


class TestCut(unittest.TestCase):
    def testSimple(self):
        input = LineString(((0, 0), (1, 0)))
        expected = [LineString(((0, 0), (0.5, 0))), LineString(((0, 0.5), (1, 0)))]
        result = garbageman.pipeline.cut(input, 0.5)

        assert expected[0].equals(result[0])
        import pdb; pdb.set_trace()
        assert expected[1].equals(result[1])
