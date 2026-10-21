#!/usr/bin/env python3
"""Import credit mentions without inferring identities from names."""
import argparse, hashlib, json, sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS films (
 id INTEGER PRIMARY KEY, source_path TEXT NOT NULL UNIQUE, title TEXT);
CREATE TABLE IF NOT EXISTS persons (
 id INTEGER PRIMARY KEY, note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS person_names (
 id INTEGER PRIMARY KEY, person_id INTEGER NOT NULL REFERENCES persons(id),
 name TEXT NOT NULL, source TEXT, UNIQUE(person_id,name));
CREATE TABLE IF NOT EXISTS credit_mentions (
 id INTEGER PRIMARY KEY, film_id INTEGER NOT NULL REFERENCES films(id),
 source_key TEXT NOT NULL, credited_name TEXT NOT NULL, credited_role TEXT NOT NULL,
 category TEXT NOT NULL CHECK(category IN ('cast','crew','acknowledgement','unresolved')),
 original_kind TEXT NOT NULL, evidence_json TEXT NOT NULL,
 person_id INTEGER REFERENCES persons(id),
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(film_id,source_key));
CREATE TABLE IF NOT EXISTS identity_candidates (
 id INTEGER PRIMARY KEY, credit_mention_id INTEGER NOT NULL REFERENCES credit_mentions(id),
 candidate_person_id INTEGER NOT NULL REFERENCES persons(id),
 state TEXT NOT NULL DEFAULT 'candidate_match'
 CHECK(state IN ('candidate_match','verified','rejected_match')),
 reason TEXT NOT NULL, reviewer_note TEXT,
 UNIQUE(credit_mention_id,candidate_person_id));
CREATE INDEX IF NOT EXISTS credit_mentions_name_idx ON credit_mentions(credited_name);
CREATE INDEX IF NOT EXISTS credit_mentions_film_idx ON credit_mentions(film_id,category);
"""

def source_key(interval_index, entry, prefix):
    evidence = entry.get("evidence", [])
    payload = [interval_index, prefix, evidence,
               entry.get("person",entry.get("name")), entry.get("role")]
    return hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode("utf8")).hexdigest()

def load(db, file):
    doc=json.loads(Path(file).read_text(encoding="utf8"))
    film=doc.get("video")
    if not film: raise ValueError("Missing video identifier")
    db.executescript(SCHEMA)
    with db:
        db.execute("INSERT OR IGNORE INTO films(source_path) VALUES (?)",(film,))
        film_id=db.execute("SELECT id FROM films WHERE source_path=?",(film,)).fetchone()[0]
        count=0
        for ix,block in enumerate(doc["intervals"]):
            for entry in block.get("credits",[]):
                kind=entry.get("kind","role")
                cat={"character":"cast","thanks":"acknowledgement"}.get(kind,"crew")
                count+=db.execute(
                    "INSERT OR IGNORE INTO credit_mentions "
                    "(film_id,source_key,credited_name,credited_role,category,original_kind,evidence_json) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (film_id,source_key(ix,entry,"credit"),entry["person"],entry["role"],
                     cat,kind,json.dumps(entry.get("evidence",[]),ensure_ascii=False))
                ).rowcount
            for entry in block.get("review",[]):
                count+=db.execute(
                    "INSERT OR IGNORE INTO credit_mentions "
                    "(film_id,source_key,credited_name,credited_role,category,original_kind,evidence_json) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (film_id,source_key(ix,entry,"review"),
                     entry.get("name","[unreadable]"),entry.get("role","[unresolved]"),
                     "unresolved","review",json.dumps(entry.get("evidence",[]),ensure_ascii=False))
                ).rowcount
    return count

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True,type=Path)
    ap.add_argument("--db",required=True,type=Path)
    args=ap.parse_args()
    args.db.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(args.db) as db:
        added=load(db,args.input)
        total=db.execute("SELECT count(*) FROM credit_mentions").fetchone()[0]
    print(f"Imported {added} new mentions; total={total}; database={args.db}")

if __name__=="__main__": main()
