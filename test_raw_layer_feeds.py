from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from map_api import raw_layer_features


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "usgs_3dep").mkdir()
        (root / "eia").mkdir()
        (root / "fbi_crime").mkdir()

        (root / "usgs_3dep" / "terrain.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [-120.5, 37.2]},
                            "properties": {"name": "USGS 3DEP terrain sample"},
                        }
                    ],
                }
            )
        )
        write_csv(
            root / "eia" / "power_plants.csv",
            [{"name": "EIA power plant sample", "latitude": 33.45, "longitude": -112.07}],
        )
        write_csv(
            root / "fbi_crime" / "crime.csv",
            [{"name": "FBI crime sample", "lat": 41.88, "lng": -87.63}],
        )

        features = raw_layer_features(root.as_posix())
        by_name = {f["properties"]["name"]: f for f in features}

        assert by_name["USGS 3DEP terrain sample"]["properties"]["layer_type"] == "relief-terrain"
        assert by_name["USGS 3DEP terrain sample"]["properties"]["source_layer"] == "relief_features"
        assert by_name["EIA power plant sample"]["properties"]["layer_type"] == "industrial-power-plants"
        assert by_name["EIA power plant sample"]["properties"]["source_layer"] == "industrial_assets"
        assert by_name["FBI crime sample"]["properties"]["layer_type"] == "relief-crime"
        assert by_name["FBI crime sample"]["properties"]["source_layer"] == "relief_features"

    print("raw layer feeds ok")


if __name__ == "__main__":
    test_main()
