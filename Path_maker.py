from dbfread import DBF
import csv
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

# -----------------------------
# Config
# -----------------------------
DBF_PATH = "shape-files/Alameda_Sections/ALAMEDAS.DBF"
CSV_OUT = "overpass_street_ranges.csv"

# -----------------------------
# Direction + suffix normalization
# -----------------------------

# Expand leading direction tokens commonly found in names
# e.g., "W. Tower" -> "West Tower", "N Midway" -> "North Midway"
DIR_WORDS = {
    "N": "North",
    "S": "South",
    "E": "East",
    "W": "West",
    "NE": "Northeast",
    "NW": "Northwest",
    "SE": "Southeast",
    "SW": "Southwest",
}

# Common suffix expansions (end-of-name only)
# You can add more here as you encounter them.
SUFFIX_MAP = {
    "ST": "Street",
    "STR": "Street",
    "AVE": "Avenue",
    "AV": "Avenue",
    "BLVD": "Boulevard",
    "DR": "Drive",
    "RD": "Road",
    "LN": "Lane",
    "CT": "Court",
    "PL": "Place",
    "PKWY": "Parkway",
    "HWY": "Highway",
    "TER": "Terrace",
    "CIR": "Circle",
    "WAY": "Way",
    "TRL": "Trail",
}

# For skipping entire records
RE_SLAB = re.compile(r"\bslab(s)?\b", re.IGNORECASE)

# Recognize "Street Name" or "Street Name (comment)"
RE_STREET_WITH_OPTIONAL_COMMENT = re.compile(
    r"^\s*(?P<street>[^()]+?)\s*(?:\((?P<comment>.+?)\))?\s*$",
    re.IGNORECASE,
)

# Allow punctuation like "E." "S." in offset text
DIR_RE = r"(N\.?|S\.?|E\.?|W\.?|NE\.?|NW\.?|SE\.?|SW\.?|NB\.?|SB\.?|EB\.?|WB\.?|NORTH|SOUTH|EAST|WEST)"
UNIT_RE = r"(?:FT|FEET|['\"]+)"
REL_TOKEN = r"(?:OF\.?|OR\.?|FROM\.?)"

# Parentheses-only: "(DIR NearbyStreet)"
RE_PAREN_DIR_NEARBY = re.compile(
    rf"^\s*\(\s*(?P<dir>{DIR_RE})\s+(?P<nearby>.+?)\s*\)\s*$",
    re.IGNORECASE,
)

# Unit-less: "422 E. of Hancock St"
RE_OFFSET_SIMPLE_OF = re.compile(
    rf"^\s*(?P<dist>\d+(?:\.\d+)?)\s+(?P<dir>{DIR_RE})\s+OF\.?\s+(?P<nearby>.+?)\s*$",
    re.IGNORECASE,
)

# "{DIST}{UNIT} {DIR} of/from {Nearby}"
RE_OFFSET_DIST_DIR_REL = re.compile(
    rf"^\s*(?P<dist>\d+(?:\.\d+)?)\s*{UNIT_RE}\s+(?P<dir>{DIR_RE})\s+{REL_TOKEN}\s+(?P<nearby>.+?)\s*$",
    re.IGNORECASE,
)

# "{DIR} {DIST}{UNIT} of/from {Nearby}"
RE_OFFSET_DIR_DIST_REL = re.compile(
    rf"^\s*(?P<dir>{DIR_RE})\s+(?P<dist>\d+(?:\.\d+)?)\s*{UNIT_RE}\s+{REL_TOKEN}\s+(?P<nearby>.+?)\s*$",
    re.IGNORECASE,
)

# TWO-DIR: "N 250' W of Lexington"
RE_OFFSET_DIRA_DIST_DIRB_REL = re.compile(
    rf"^\s*(?P<dir_a>{DIR_RE})\s+(?P<dist>\d+(?:\.\d+)?)\s*{UNIT_RE}\s+(?P<dir_b>{DIR_RE})\s+{REL_TOKEN}\s+(?P<nearby>.+?)\s*$",
    re.IGNORECASE,
)


