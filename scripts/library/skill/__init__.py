"""Skill assists: the mechanical phases of agent skills, done by scripts and local models.

Each module here takes over one phase a skill used to spend a Claude model on -- building a
digest, extracting findings, drafting a checklist -- and returns output that a script has
checked (a set comparison, a citation check) or that is plainly marked as a local model's lead.
A verdict is never delegated: the skill still decides. The command line is ``skill/skill_assist.py``
(wrapped by ``scripts/skill/skill-assist.ps1``).
"""
