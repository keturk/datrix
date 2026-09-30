"""The code index: definitions, references, outlines, search and logic-map markers.

An index of every Python file in the workspace repositories, kept in SQLite next to the
checkout it describes (``<workspace>/.code-index/``). Each development machine builds
its own from its own working tree, so the index always matches the code on that
machine, uncommitted edits included, and nothing is ever synchronised between machines.

Every query refreshes the index first: files whose size or modification time changed
are re-hashed, and only files whose content changed are parsed again. Queries never
leave the machine. The one step that does -- asking a local model to summarize modules
(``summaries``) -- runs only when asked for, and its results are cached by content hash
in a separate database that survives index rebuilds.

The logic map lives here too: the index extracts the ``@canonical``/``@pattern``/...
markers with the logic map's own parser and rewrites ``.logic-map/markers.db`` whenever
a refresh changes the marker set, so that database is exactly as fresh as the index.
"""
