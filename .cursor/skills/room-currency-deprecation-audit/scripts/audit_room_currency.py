#!/usr/bin/env python3
"""Generate a first-pass audit for room/basic-room currency deprecation.

The script is intentionally heuristic and read-only. It favors fast narrowing of
large Java service repositories over perfect semantic analysis.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {
    ".java",
    ".kt",
    ".scala",
    ".proto",
    ".thrift",
    ".avsc",
    ".json",
    ".xml",
    ".yml",
    ".yaml",
    ".properties",
}

IGNORED_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    ".gradle",
    "target",
    "build",
    "out",
    "dist",
    "node_modules",
    "logs",
}

ROOM_RE = re.compile(
    r"(basic[-_\s]*room[-_\s]*type|basicroomtype|room[-_\s]*type|roomtype|"
    r"htlhoteldb[._-]*(roomtype|basicroomtype))",
    re.IGNORECASE,
)
CURRENCY_RE = re.compile(r"\bcurrency\b", re.IGNORECASE)
FIELD_RE = re.compile(
    r"^\s*(?:@\w+(?:\([^)]*\))?\s*)*"
    r"(?:(?:private|protected|public)\s+)?"
    r"(?:(?:static|final|transient|volatile)\s+)*"
    r"[\w.$<>\[\]?,\s]+\s+currency\s*(?:[=;,)])",
    re.IGNORECASE,
)
SCHEMA_FIELD_RE = re.compile(r"(?i)(?:^|\W)(?:currency|\"currency\"|'currency')\s*[:=;]")
SCHEMA_NAME_RE = re.compile(r"""(?i)["']name["']\s*:\s*["']currency["']""")
TYPE_RE = re.compile(r"\b(?:class|interface|record|enum|message)\s+([A-Za-z_]\w*)")
PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;")
METHOD_RE = re.compile(
    r"^\s*(?:(?:public|protected|private|static|final|synchronized|abstract|default|native)\s+)*"
    r"(?:[\w.$<>\[\]?,]+\s+)+([A-Za-z_]\w*)\s*\([^;{}]*\)"
    r"\s*(?:throws\s+[^{]+)?\{"
)


@dataclass(frozen=True)
class Match:
    path: Path
    line_no: int
    text: str


@dataclass
class SourceFile:
    path: Path
    rel_path: str
    lines: list[str]
    package: str = ""
    types: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        if self.types:
            first_type = self.types[0]
            return f"{self.package}.{first_type}" if self.package else first_type
        return self.rel_path

    @property
    def is_room_related(self) -> bool:
        haystack = " ".join([self.rel_path, self.package, *self.types])
        return bool(ROOM_RE.search(haystack))


@dataclass
class MethodEvidence:
    owner: SourceFile
    name: str
    start_line: int
    currency_lines: list[int]
    direct_call_sites: list[Match] = field(default_factory=list)


def iter_source_paths(root: Path, include_tests: bool) -> Iterable[Path]:
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        current = Path(current_root)
        if not include_tests and is_test_path(current.relative_to(root).as_posix()):
            dirnames[:] = []
            continue
        for filename in filenames:
            path = current / filename
            if path.suffix.lower() in TEXT_EXTENSIONS:
                yield path


def is_test_path(path: str) -> bool:
    lowered = path.lower()
    return (
        "/test/" in f"/{lowered}/"
        or "/tests/" in f"/{lowered}/"
        or lowered.startswith("test/")
        or lowered.endswith("test.java")
        or lowered.endswith("tests.java")
    )


def read_source(path: Path, root: Path) -> SourceFile | None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="latin-1")
        except UnicodeDecodeError:
            return None

    lines = text.splitlines()
    package = ""
    types: list[str] = []
    for line in lines:
        if not package:
            package_match = PACKAGE_RE.search(line)
            if package_match:
                package = package_match.group(1)
        type_match = TYPE_RE.search(line)
        if type_match:
            types.append(type_match.group(1))

    return SourceFile(
        path=path,
        rel_path=path.relative_to(root).as_posix(),
        lines=lines,
        package=package,
        types=types,
    )


def classify_usage(line: str) -> str:
    lowered = line.lower()
    if "setcurrency" in lowered or re.search(r"\bcurrency\s*=", lowered):
        return "pass-through/write"
    if "getcurrency" in lowered:
        return "read"
    if SCHEMA_FIELD_RE.search(line) or SCHEMA_NAME_RE.search(line):
        return "schema/serialization"
    if FIELD_RE.search(line):
        return "field definition"
    if ".currency" in lowered:
        return "direct field access"
    return "variable/reference"


