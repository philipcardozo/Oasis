from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import redirect_stdout
import io

from expand_us import load_source_nodes, merge_source_nodes


def main() -> None:
    with TemporaryDirectory() as d:
        p = Path(d) / "test_intl.jsonl"
        p.write_text(
            '{"canonical_id":"XETR:NVD","name":"NVIDIA Frankfurt","country":"DE","exchange":"XETR","sector_or_sic":"Information Technology"}\n'
            '{"canonical_id":"XLON:ZZZ","name":"Zulu PLC","country":"GB","exchange":"XLON","sector_or_sic":"Industrials","website":"https://example.com","quote_symbol":"ZZZ.L","price":{"as_of":"2026-06-30","price":12.34},"research":{"profile":"https://example.com/profile"}}\n'
            '{"canonical_id":"BROKEN","name":"Broken"}\n'
        )
        with redirect_stdout(io.StringIO()):
            loaded = load_source_nodes(Path(d))
        assert [n["canonical_id"] for n in loaded] == ["NVDA", "XLON:ZZZ"]
        assert loaded[1]["research"]["website"] == "https://example.com"
        assert loaded[1]["research"]["profile"] == "https://example.com/profile"
        assert loaded[1]["quote_symbol"] == "ZZZ.L"
        assert loaded[1]["price"]["price"] == 12.34

        base = [{"id": "NVDA", "canonical_id": "NVDA", "n": "NVIDIA CORP", "t": "NVDA"}]
        with redirect_stdout(io.StringIO()):
            merged = merge_source_nodes(base, Path(d))
        assert len([n for n in merged if n["canonical_id"] == "NVDA"]) == 1
        assert any(n["canonical_id"] == "XLON:ZZZ" for n in merged)


if __name__ == "__main__":
    main()