def _clean(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if s else None


def _norm_offset_dir(d: Optional[str]) -> Optional[str]:
    if not d:
        return None
    # For offset columns, we keep N/E/S/W style (like you already output)
    key = d.strip().upper().replace(".", "")
    # Collapse words to letters if they appear
    if key in ("NORTH",):
        return "N"
    if key in ("SOUTH",):
        return "S"
    if key in ("EAST",):
        return "E"
    if key in ("WEST",):
        return "W"
    return key


def _combine_dirs(a: Optional[str], b: Optional[str]) -> Optional[str]:
    a = _norm_offset_dir(a)
    b = _norm_offset_dir(b)
    if not a:
        return b
    if not b:
        return a
    combos = {
        ("N", "E"): "NE", ("E", "N"): "NE",
        ("N", "W"): "NW", ("W", "N"): "NW",
        ("S", "E"): "SE", ("E", "S"): "SE",
        ("S", "W"): "SW", ("W", "S"): "SW",
    }
    return combos.get((a, b), b)


def _expand_leading_direction_words(name: str) -> str:
    """
    Expand a leading direction token in street names:
      "W. Tower" -> "West Tower"
      "NE 1st" -> "Northeast 1st"
    Only affects the leading token.
    """
    parts = name.split(" ", 1)
    if not parts:
        return name
    first = parts[0].strip().upper().replace(".", "")
    rest = parts[1] if len(parts) > 1 else ""
    if first in DIR_WORDS:
        expanded = DIR_WORDS[first]
        return (expanded + (" " + rest if rest else "")).strip()
    return name


def _expand_suffix(name: str) -> str:
    """
    Expand a trailing suffix token:
      "Hancock St." -> "Hancock Street"
      "Red Jacket Ave" -> "Red Jacket Avenue"
    Only affects the final token.
    """
    tokens = name.split()
    if not tokens:
        return name

    last = tokens[-1].strip().upper().replace(".", "")
    if last in SUFFIX_MAP:
        tokens[-1] = SUFFIX_MAP[last]
        return " ".join(tokens)
    return name


def normalize_street_name(name: Optional[str]) -> Optional[str]:
    """
    Normalize street names for Overpass:
      - Expand leading direction abbreviations: W. -> West, etc.
      - Expand trailing suffix abbreviations: St./Str. -> Street, Ave. -> Avenue, etc.
    """
    s = _clean(name)
    if not s:
        return None
    s = _expand_leading_direction_words(s)
    s = _expand_suffix(s)
    return s


@dataclass
class LocParse:
    raw: str
    base_street: Optional[str] = None
    direction: Optional[str] = None
    feet: Optional[float] = None
    comment_street: Optional[str] = None
    has_comment: bool = False
    kind: Optional[str] = None  # street, street+comment, paren_dir_nearby, offset_only, unknown


def parse_offset_text(text: str) -> Dict[str, Any]:
    """
    Parse offset-like text that may appear inside parentheses OR standalone:
      - "100' S. of Pearl Harbor"
      - "422 E. of Hancock St"
      - "N 250' W of Lexington"
    """
    t = _clean(text) or ""
    if not t:
        return {"direction": None, "feet": None, "comment_street": None}

    m = RE_OFFSET_SIMPLE_OF.match(t)
    if m:
        return {
            "direction": _norm_offset_dir(m.group("dir")),
            "feet": float(m.group("dist")),
            "comment_street": normalize_street_name(m.group("nearby")),
        }

    m = RE_OFFSET_DIRA_DIST_DIRB_REL.match(t)
    if m:
        return {
            "direction": _combine_dirs(m.group("dir_a"), m.group("dir_b")),
            "feet": float(m.group("dist")),
            "comment_street": normalize_street_name(m.group("nearby")),
        }

    m = RE_OFFSET_DIST_DIR_REL.match(t)
    if m:
        return {
            "direction": _norm_offset_dir(m.group("dir")),
            "feet": float(m.group("dist")),
            "comment_street": normalize_street_name(m.group("nearby")),
        }

    m = RE_OFFSET_DIR_DIST_REL.match(t)
    if m:
        return {
            "direction": _norm_offset_dir(m.group("dir")),
            "feet": float(m.group("dist")),
            "comment_street": normalize_street_name(m.group("nearby")),
        }

    return {"direction": None, "feet": None, "comment_street": None}


def parse_loc(loc_text: Optional[str]) -> Dict[str, Any]:
    """
    Handles:
      - "Street"
      - "Street (offset/comment)"
      - "(DIR NearbyStreet)"
      - Standalone offset: "100' S. of Pearl Harbor"
      - Unit-less offset: "422 E. of Hancock St"
    """
    raw = _clean(loc_text) or ""
    out = LocParse(raw=raw)

    if not raw:
        out.kind = "unknown"
        return asdict(out)

    # "(DIR NearbyStreet)"
    m = RE_PAREN_DIR_NEARBY.match(raw)
    if m:
        out.kind = "paren_dir_nearby"
        out.has_comment = True
        out.direction = _norm_offset_dir(m.group("dir"))
        out.comment_street = normalize_street_name(m.group("nearby"))
        return asdict(out)

    # Standalone offset (no parentheses)
    off = parse_offset_text(raw)
    if off.get("comment_street"):
        out.kind = "offset_only"
        out.has_comment = True
        out.direction = off.get("direction")
        out.feet = off.get("feet")
        out.comment_street = off.get("comment_street")
        return asdict(out)

    # "Street" or "Street (comment)"
    m = RE_STREET_WITH_OPTIONAL_COMMENT.match(raw)
    if m:
        out.base_street = normalize_street_name(m.group("street"))
        comment = _clean(m.group("comment"))

        if comment:
            out.kind = "street+comment"
            out.has_comment = True
            off2 = parse_offset_text(comment)
            out.direction = off2.get("direction")
            out.feet = off2.get("feet")
            out.comment_street = off2.get("comment_street")
        else:
            out.kind = "street"
        return asdict(out)

    out.kind = "unknown"
    return asdict(out)


# -----------------------------
# Output columns (your schema)
# -----------------------------
OUT_FIELDS = [
    "surveyed_street",
    "beginning_street",
    "end_street",
    "start_direction",
    "start_feet",
    "start_comment_street",
    "end_direction",
    "end_feet",
    "end_comment_street",
]


def main() -> None:
    dbf_file = Path(DBF_PATH)
    if not dbf_file.exists():
        raise FileNotFoundError(f"DBF file not found: {dbf_file.resolve()}")

    table = DBF(str(dbf_file), load=True, char_decode_errors="ignore")

    with open(CSV_OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        writer.writeheader()

        written = 0
        skipped_slab = 0

        for record in table:
            beg_loc = record.get("BEG_LOC", "")
            end_loc = record.get("END_LOC", "")

            # Skip slab rows completely
            if RE_SLAB.search(str(beg_loc)) or RE_SLAB.search(str(end_loc)):
                skipped_slab += 1
                continue

            surveyed = normalize_street_name(record.get("ST_NAME", "")) or ""

            beg = parse_loc(beg_loc)
            end = parse_loc(end_loc)

            beginning_street = beg.get("base_street") or beg.get("comment_street") or ""
            end_street = end.get("base_street") or end.get("comment_street") or ""

            # Normalize again (safe) in case the fallback chosen was comment_street
            beginning_street = normalize_street_name(beginning_street) or beginning_street
            end_street = normalize_street_name(end_street) or end_street

            writer.writerow({
                "surveyed_street": surveyed,
                "beginning_street": beginning_street,
                "end_street": end_street,

                "start_direction": beg.get("direction") or "",
                "start_feet": beg.get("feet") if beg.get("feet") is not None else "",
                "start_comment_street": beg.get("comment_street") or "",

                "end_direction": end.get("direction") or "",
                "end_feet": end.get("feet") if end.get("feet") is not None else "",
                "end_comment_street": end.get("comment_street") or "",
            })
            written += 1

    print(f"Input DBF: {dbf_file.resolve()}")
    print(f"Output CSV: {Path(CSV_OUT).resolve()}")
    print(f"Rows written: {written}")
    print(f"Rows skipped (slabs): {skipped_slab}")


if __name__ == "__main__":
    main()
