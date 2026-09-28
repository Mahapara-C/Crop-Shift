"""
Unit tests for src/compute/reference.py
Run from the repo root with: python -m pytest src -q
"""

import pytest
from reference import load_file, load_reference, parse_value, ReferenceData

HEADER = "item,value,unit,source_title,source_url,page,year,notes\n"
GOOD = "https://example.org/paper.pdf"

SYNTHETIC = (
    HEADER
    + f"wheat.heat.anthesis_tmax,31,degC,Good paper,{GOOD},4,2021,ok\n"
    + f"wheat.sow.window_start,1115,MMDD,Good paper,{GOOD},4,2021,ok\n"
    + f"boro_rice.sow.window_end,0130,MMDD,Good paper,{GOOD},5,2021,leading zero kept\n"
    + f"potato.stage.days_to_tuber_initiation,35-55,days,Good paper,{GOOD},6,2021,range\n"
    + f"potato.cold.frost_tmin,-3.0,degC,Good paper,{GOOD},7,2021,negative number\n"
    + f"lentil.stage.days_to_flowering,72,days,Variety A trial,{GOOD},1,2020,variety A\n"
    + f"lentil.stage.days_to_flowering,80,days,Variety B trial,{GOOD},2,2020,variety B\n"
    + f"potato.varieties.list,\"BARI Alu-7, BARI Alu-13\",text,Good paper,{GOOD},1,2024,text\n"
    + "mustard.sow.optimum,1025,MMDD,PLACEHOLDER - NOT A REAL SOURCE,n/a,n/a,n/a,fake\n"
    + "boro_rice.stage.days_to_maturity,140,days,BRRI fact sheet,brridhan28.pdf,2,2025,no url\n"
    + "mustard.stage.days_to_flowering_low,37,days,ANNUAL RESEARCH REPORT\n"
    + f"2024-2025,{GOOD},156,2025,broken row continued\n"
    + f"wheat.heat.grainfill_tmax,hot,degC,Good paper,{GOOD},4,2021,unparseable\n"
    + f"aman_rice.sow.optimum,0700,MMDD,Good paper,{GOOD},4,2021,day 00 is not a date\n"
)


@pytest.fixture
def ref_file(tmp_path):
    path = tmp_path / "synthetic.csv"
    path.write_text(SYNTHETIC, encoding="utf-8")
    return path


def test_parse_value_kinds():
    assert parse_value("35.4", "degC")["value"] == 35.4
    assert parse_value("-3.0", "degC")["value"] == -3.0
    r = parse_value("35-55", "days")
    assert (r["kind"], r["low"], r["high"], r["value"]) == ("range", 35.0, 55.0, 45.0)
    d = parse_value("0130", "MMDD")
    assert (d["month"], d["day"]) == (1, 30)
    d = parse_value("130", "MMDD")   # a spreadsheet may drop the leading zero
    assert (d["month"], d["day"]) == (1, 30)
    assert parse_value("1015", "MMDD")["month"] == 10
    assert parse_value("Suitable", "class")["text"] == "Suitable"


@pytest.mark.parametrize("value,unit", [("hot", "degC"), ("0700", "MMDD"), ("1332", "MMDD"),
                                        ("55-35", "days"), ("", "days"), ("10-16 (a) or 10-14", "days")])
def test_parse_value_rejects(value, unit):
    with pytest.raises(ValueError):
        parse_value(value, unit)


def test_placeholder_and_broken_rows_are_skipped_with_reasons(ref_file):
    kept, skipped = load_file(ref_file)
    reasons = dict(zip(skipped["item"], skipped["reason"]))
    assert reasons["mustard.sow.optimum"] == "placeholder"
    assert reasons["boro_rice.stage.days_to_maturity"] == "source_url"
    # the line-broken row: first half has no url, second half has no valid item
    assert reasons["mustard.stage.days_to_flowering_low"] == "source_url"
    assert reasons["2024-2025"] == "item"
    assert reasons["wheat.heat.grainfill_tmax"] == "value"
    assert reasons["aman_rice.sow.optimum"] == "value"
    assert len(skipped) == 6
    assert len(kept) == 8
    assert not kept["source_title"].str.startswith("PLACEHOLDER").any()
    assert kept["source_url"].str.startswith("http").all()


def test_kept_rows_keep_provenance_and_parsed_values(ref_file):
    kept, _ = load_file(ref_file)
    row = kept[kept["item"] == "wheat.heat.anthesis_tmax"].iloc[0]
    assert row["value"] == 31.0
    assert (row["source_title"], row["source_url"], row["page"]) == ("Good paper", GOOD, "4")
    end = kept[kept["item"] == "boro_rice.sow.window_end"].iloc[0]
    assert (end["month"], end["day"]) == (1, 30)
    tuber = kept[kept["item"] == "potato.stage.days_to_tuber_initiation"].iloc[0]
    assert (tuber["low"], tuber["high"]) == (35.0, 55.0)


def test_repeated_items_are_all_kept(ref_file):
    kept, skipped = load_file(ref_file)
    data = ReferenceData(kept, skipped)
    rows = data.rows("lentil.stage.days_to_flowering")
    assert sorted(rows["value"]) == [72.0, 80.0]
    assert set(rows["source_title"]) == {"Variety A trial", "Variety B trial"}
    assert data.skipped_counts() == {"source_url": 2, "value": 2, "placeholder": 1, "item": 1}


def test_non_item_value_file_is_reported_not_parsed(tmp_path):
    (tmp_path / "oni.csv").write_text("season,year,total,anom\nDJF,1950,25.0,-1.3\n", encoding="utf-8")
    (tmp_path / "good.csv").write_text(HEADER + f"a.b,1,m,T,{GOOD},1,2020,\n", encoding="utf-8")
    data = load_reference(reference_dir=str(tmp_path))
    assert list(data.kept["item"]) == ["a.b"]
    assert list(data.skipped["reason"]) == ["header"]


def test_blank_leading_line_is_ignored(tmp_path):
    (tmp_path / "yields.csv").write_text("\n" + HEADER + f"a.b,2,m,T,{GOOD},1,2020,\n",
                                         encoding="utf-8")
    kept, skipped = load_file(tmp_path / "yields.csv")
    assert list(kept["value"]) == [2.0] and skipped.empty
