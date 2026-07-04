from pathlib import Path

from openpyxl import load_workbook

from dcf_export import build_dcf_workbook


def check_workbook(path: Path, model_sheet: str) -> None:
    assert path.exists() and path.stat().st_size > 10_000
    wb = load_workbook(path, data_only=False)
    for sheet in ["Assumptions", "Historical SEC Data", model_sheet, "Sources", "Checks"]:
        assert sheet in wb.sheetnames
    assumptions = wb["Assumptions"]
    assert assumptions["A6"].value == "Revenue growth"
    assert assumptions["A12"].value == "WACC / discount rate"
    assert assumptions["A13"].value == "Terminal growth"
    formulas = "\n".join(
        str(cell.value)
        for ws in wb.worksheets
        for row in ws.iter_rows()
        for cell in row
        if isinstance(cell.value, str) and cell.value.startswith("=")
    )
    assert "#REF!" not in formulas
    assert "'Assumptions'!$B$6" in formulas or model_sheet == "Dividend DCF"


def main() -> None:
    check_workbook(build_dcf_workbook("BLK", "cash_flow"), "Cash Flow DCF")
    check_workbook(build_dcf_workbook("BLK", "dividend"), "Dividend DCF")
    check_workbook(build_dcf_workbook("PFE", "cash_flow"), "Cash Flow DCF")
    check_workbook(build_dcf_workbook("PFE", "dividend"), "Dividend DCF")
    print("dcf export ok")


if __name__ == "__main__":
    main()
