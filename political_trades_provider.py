"""Provider seam for normalized congressional transaction rows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Iterable


@dataclass(frozen=True)
class PoliticalTrade:
    politician_bioguide: str | None
    politician_name: str
    ticker: str
    asset_name: str
    tx_type: str
    amount_low: int | None
    amount_high: int | None
    tx_date: str
    disclosure_date: str
    source_url: str

    def as_store_row(self) -> dict:
        row = asdict(self)
        return {
            **row,
            "politician_id": f"POL_{self.politician_bioguide}" if self.politician_bioguide else None,
            "filer_name": self.politician_name,
            "filing_type": "TRANSACTION",
            "doc_id": None,
            "amount_range": None,
        }


class PoliticalTradesProvider:
    provider_id = "abstract"
    reason = ""

    def fetch_transactions(self, start_date: date, end_date: date) -> Iterable[PoliticalTrade]:
        raise NotImplementedError


class NullPoliticalTradesProvider(PoliticalTradesProvider):
    """Launch placeholder while paid QuiverQuant access is deferred."""

    provider_id = "null"
    reason = "QuiverQuant paid access deferred until launch"

    def fetch_transactions(self, start_date: date, end_date: date) -> Iterable[PoliticalTrade]:
        return ()

