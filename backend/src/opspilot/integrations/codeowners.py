"""Minimal CODEOWNERS parser: gitignore-style patterns, the last matching rule wins."""

import re


def _regex(pattern: str) -> re.Pattern[str]:
    anchored = pattern.startswith("/") or "/" in pattern.rstrip("/")
    body = pattern.strip("/")
    out = ""
    i = 0
    while i < len(body):
        if body.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif body.startswith("**", i):
            out += ".*"
            i += 2
        elif body[i] == "*":
            out += "[^/]*"
            i += 1
        elif body[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(body[i])
            i += 1
    prefix = "" if anchored else "(?:.*/)?"
    return re.compile(f"^{prefix}{out}(?:/.*)?$")


def parse(text: str) -> list[tuple[re.Pattern[str], list[str]]]:
    rules = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        parts = line.split()
        if len(parts) >= 2:
            rules.append((_regex(parts[0]), parts[1:]))
    return rules


def owners_for(rules: list[tuple[re.Pattern[str], list[str]]], path: str) -> list[str]:
    owners: list[str] = []
    for rx, o in rules:
        if rx.match(path):
            owners = o
    return owners
