from dedupe_report import normalize_name


def main() -> None:
    assert normalize_name("Apple Inc.") == normalize_name("APPLE INC")
    assert normalize_name("Apple Inc.") != normalize_name("Applied Materials")


if __name__ == "__main__":
    main()