def contract_type(source: SourceFile) -> str:
    haystack = f"{source.rel_path} {' '.join(source.types)}".lower()
    if any(token in haystack for token in ("entity", "po.", "dao", "mapper", "mybatis", "jpa")):
        return "DB/entity"
    if any(token in haystack for token in ("redis", "cache")):
        return "Redis/cache"
    if any(token in haystack for token in ("qmq", "message", "event", "mq", "payload")):
        return "QMQ/message"
    if any(token in haystack for token in ("dto", "vo", "response", "request", "client", "remote", "api", "thrift", "proto")):
        return "RPC/remote DTO"
    if source.path.suffix.lower() in {".proto", ".thrift", ".avsc", ".json", ".xml", ".yml", ".yaml"}:
        return "schema/config"
    return "internal/model"


def find_definition_lines(source: SourceFile) -> list[int]:
    lines: list[int] = []
    for index, line in enumerate(source.lines, start=1):
        if not CURRENCY_RE.search(line):
            continue
        if FIELD_RE.search(line) or SCHEMA_FIELD_RE.search(line) or SCHEMA_NAME_RE.search(line):
            lines.append(index)
    return lines


def find_usage_matches(sources: list[SourceFile]) -> list[Match]:
    matches: list[Match] = []
    for source in sources:
        for index, line in enumerate(source.lines, start=1):
            if CURRENCY_RE.search(line):
                matches.append(Match(source.path, index, line.strip()))
    return matches


def brace_delta(line: str) -> int:
    stripped = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
    stripped = re.sub(r"'(?:\\.|[^'\\])*'", "''", stripped)
    return stripped.count("{") - stripped.count("}")


def find_methods_with_currency(source: SourceFile) -> list[MethodEvidence]:
    methods: list[MethodEvidence] = []
    active_name: str | None = None
    active_start = 0
    active_depth = 0
    active_currency_lines: list[int] = []

    for index, line in enumerate(source.lines, start=1):
        if active_name is None:
            match = METHOD_RE.search(line)
            if not match:
                continue
            active_name = match.group(1)
            active_start = index
            active_depth = brace_delta(line)
            active_currency_lines = [index] if CURRENCY_RE.search(line) else []
            if active_depth <= 0:
                if active_currency_lines:
                    methods.append(MethodEvidence(source, active_name, active_start, active_currency_lines))
                active_name = None
            continue

        if CURRENCY_RE.search(line):
            active_currency_lines.append(index)
        active_depth += brace_delta(line)
        if active_depth <= 0:
            if active_currency_lines:
                methods.append(MethodEvidence(source, active_name, active_start, active_currency_lines))
            active_name = None
            active_depth = 0
            active_currency_lines = []

    return methods


def direct_call_sites(method_name: str, sources: list[SourceFile], owner: SourceFile, max_sites: int) -> list[Match]:
    pattern = re.compile(rf"\b{re.escape(method_name)}\s*\(")
    sites: list[Match] = []
    for source in sources:
        for index, line in enumerate(source.lines, start=1):
            if not pattern.search(line):
                continue
            if METHOD_RE.search(line):
                continue
            stripped = line.strip()
            if stripped.startswith(("//", "*")):
                continue
            sites.append(Match(source.path, index, stripped))
            if len(sites) >= max_sites:
                return sites
    return sites


def has_rg() -> bool:
    return shutil.which("rg") is not None


