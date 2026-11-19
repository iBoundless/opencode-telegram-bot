from __future__ import annotations

from fnmatch import fnmatchcase

from .opencode.models import Rule

# Order matters: the last matching rule wins, so the ask rules follow the
# broad allow. Every session created by the bot carries this profile.
BOT_SESSION_PERMISSIONS: list[Rule] = [
    Rule(action="*", resource="*", effect="allow"),
    Rule(action="read", resource="*.env", effect="ask"),
    Rule(action="read", resource="*.env.*", effect="ask"),
    Rule(action="shell", resource="*", effect="ask"),
    Rule(action="edit", resource="*", effect="ask"),
    Rule(action="webfetch", resource="*", effect="ask"),
    Rule(action="external_directory", resource="*", effect="ask"),
]


def evaluate(rules: list[Rule], action: str, resource: str) -> str:
    """Return the effective effect using last-match-wins semantics."""
    effect = "deny"
    for rule in rules:
        if fnmatchcase(action, rule.action) and fnmatchcase(resource, rule.resource):
            effect = rule.effect
    return effect
