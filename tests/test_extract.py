import unittest
from extract_credits import reading_order, consolidate, normalized

def line(text, left, top, right, bottom, confidence=90):
    return {"text":text,"bbox":[left,top,right,bottom],"confidence":confidence}

class ExtractionTest(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalized("Оператор-постановщик"),"операторпостановщик")
    def test_coordinates_preserved(self):
        source=[line("Дмитрий Конов",.6,.4,.9,.43)]
        result, cols=reading_order(source)
        self.assertEqual(result[0]["bbox"],[.6,.4,.9,.43])
        self.assertEqual(cols,1)
    def test_columns(self):
        rows=[]
        for n in range(4):
            rows += [line("Оператор",.1,.1+n*.1,.35,.13+n*.1),
                     line("Иван Петров",.63,.1+n*.1,.89,.13+n*.1)]
        ordered, ncols=reading_order(rows)
        self.assertEqual(ncols,2)
        self.assertTrue(all(p["column"]=="left" for p in ordered[:4]))
        self.assertTrue(all(p["column"]=="right" for p in ordered[4:]))
    def test_deduplicates_consecutive_frames(self):
        a={"time_sec":10,"lines":[dict(line("Наталия Конова",.1,.3,.4,.35),column="full")]}
        b={"time_sec":11,"lines":[dict(line("Наталия Конова",.1,.2,.4,.25),column="full")]}
        merged=consolidate([a,b])
        self.assertEqual(len(merged),1)
        self.assertEqual(merged[0]["observations"],2)
    def test_repeated_credits_distant_not_merged(self):
        a={"time_sec":10,"lines":[dict(line("Наталия Конова",.1,.3,.4,.35),column="full")]}
        b={"time_sec":30,"lines":[dict(line("Наталия Конова",.1,.2,.4,.25),column="full")]}
        self.assertEqual(len(consolidate([a,b])),2)

if __name__=="__main__":
    unittest.main()
