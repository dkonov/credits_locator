import unittest
from locator import TERMS, score, group_hits, sample_times

class CreditHeuristicsTest(unittest.TestCase):
    def test_inflected_russian_terms(self):
        self.assertGreaterEqual(len(TERMS.findall("Автор сценария и режиссер Наталия Конова")), 2)
    def test_noise_not_credits(self):
        f = {"dark_fraction": .25, "upper_shapes": 12}
        r = {"valid_words": 4, "ocr_lines": 30, "credit_keywords": 0}
        self.assertEqual(score(f, r), 0)
    def test_multi_line_dark(self):
        f = {"dark_fraction": .97, "upper_shapes": 14}
        r = {"valid_words": 20, "ocr_lines": 10, "credit_keywords": 0}
        self.assertGreaterEqual(score(f, r), .6)
    def test_group_hits(self):
        items = [{"time_sec": t, "score": s} for t,s in
                 [(60,.65), (165,.65), (560,.96), (565,1), (570,1), (575,1), (580,1), (585,.8)]]
        found = group_hits(items,.6,7.5,5,591,2)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["start_sec"], 555)
    def test_sampling(self):
        points = sample_times(591, 600, 900, 5, 20)
        self.assertEqual(points[0],0)
        self.assertIn(560,points)

if __name__ == "__main__":
    unittest.main()
