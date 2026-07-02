from expand_us import company_group, group_key


def main() -> None:
    assert company_group({"sector": "Information Technology", "sub": "Semiconductors", "n": "NVIDIA CORP", "t": "NVDA"}) == "AI & semiconductors"
    assert company_group({"sector": "Information Technology", "sub": "Services-Prepackaged Software", "n": "Software Co", "t": "SOFT"}) == "Cloud & software"
    assert company_group({"sector": "Financials", "sub": "Asset Management & Custody Banks", "n": "BlackRock", "t": "BLK"}) == "Asset management & advisory"
    assert company_group({"sector": "Other", "sub": "Services-Management Consulting Services", "n": "Consulting Co", "t": "CONS"}) == "Consulting & professional services"
    assert group_key("AI & semiconductors") == "ai_semiconductors"


if __name__ == "__main__":
    main()
