# Knowledge Base — Text Copy

`learned/` holds the committed text copy of every answer that `scripts/dev/ineedtoknow.ps1` has gathered with a local model and verified. It exists so two machines stay in step: the SQLite database that answers questions lives under the workspace root (`.knowledge\knowledge.db`), is per machine, and can always be rebuilt.

- **One markdown file per answer**, named by the hash of its question, so two machines learning different things never conflict.
- **Each file records the content hash of every file its answer cites.** A machine imports a file only while those files still hash the same there; an answer never outlives the code or docs it described. A stale file stays here until the question is learned again (which overwrites it) or `ineedtoknow.ps1 -Prune` deletes it.
- **Curated knowledge has no copy here.** It is cut from the docs themselves (see `CURATED_PATTERNS` in `scripts/library/knowledge/seed.py`), so the docs are its source.
- **Nothing here is written by hand.** A file whose id is not the hash of its question is rejected. To correct an answer, ask again with `-Refresh`.
- **After a pull**, the next `ineedtoknow.ps1` call imports new files; `-Rebuild` recreates the database from scratch.

Reference: `scripts/dev/quick-reference.md`, `dev\ineedtoknow.ps1`.
