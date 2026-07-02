from refresh_filings import filing_url, pick_filings


def main() -> None:
    recent = {
        "form": ["8-K", "10-Q", "10-K"],
        "accessionNumber": ["0001045810-26-000001", "0001045810-25-000099", "0001045810-25-000010"],
        "filingDate": ["2026-01-02", "2025-11-20", "2025-02-26"],
        "primaryDocument": ["nvda-20260102.htm", "nvda-20251026.htm", "nvda-20250126.htm"],
    }
    out = pick_filings(recent, "0001045810")
    assert [x["form"] for x in out] == ["8-K", "10-Q", "10-K"]
    assert out[0]["url"] == filing_url("0001045810", "0001045810-26-000001", "nvda-20260102.htm")


if __name__ == "__main__":
    main()
