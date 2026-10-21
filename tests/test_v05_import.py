import json, sqlite3, tempfile, unittest
from pathlib import Path
from credits_v05_import import load

class ImportTest(unittest.TestCase):
    def test_same_name_remains_two_mentions_and_import_idempotent(self):
        doc={"video":"movie.mov","intervals":[{"credits":[
            {"person":"Александр Петров","role":"Актёр","kind":"character","evidence":["a"]},
            {"person":"Александр Петров","role":"Оператор","kind":"role","evidence":["b"]},
            {"person":"Дмитрий Конов","role":"Монтаж","kind":"role","evidence":["c"]}
        ],"review":[{"name":"Игорь Сигаев","evidence":["d"]}]}]}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"data.json"
            path.write_text(json.dumps(doc),encoding="utf8")
            with sqlite3.connect(":memory:") as db:
                self.assertEqual(load(db,path),4)
                self.assertEqual(load(db,path),0)
                self.assertEqual(db.execute(
                    "SELECT count(*) FROM credit_mentions WHERE credited_name=?",
                    ("Александр Петров",)).fetchone()[0],2)
                self.assertEqual(db.execute("SELECT count(*) FROM persons").fetchone()[0],0)
                self.assertEqual(db.execute(
                    "SELECT count(*) FROM credit_mentions WHERE person_id IS NULL").fetchone()[0],4)
                self.assertEqual(db.execute(
                    "SELECT category FROM credit_mentions WHERE credited_name='Игорь Сигаев'"
                ).fetchone()[0],"unresolved")

if __name__=="__main__":unittest.main()