def rg_hint(root: Path) -> str:
    if not has_rg():
        return "ripgrep (rg) was not found; Python filesystem scanning was used."
    try:
        result = subprocess.run(
            ["rg", "--version"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "ripgrep (rg) is installed but unavailable; Python filesystem scanning was used."
    if result.returncode in (0, 1):
        return "ripgrep (rg) is available for follow-up focused searches."
    return "ripgrep (rg) returned a non-zero status during availability check."


def relative_match(match: Match, root: Path) -> str:
    try:
        path = match.path.relative_to(root).as_posix()
    except ValueError:
        path = match.path.as_posix()
    return f"{path}:{match.line_no}"


def render_report(
    root: Path,
    sources: list[SourceFile],
    definitions: list[tuple[SourceFile, list[int]]],
    usages: list[Match],
    methods: list[MethodEvidence],
    max_usages: int,
) -> str:
    room_related_paths = {source.path for source in sources if source.is_room_related}
    room_currency_usages = [
        usage
        for usage in usages
        if CURRENCY_RE.search(usage.text)
        and (
            ROOM_RE.search(usage.path.as_posix())
            or usage.path in room_related_paths
        )
    ]

    lines: list[str] = []
    lines.append("# Room currency audit")
    lines.append("")
    lines.append(f"- Root: `{root}`")
    lines.append(f"- Source files scanned: {len(sources)}")
    lines.append(f"- {rg_hint(root)}")
    lines.append("")

    lines.append("## Definitions")
    if not definitions:
        lines.append("")
        lines.append("No room/basic-room related `currency` field or schema definitions were found.")
    else:
        lines.append("")
        lines.append("| File/class | Lines | Contract type | Evidence |")
        lines.append("| --- | ---: | --- | --- |")
        for source, line_numbers in definitions:
            evidence = "<br>".join(
                f"`{line_no}: {source.lines[line_no - 1].strip()}`" for line_no in line_numbers[:3]
            )
            if len(line_numbers) > 3:
                evidence += f"<br>... {len(line_numbers) - 3} more"
            line_list = ", ".join(str(line_no) for line_no in line_numbers)
            lines.append(
                f"| `{source.rel_path}`<br>`{source.display_name}` | {line_list} | "
                f"{contract_type(source)} | {evidence} |"
            )

    lines.append("")
    lines.append("## Usages and pass-through evidence")
    if not room_currency_usages:
        lines.append("")
        lines.append("No room/basic-room related `currency` usages were found.")
    else:
        lines.append("")
        lines.append("| Location | Usage type | Evidence |")
        lines.append("| --- | --- | --- |")
        for usage in room_currency_usages[:max_usages]:
            lines.append(
                f"| `{relative_match(usage, root)}` | {classify_usage(usage.text)} | "
                f"`{usage.text}` |"
            )
        if len(room_currency_usages) > max_usages:
            lines.append("")
            lines.append(f"_Output truncated: {len(room_currency_usages) - max_usages} more usage lines omitted._")

    lines.append("")
    lines.append("## Related methods and direct calls")
    if not methods:
        lines.append("")
        lines.append("No method bodies containing room/basic-room `currency` logic were detected.")
    else:
        lines.append("")
        lines.append("| Method | Currency lines | Direct-call status | Sample call sites |")
        lines.append("| --- | ---: | --- | --- |")
        for method in methods:
            status = "directly called" if method.direct_call_sites else "not directly called"
            samples = "<br>".join(
                f"`{relative_match(site, root)} {site.text}`" for site in method.direct_call_sites[:5]
            )
            if not samples:
                samples = "No direct production call site found by static name search; check framework/serialization usage."
            lines.append(
                f"| `{method.owner.display_name}.{method.name}(...)`<br>`{method.owner.rel_path}:{method.start_line}` | "
                f"{', '.join(str(line_no) for line_no in method.currency_lines)} | "
                f"{status} | {samples} |"
            )

    lines.append("")
    lines.append("## Recommended next steps")
    lines.append("")
    lines.append("1. Manually inspect every definition classified as DB/entity, RPC/remote DTO, Redis/cache, or QMQ/message before editing.")
    lines.append("2. Remove only confirmed pass-through assignments first, such as `target.setCurrency(source.getCurrency())`.")
    lines.append("3. Keep persisted/external schema fields until a schema/cache/message migration plan is confirmed.")
    lines.append("4. For methods reported as not directly called, still check annotations, mapper XML, reflection, serialization, scheduled jobs, and message listeners.")
    lines.append("5. Run focused compile/tests for edited converters, mappers, serializers, and message producers/consumers.")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit room/basic-room currency definitions and usages.")
    parser.add_argument("root", nargs="?", default=".", help="Repository root to scan.")
    parser.add_argument("--output", "-o", help="Write markdown report to this path.")
    parser.add_argument("--include-tests", action="store_true", help="Include test source paths in the scan.")
    parser.add_argument("--max-usages", type=int, default=200, help="Maximum usage rows to render.")
    parser.add_argument("--max-call-sites", type=int, default=20, help="Maximum direct call sites to keep per method.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"Root does not exist: {root}", file=sys.stderr)
        return 2

    sources = [
        source
        for path in iter_source_paths(root, args.include_tests)
        if (source := read_source(path, root)) is not None
    ]
    definitions = [
        (source, definition_lines)
        for source in sources
        if source.is_room_related and (definition_lines := find_definition_lines(source))
    ]
    usages = find_usage_matches(sources)

    room_paths = {source.path for source, _ in definitions}
    methods: list[MethodEvidence] = []
    for source in sources:
        if source.path not in room_paths and not source.is_room_related:
            continue
        methods.extend(find_methods_with_currency(source))
    for method in methods:
        method.direct_call_sites = direct_call_sites(
            method.name,
            sources,
            method.owner,
            args.max_call_sites,
        )

    report = render_report(root, sources, definitions, usages, methods, args.max_usages)
    if args.output:
        output = Path(args.output)
        output.write_text(report, encoding="utf-8")
        print(f"Wrote audit report to {output}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
