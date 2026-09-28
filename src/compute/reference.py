"""
src/compute/reference.py

Strict loader for the researched values in data/reference/*.csv
(columns: item,value,unit,source_title,source_url,page,year,notes).

A row is KEPT only if all of these hold, checked in this order; otherwise it
is SKIPPED and reported with the first reason that failed:
  1. "placeholder"   source_title does not start with "PLACEHOLDER"
  2. "item"          item is a lower-case dotted name, e.g. wheat.heat.anthesis_tmax
  3. "source_url"    source_url starts with http:// or https://
  4. "value"         value parses for its unit:
                       unit MMDD         -> month/day ("1015", "0130", "130" -> 01-30)
                       unit text / class -> kept as text
                       any other unit    -> a number ("35.4", "-3.0") or a range
                                            "A-B" ("35-55" -> low 35, high 55)
The files in data/reference/ belong to teammates and are never edited here:
bad rows are handled in code and listed, so they can be fixed at the source.

Every kept row keeps its source_title, source_url and page for provenance.
An item may appear several times (different varieties, regions or sources);
all rows are kept and ReferenceData.rows(item) returns every one of them.
"""

import csv
import datetime
import glob
import os
import re

import pandas as pd

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REFERENCE_DIR = os.path.join(REPO_ROOT, "data", "reference")

COLUMNS = ["item", "value", "unit", "source_title", "source_url", "page", "year", "notes"]
ITEM_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")
RANGE_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)$")
MMDD_RE = re.compile(r"^\d{3,4}$")
TEXT_UNITS = {"text", "class"}
DATE_UNITS = {"mmdd"}

KEPT_COLUMNS = ["file", "line", "item", "kind", "value", "low", "high", "month", "day",
                "text", "unit", "source_title", "source_url", "page", "year", "notes"]
SKIPPED_COLUMNS = ["file", "line", "item", "value", "reason", "detail"]


def parse_value(value, unit):
    """Parses one value for its unit. Returns a dict with kind ("number",
    "range", "mmdd" or "text") and value/low/high/month/day/text (None when
    not used; a range's value is its midpoint). Raises ValueError if the
    value does not parse."""
    raw = (value or "").strip()
    unit_key = (unit or "").strip().lower()
    out = {"kind": None, "value": None, "low": None, "high": None,
           "month": None, "day": None, "text": None}
    if unit_key in TEXT_UNITS:
        if not raw:
            raise ValueError("empty text value")
        return {**out, "kind": "text", "text": raw}
    if unit_key in DATE_UNITS:
        if not MMDD_RE.match(raw):
            raise ValueError(f"MMDD value {raw!r} is not 3-4 digits")
        padded = raw.zfill(4)
        month, day = int(padded[:2]), int(padded[2:])
        datetime.date(2000, month, day)  # leap year, so 0229 is valid; raises if not a date
        return {**out, "kind": "mmdd", "month": month, "day": day}
    if NUMBER_RE.match(raw):
        number = float(raw)
        return {**out, "kind": "number", "value": number, "low": number, "high": number}
    match = RANGE_RE.match(raw)
    if match:
        low, high = float(match.group(1)), float(match.group(2))
        if low > high:
            raise ValueError(f"range {raw!r} has low > high")
        return {**out, "kind": "range", "value": (low + high) / 2, "low": low, "high": high}
    raise ValueError(f"{raw!r} is not a number or an A-B range")


def check_row(row):
    """Returns (reason, detail) for the first rule a row breaks, or None if
    the row is kept. row: dict with the COLUMNS keys."""
    if row["source_title"].strip().upper().startswith("PLACEHOLDER"):
        return "placeholder", "source_title starts with PLACEHOLDER"
    if not ITEM_RE.match(row["item"].strip()):
        return "item", f"item name is malformed: {row['item'][:60]!r}"
    if not re.match(r"^https?://", row["source_url"].strip(), re.IGNORECASE):
        return "source_url", f"source_url is not http(s): {row['source_url'][:60]!r}"
    try:
        parse_value(row["value"], row["unit"])
    except ValueError as err:
        return "value", f"value does not parse ({err})"
    return None


def load_file(path):
    """Loads one reference CSV. Returns (kept, skipped) DataFrames.

    A file whose header is not the standard COLUMNS (e.g. oni.csv, a plain
    data table) is not an item/value file: nothing is kept and one skipped
    entry with reason "header" is returned. Blank lines are ignored. A
    physical line break inside an unquoted field splits a row in two; both
    halves then fail the rules above and are reported."""
    name = os.path.basename(path)
    kept, skipped = [], []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = None
        for fields in reader:
            if not any(f.strip() for f in fields):
                continue
            if header is None:
                header = [f.strip() for f in fields]
                if header[:len(COLUMNS)] != COLUMNS:
                    skipped.append({"file": name, "line": reader.line_num, "item": "",
                                    "value": "", "reason": "header",
                                    "detail": f"not an item/value file (header {header[:4]})"})
                    break
                continue
            fields = (fields + [""] * len(COLUMNS))[:len(COLUMNS)]
            row = dict(zip(COLUMNS, fields))
            problem = check_row(row)
            if problem:
                skipped.append({"file": name, "line": reader.line_num,
                                "item": row["item"].strip(), "value": row["value"].strip(),
                                "reason": problem[0], "detail": problem[1]})
                continue
            parsed = parse_value(row["value"], row["unit"])
            kept.append({"file": name, "line": reader.line_num, "item": row["item"].strip(),
                         **parsed, "unit": row["unit"].strip(),
                         "source_title": row["source_title"].strip(),
                         "source_url": row["source_url"].strip(),
                         "page": row["page"].strip(), "year": row["year"].strip(),
                         "notes": row["notes"].strip()})
    return (pd.DataFrame(kept, columns=KEPT_COLUMNS),
            pd.DataFrame(skipped, columns=SKIPPED_COLUMNS))


class ReferenceData:
    """Kept and skipped rows of one or more reference files."""

    def __init__(self, kept, skipped):
        self.kept = kept.reset_index(drop=True)
        self.skipped = skipped.reset_index(drop=True)

    def rows(self, item):
        """Every kept row for this exact item (possibly several)."""
        return self.kept[self.kept["item"] == item]

    def has(self, item):
        return not self.rows(item).empty

    def with_prefix(self, prefix):
        """Kept rows whose item starts with prefix (e.g. "area.feni.")."""
        return self.kept[self.kept["item"].str.startswith(prefix)]

    def skipped_counts(self):
        """{reason: number of skipped rows}."""
        return self.skipped["reason"].value_counts().to_dict()


def citation(row):
    """Provenance of one kept row as a plain dict."""
    return {"source_title": row["source_title"], "source_url": row["source_url"],
            "page": row["page"]}


def load_reference(files=None, reference_dir=REFERENCE_DIR):
    """Loads reference files into one ReferenceData. files: file names
    inside reference_dir (default: every *.csv except _TEMPLATE.csv)."""
    if files is None:
        files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(reference_dir, "*.csv"))
                       if not os.path.basename(p).startswith("_"))
    kept, skipped = [], []
    for name in files:
        k, s = load_file(os.path.join(reference_dir, name))
        kept.append(k)
        skipped.append(s)
    return ReferenceData(pd.concat(kept, ignore_index=True) if kept else pd.DataFrame(columns=KEPT_COLUMNS),
                         pd.concat(skipped, ignore_index=True) if skipped else pd.DataFrame(columns=SKIPPED_COLUMNS))
