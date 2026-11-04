"""Keep one copy of each duplicated test fixture: the modules behind ``dev/fixture-dedupe.ps1``.

``references`` resolves the files a fixture names, ``static_paths`` evaluates a test module's path
expressions without running it, ``walks`` finds the fixture directories a test reads whole, ``groups``
finds the groups of one fixture (files and inline literals), ``secret_screen`` runs the model-contract
capture's secret screen over the would-be corpus, ``layout`` names where the shared set and its corpus lie,
``follow`` rewrites each reference to reach its file's new place, ``sites`` rewrites each test-module site
reading a copy that leaves to the shared accessor, ``plan`` places each group's copy and keeps what a
directory read, the screen, a copy of other bytes or a reference that cannot follow needs, ``proof`` builds
the write set and proves it over the planned or written tree, ``baseline`` proves each package's semantic
baseline across the write, ``write`` writes, rolls back and records it, and ``cli`` lists or writes the plan.
"""
