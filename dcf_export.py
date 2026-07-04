from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from cache_companyfacts import cache_one, cik10

ROOT = Path(__file__).parent
DATA = ROOT / "graph" / "data"
FACTS = DATA / "companyfacts"
OUTPUTS = ROOT / "outputs" / "dcf"
UNIVERSE = DATA / "universe.json"

USD = '$#,##0;[Red]($#,##0);-'
USD_MM = '$#,##0.0;[Red]($#,##0.0);-'
PER_SHARE = '$0.00;[Red]($0.00);-'
PCT = '0.0%;[Red](0.0%);-'
NUM = '#,##0;[Red](#,##0);-'

BLUE = "0000FF"
GREEN = "008000"
DARK = "17324D"
LIGHT = "EAF2F8"
YELLOW = "FFF2CC"
OK = "E2F0D9"
BAD = "FCE4D6"


TAGS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "ebit": ["OperatingIncomeLoss"],
    "pretax": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "tax": ["IncomeTaxExpenseBenefit"],
    "da": ["DepreciationDepletionAndAmortization", "DepreciationDepletionAndAmortizationExpense", "DepreciationAndAmortization", "Depreciation"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "dividends": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends", "DividendsCommonStockCash"],
    "shares": ["WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic", "EntityCommonStockSharesOutstanding"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "debt": ["LongTermDebtCurrent", "LongTermDebtNoncurrent", "ShortTermBorrowings", "ShortTermDebt", "LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebtAndFinanceLeaseObligationsNoncurrent"],
}


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")[:48] or "dcf"


def load_node(entity_id: str) -> dict:
    nodes = json.load(UNIVERSE.open())["nodes"]
    aliases = {str(n.get("t", "")).upper(): n["id"] for n in nodes if n.get("t")}
    aliases.update({n["id"].upper(): n["id"] for n in nodes})
    resolved = aliases.get(entity_id.upper(), entity_id)
    by_id = {n["id"]: n for n in nodes}
    if resolved not in by_id:
        raise ValueError(f"unknown entity {entity_id}")
    node = by_id[resolved]
    if node.get("issuer_id") and node["issuer_id"] in by_id:
        return by_id[node["issuer_id"]]
    return node


def load_facts(node: dict) -> tuple[dict, Path]:
    cik = cik10(node.get("cik", ""))
    path = FACTS / f"CIK{cik}.json"
    if not path.exists():
        path = cache_one(cik)
    return json.load(path.open()), path


def annual_rows(facts: dict, tag: str, unit: str = "USD") -> list[dict]:
    rows = facts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get(unit, [])
    out = []
    for row in rows:
        if not isinstance(row.get("val"), (int, float)) or not row.get("fy"):
            continue
        annual = row.get("fp") == "FY" or row.get("form") == "10-K"
        if row.get("start") and row.get("end"):
            try:
                annual = annual or (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days >= 300
            except ValueError:
                pass
        if annual:
            out.append(row)
    return out


def pick_annual(facts: dict, names: list[str], unit: str = "USD") -> dict[int, tuple[float, str, str]]:
    picked: dict[int, tuple[float, str, str]] = {}
    for tag in names:
        for row in annual_rows(facts, tag, unit):
            fy = int(row["fy"])
            prev = picked.get(fy)
            if not prev or str(row.get("filed", "")) > prev[1]:
                picked[fy] = (float(row["val"]), str(row.get("filed", "")), tag)
    return picked


def latest_instant(facts: dict, names: list[str], unit: str = "USD") -> tuple[float, str, str] | None:
    candidates = []
    for tag in names:
        rows = facts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get(unit, [])
        for row in rows:
            if isinstance(row.get("val"), (int, float)) and row.get("end"):
                candidates.append((str(row.get("end")), float(row["val"]), tag))
    if not candidates:
        return None
    end, value, tag = sorted(candidates)[-1]
    return value, end, tag


def avg(values: list[float], fallback: float) -> float:
    vals = [v for v in values if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else fallback


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def cagr(first: float, last: float, periods: int, fallback: float) -> float:
    if first > 0 and last > 0 and periods > 0:
        return (last / first) ** (1 / periods) - 1
    return fallback


def history(facts: dict) -> tuple[list[int], dict[str, dict[int, tuple[float, str, str]]]]:
    series = {key: pick_annual(facts, tags, "shares" if key == "shares" else "USD") for key, tags in TAGS.items() if key not in {"cash", "debt"}}
    years = sorted(set().union(*(set(s) for s in series.values())))[-5:]
    return years, series


def safe_div(a: float | None, b: float | None, fallback: float = 0.0) -> float:
    return a / b if a is not None and b not in (None, 0) else fallback


def style_workbook(wb: Workbook) -> None:
    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = False
        ws.freeze_panes = "B6"
        for row in ws.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical="center")
        for col in range(1, ws.max_column + 1):
            letter = get_column_letter(col)
            if (ws.column_dimensions[letter].width or 0) < 14:
                ws.column_dimensions[letter].width = 14
        if (ws.column_dimensions["A"].width or 0) < 34:
            ws.column_dimensions["A"].width = 34


def title(ws, text: str, subtitle: str) -> None:
    ws["A1"] = text
    ws["A1"].font = Font(size=16, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor=DARK)
    ws["A2"] = subtitle
    ws["A2"].font = Font(italic=True, color="666666")


def section(ws, row: int, text: str, last_col: int) -> None:
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    c = ws.cell(row, 1, text)
    c.fill = PatternFill("solid", fgColor=DARK)
    c.font = Font(color="FFFFFF", bold=True)


def row_border(ws, row: int, first_col: int, last_col: int) -> None:
    side = Side(style="thin", color="808080")
    for col in range(first_col, last_col + 1):
        ws.cell(row, col).border = Border(top=side)


def add_sources(wb: Workbook, node: dict, facts_path: Path, method: str) -> None:
    ws = wb.create_sheet("Sources")
    title(ws, "Sources / Audit", f"{node.get('n')} | {method.replace('_', ' ').title()} DCF")
    rows = [
        ["Item", "Value", "Source", "Notes"],
        ["SEC companyfacts cache", str(facts_path), "https://www.sec.gov/search-filings/edgar-application-programming-interfaces", "Standardized XBRL companyfacts; backend fetch required because SEC data API does not support browser CORS."],
        ["SEC filings", node.get("research", {}).get("sec_filings", ""), "SEC EDGAR", "Primary filing source."],
        ["Market price", node.get("price", {}).get("price", ""), node.get("price", {}).get("source", ""), f"As of {node.get('price', {}).get('as_of', '')}."],
        ["Model date", date.today().isoformat(), "Generated by Oasis", "Workbook assumptions are editable blue cells."],
    ]
    for r, row in enumerate(rows, 4):
        for c, value in enumerate(row, 1):
            ws.cell(r, c, value)
    ws["A4"].fill = ws["B4"].fill = ws["C4"].fill = ws["D4"].fill = PatternFill("solid", fgColor=LIGHT)
    for cell in ws[4]:
        cell.font = Font(bold=True)
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 48
    ws.column_dimensions["C"].width = 62
    ws.column_dimensions["D"].width = 70
    for row in ws.iter_rows(min_row=5, max_col=4):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")


def write_assumptions(wb: Workbook, node: dict, facts: dict, years: list[int], series: dict, method: str) -> None:
    ws = wb.create_sheet("Assumptions")
    title(ws, "DCF Assumptions", f"{node.get('n')} ({node.get('t')})")
    revenue = [series["revenue"].get(y, (None, "", ""))[0] for y in years]
    ebit = [series["ebit"].get(y, (None, "", ""))[0] for y in years]
    tax = [abs(series["tax"].get(y, (None, "", ""))[0]) if series["tax"].get(y) else None for y in years]
    pretax = [series["pretax"].get(y, (None, "", ""))[0] for y in years]
    da = [series["da"].get(y, (None, "", ""))[0] for y in years]
    capex = [abs(series["capex"].get(y, (None, "", ""))[0]) if series["capex"].get(y) else None for y in years]
    dividends = [abs(series["dividends"].get(y, (None, "", ""))[0]) if series["dividends"].get(y) else None for y in years]
    first_rev = next((x for x in revenue if x and x > 0), None)
    last_rev = next((x for x in reversed(revenue) if x and x > 0), None)
    rev_growth = clamp(cagr(first_rev or 0, last_rev or 0, max(1, len([x for x in revenue if x]) - 1), 0.03), -0.05, 0.12)
    ebit_margin = clamp(avg([safe_div(e, r) for e, r in zip(ebit, revenue) if e and r], 0.15), -0.05, 0.45)
    tax_rate = clamp(avg([safe_div(t, p) for t, p in zip(tax, pretax) if t is not None and p and p > 0], 0.21), 0.05, 0.35)
    da_pct = clamp(avg([safe_div(d, r) for d, r in zip(da, revenue) if d and r], 0.03), 0.0, 0.15)
    capex_pct = clamp(avg([safe_div(c, r) for c, r in zip(capex, revenue) if c and r], 0.04), 0.0, 0.2)
    div_growth = clamp(cagr(next((x for x in dividends if x and x > 0), 0), next((x for x in reversed(dividends) if x and x > 0), 0), max(1, len([x for x in dividends if x]) - 1), 0.03), -0.05, 0.10)
    rows = [
        ["Assumption", "Value", "Source / rationale"],
        ["Forecast years", 5, "Standard explicit forecast horizon"],
        ["Revenue growth", rev_growth, "Historical CAGR, clipped to avoid one-time distortions"],
        ["EBIT margin", ebit_margin, "Historical average from SEC XBRL"],
        ["Cash tax rate", tax_rate, "Income tax expense / pre-tax income"],
        ["D&A % revenue", da_pct, "Historical D&A / revenue"],
        ["Capex % revenue", capex_pct, "Historical capex / revenue"],
        ["NWC % revenue", 0.0, "Simplified placeholder; add working-capital schedule when balance-sheet parser is added"],
        ["WACC / discount rate", 0.10, "Editable placeholder until capital-structure beta/debt model is added"],
        ["Terminal growth", 0.025, "Long-run nominal growth placeholder"],
        ["Dividend growth", div_growth, "Historical dividend CAGR where available"],
        ["Cost of equity", 0.10, "Editable placeholder for dividend DCF"],
    ]
    for r, row in enumerate(rows, 4):
        for c, value in enumerate(row, 1):
            ws.cell(r, c, value)
    ws["A4"].fill = ws["B4"].fill = ws["C4"].fill = PatternFill("solid", fgColor=LIGHT)
    for cell in ws[4]:
        cell.font = Font(bold=True)
    for r in range(5, 17):
        ws.cell(r, 2).font = Font(color=BLUE)
        ws.cell(r, 2).fill = PatternFill("solid", fgColor=YELLOW if r in {13, 14} else "FFFFFF")
    for r in [6, 7, 8, 9, 10, 11, 12, 13, 14, 15]:
        ws.cell(r, 2).number_format = PCT
    ws["C11"].comment = Comment("Simplified by design. Replace with AR/AP/inventory/current-liability schedule when balance sheet normalization is implemented.", "Oasis")
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 92
    for row in range(5, 16):
        ws.cell(row, 3).alignment = Alignment(wrap_text=True, vertical="top")


def write_historical(wb: Workbook, node: dict, years: list[int], series: dict) -> None:
    ws = wb.create_sheet("Historical SEC Data")
    title(ws, "Historical SEC Data", "Amounts shown in $mm except share counts and per-share values")
    headers = ["Metric"] + years
    for c, value in enumerate(headers, 1):
        ws.cell(4, c, value)
        ws.cell(4, c).fill = PatternFill("solid", fgColor=LIGHT)
        ws.cell(4, c).font = Font(bold=True)
    metrics = [
        ("Revenue", "revenue", USD_MM, 1e6),
        ("EBIT", "ebit", USD_MM, 1e6),
        ("Pre-tax income", "pretax", USD_MM, 1e6),
        ("Income tax expense", "tax", USD_MM, 1e6),
        ("D&A", "da", USD_MM, 1e6),
        ("Capex", "capex", USD_MM, 1e6),
        ("Cash from operations", "cfo", USD_MM, 1e6),
        ("Dividends paid", "dividends", USD_MM, 1e6),
        ("Diluted/basic shares", "shares", NUM, 1),
    ]
    for r, (label, key, fmt, scale) in enumerate(metrics, 5):
        ws.cell(r, 1, label)
        for c, year in enumerate(years, 2):
            item = series.get(key, {}).get(year)
            ws.cell(r, c, (item[0] / scale) if item else None)
            ws.cell(r, c).number_format = fmt
            ws.cell(r, c).font = Font(color=GREEN)
            if item:
                ws.cell(r, c).comment = Comment(f"SEC XBRL tag: {item[2]}; filed {item[1]}", "Oasis")
    ws.column_dimensions["A"].width = 28


def write_cash_flow_dcf(wb: Workbook, node: dict, years: list[int], series: dict, facts: dict) -> None:
    ws = wb.create_sheet("Cash Flow DCF")
    forecast_years = [max(years) + i for i in range(1, 6)]
    cols = list(range(2, 2 + len(years) + len(forecast_years)))
    title(ws, "Cash Flow Based DCF", "Unlevered free cash flow; amounts in $mm except per-share values")
    ws.cell(4, 1, "Metric")
    for idx, year in enumerate(years + forecast_years, 2):
        ws.cell(4, idx, f"{year}A" if year in years else f"{year}E")
        ws.cell(4, idx).fill = PatternFill("solid", fgColor=LIGHT)
        ws.cell(4, idx).font = Font(bold=True)
    ws["A4"].fill = PatternFill("solid", fgColor=LIGHT)
    ws["A4"].font = Font(bold=True)
    labels = ["Revenue", "Revenue growth", "EBIT", "EBIT margin", "Cash taxes", "NOPAT", "D&A", "Capex", "Change in NWC", "Unlevered FCF", "Discount factor", "PV of FCF"]
    for r, label in enumerate(labels, 5):
        ws.cell(r, 1, label)
    for i, year in enumerate(years, 2):
        rev = series["revenue"].get(year)
        ebit = series["ebit"].get(year)
        tax = series["tax"].get(year)
        da = series["da"].get(year)
        capex = series["capex"].get(year)
        ws.cell(5, i, rev[0] / 1e6 if rev else None)
        ws.cell(7, i, ebit[0] / 1e6 if ebit else None)
        ws.cell(9, i, -abs(tax[0]) / 1e6 if tax else None)
        ws.cell(11, i, da[0] / 1e6 if da else None)
        ws.cell(12, i, -abs(capex[0]) / 1e6 if capex else None)
        ws.cell(6, i, None if i == 2 else f"={get_column_letter(i)}5/{get_column_letter(i-1)}5-1")
        ws.cell(8, i, f"={get_column_letter(i)}7/{get_column_letter(i)}5")
        ws.cell(10, i, f"={get_column_letter(i)}7+{get_column_letter(i)}9")
        ws.cell(13, i, 0)
        ws.cell(14, i, f"=SUM({get_column_letter(i)}10:{get_column_letter(i)}13)")
    first_f = 2 + len(years)
    for i, year in enumerate(forecast_years, first_f):
        prev = get_column_letter(i - 1)
        col = get_column_letter(i)
        ws.cell(5, i, f"={prev}5*(1+'Assumptions'!$B$6)")
        ws.cell(6, i, f"={col}5/{prev}5-1")
        ws.cell(7, i, f"={col}5*'Assumptions'!$B$7")
        ws.cell(8, i, f"={col}7/{col}5")
        ws.cell(9, i, f"=-{col}7*'Assumptions'!$B$8")
        ws.cell(10, i, f"={col}7+{col}9")
        ws.cell(11, i, f"={col}5*'Assumptions'!$B$9")
        ws.cell(12, i, f"=-{col}5*'Assumptions'!$B$10")
        ws.cell(13, i, f"=-({col}5-{prev}5)*'Assumptions'!$B$11")
        ws.cell(14, i, f"=SUM({col}10:{col}13)")
        ws.cell(15, i, f"=1/(1+'Assumptions'!$B$12)^({i-first_f+1}-0.5)")
        ws.cell(16, i, f"={col}14*{col}15")
    last_col = get_column_letter(first_f + 4)
    out_col = first_f + 6
    section(ws, 18, "Valuation Output", out_col + 1)
    outputs = [
        ("PV of forecast FCF", f"=SUM({get_column_letter(first_f)}16:{last_col}16)"),
        ("Terminal value", f"={last_col}14*(1+'Assumptions'!$B$13)/('Assumptions'!$B$12-'Assumptions'!$B$13)"),
        ("PV of terminal value", f"={get_column_letter(out_col)}20*{last_col}15"),
        ("Enterprise value", f"=SUM({get_column_letter(out_col)}19,{get_column_letter(out_col)}21)"),
    ]
    cash = latest_instant(facts, TAGS["cash"])
    debt_items = [latest_instant(facts, [tag]) for tag in TAGS["debt"]]
    debt = sum(item[0] for item in debt_items if item)
    shares = latest_instant(facts, TAGS["shares"], "shares")
    ws.cell(23, out_col - 1, "Cash")
    ws.cell(23, out_col, (cash[0] / 1e6) if cash else 0)
    ws.cell(24, out_col - 1, "Debt")
    ws.cell(24, out_col, debt / 1e6)
    ws.cell(25, out_col - 1, "Equity value")
    ws.cell(25, out_col, f"={get_column_letter(out_col)}22+{get_column_letter(out_col)}23-{get_column_letter(out_col)}24")
    ws.cell(26, out_col - 1, "Shares")
    ws.cell(26, out_col, shares[0] if shares else None)
    ws.cell(27, out_col - 1, "Implied value / share")
    ws.cell(27, out_col, f"={get_column_letter(out_col)}25*1000000/{get_column_letter(out_col)}26")
    for r, (label, formula) in enumerate(outputs, 19):
        ws.cell(r, out_col - 1, label)
        ws.cell(r, out_col, formula)
    for row in range(5, 28):
        row_border(ws, row, 1, out_col)
    for row in [5, 7, 9, 10, 11, 12, 13, 14, 16, 19, 20, 21, 22, 23, 24, 25]:
        for col in range(2, out_col + 1):
            ws.cell(row, col).number_format = USD_MM
    for row in [6, 8, 15]:
        for col in range(2, out_col + 1):
            ws.cell(row, col).number_format = PCT
    ws.cell(27, out_col).number_format = PER_SHARE


def write_dividend_dcf(wb: Workbook, node: dict, years: list[int], series: dict, facts: dict) -> None:
    ws = wb.create_sheet("Dividend DCF")
    forecast_years = [max(years) + i for i in range(1, 6)]
    title(ws, "Dividend Based DCF", "Equity value from distributable dividends; amounts in $mm except per-share values")
    ws.cell(4, 1, "Metric")
    for idx, year in enumerate(years + forecast_years, 2):
        ws.cell(4, idx, f"{year}A" if year in years else f"{year}E")
        ws.cell(4, idx).fill = PatternFill("solid", fgColor=LIGHT)
        ws.cell(4, idx).font = Font(bold=True)
    ws["A4"].fill = PatternFill("solid", fgColor=LIGHT)
    ws["A4"].font = Font(bold=True)
    labels = ["Dividends paid", "Dividend growth", "Discount factor", "PV of dividends"]
    for r, label in enumerate(labels, 5):
        ws.cell(r, 1, label)
    for i, year in enumerate(years, 2):
        divs = series["dividends"].get(year)
        ws.cell(5, i, abs(divs[0]) / 1e6 if divs else None)
        ws.cell(6, i, None if i == 2 else f"={get_column_letter(i)}5/{get_column_letter(i-1)}5-1")
    first_f = 2 + len(years)
    for i, _year in enumerate(forecast_years, first_f):
        prev = get_column_letter(i - 1)
        col = get_column_letter(i)
        ws.cell(5, i, f"={prev}5*(1+'Assumptions'!$B$14)")
        ws.cell(6, i, f"={col}5/{prev}5-1")
        ws.cell(7, i, f"=1/(1+'Assumptions'!$B$15)^({i-first_f+1}-0.5)")
        ws.cell(8, i, f"={col}5*{col}7")
    last_col = get_column_letter(first_f + 4)
    out_col = first_f + 6
    section(ws, 10, "Valuation Output", out_col + 1)
    ws.cell(11, out_col - 1, "PV of forecast dividends")
    ws.cell(11, out_col, f"=SUM({get_column_letter(first_f)}8:{last_col}8)")
    ws.cell(12, out_col - 1, "Terminal equity value")
    ws.cell(12, out_col, f"={last_col}5*(1+'Assumptions'!$B$13)/('Assumptions'!$B$15-'Assumptions'!$B$13)")
    ws.cell(13, out_col - 1, "PV of terminal value")
    ws.cell(13, out_col, f"={get_column_letter(out_col)}12*{last_col}7")
    ws.cell(14, out_col - 1, "Equity value")
    ws.cell(14, out_col, f"=SUM({get_column_letter(out_col)}11,{get_column_letter(out_col)}13)")
    shares = latest_instant(facts, TAGS["shares"], "shares")
    ws.cell(15, out_col - 1, "Shares")
    ws.cell(15, out_col, shares[0] if shares else None)
    ws.cell(16, out_col - 1, "Implied value / share")
    ws.cell(16, out_col, f"={get_column_letter(out_col)}14*1000000/{get_column_letter(out_col)}15")
    for row in range(5, 17):
        row_border(ws, row, 1, out_col)
    for row in [5, 8, 11, 12, 13, 14]:
        for col in range(2, out_col + 1):
            ws.cell(row, col).number_format = USD_MM
    for row in [6, 7]:
        for col in range(2, out_col + 1):
            ws.cell(row, col).number_format = PCT
    ws.cell(16, out_col).number_format = PER_SHARE


def write_checks(wb: Workbook, method: str) -> None:
    ws = wb.create_sheet("Checks")
    title(ws, "Model Checks", "Formula and source completeness checks")
    rows = [
        ["Check", "Status", "Notes"],
        ["SEC companyfacts loaded", "OK", "Workbook generated only after companyfacts are available."],
        ["No browser-side SEC fetch", "OK", "SEC does not support CORS; export is backend-generated."],
        ["Assumptions editable", "OK", "Blue input cells live on Assumptions tab."],
        ["Model type", method.replace("_", " ").title(), "Generated on demand."],
    ]
    for r, row in enumerate(rows, 4):
        for c, value in enumerate(row, 1):
            ws.cell(r, c, value)
    for cell in ws[4]:
        cell.fill = PatternFill("solid", fgColor=LIGHT)
        cell.font = Font(bold=True)
    for r in range(5, 9):
        ws.cell(r, 2).fill = PatternFill("solid", fgColor=OK if ws.cell(r, 2).value == "OK" else YELLOW)
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 80


def build_dcf_workbook(entity_id: str, method: str = "cash_flow") -> Path:
    if method not in {"cash_flow", "dividend"}:
        raise ValueError("method must be cash_flow or dividend")
    node = load_node(entity_id)
    facts, facts_path = load_facts(node)
    years, series = history(facts)
    if len(years) < 2:
        raise ValueError("not enough annual SEC facts to build a DCF")
    wb = Workbook()
    wb.remove(wb.active)
    write_assumptions(wb, node, facts, years, series, method)
    write_historical(wb, node, years, series)
    if method == "cash_flow":
        write_cash_flow_dcf(wb, node, years, series, facts)
    else:
        write_dividend_dcf(wb, node, years, series, facts)
    add_sources(wb, node, facts_path, method)
    write_checks(wb, method)
    style_workbook(wb)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    path = OUTPUTS / f"{slug(node.get('t') or node['id'])}_{method}_dcf.xlsx"
    wb.save(path)
    return path


def main() -> None:
    import sys

    entity_id = sys.argv[1] if len(sys.argv) > 1 else "BLK"
    method = sys.argv[2] if len(sys.argv) > 2 else "cash_flow"
    print(build_dcf_workbook(entity_id, method))


if __name__ == "__main__":
    main()
