from expand_us import normalize_link, resolve_id


def test_main() -> None:
    assert resolve_id("BRK.B") == "BRK-B"
    assert resolve_id("Twitter") == "LEGACY_TWTR"
    assert resolve_id("TikTok") == "PVT_BYTEDANCE"

    link = normalize_link({"from": "BRK.B", "to": "TikTok", "rel": "partners"})
    assert link["from"] == "BRK-B"
    assert link["to"] == "PVT_BYTEDANCE"


if __name__ == "__main__":
    test_main()
