"""Keep one copy of each duplicated test fixture: the modules behind ``dev/fixture-dedupe.ps1``.

``references`` resolves the files a fixture names, ``static_paths`` evaluates a test module's path
expressions without running it, ``walks`` finds the fixture directories a test reads whole, ``groups``
finds the groups of one fixture (files and inline literals), ``secret_screen`` runs the model-contract
capture's secret screen over the would-be corpus, ``plan`` places each group's copy and keeps what a
directory read or the screen needs, and ``cli`` lists the plan.
"""
