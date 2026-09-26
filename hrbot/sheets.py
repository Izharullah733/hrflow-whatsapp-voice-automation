"""Synchronize dedicated worksheets from SQLite, including new extra columns."""

from __future__ import annotations

from .config import Settings
from .storage import Store


BASE_HEADERS = ["ID", "Name", "Field", "Supervisor", "Registration Date"]
COMP_HEADERS = ["Name", "Type", "Amount PKR", "Updated At"]


def _safe_cell(value: object) -> str:
    text = str(value if value is not None else "")
    return "'" + text if text[:1] in {"=", "+", "-", "@"} else text


def _worksheet(book, title: str, rows: int, columns: int):
    try:
        return book.worksheet(title)
    except Exception as exc:
        import gspread
        if not isinstance(exc, gspread.WorksheetNotFound):
            raise
        return book.add_worksheet(title=title, rows=max(rows, 100), cols=max(columns, 12))


def sync(store: Store, settings: Settings) -> tuple[int, int]:
    if not settings.sheet_id:
        return 0, 0
    import gspread

    client = gspread.service_account(filename=str(settings.service_account_file))
    book = client.open_by_key(settings.sheet_id)
    records = store.records()
    extras = sorted({key for row in records for key in row["extras"]}, key=str.casefold)
    headers = BASE_HEADERS + extras
    sheet = _worksheet(book, "Registrations", len(records) + 1, len(headers))
    if sheet.col_count < len(headers):
        sheet.resize(cols=len(headers))
    existing = sheet.get_all_values()
    existing_headers = existing[0] if existing else []
    if existing_headers != headers:
        sheet.update(range_name="A1", values=[headers], value_input_option="RAW")
    by_id = {row[0]: index for index, row in enumerate(existing[1:], start=2) if row}
    inserts = []
    for record in records:
        values = [record["id"], record["name"], record["field"], record["supervisor"], record["registration_date"]]
        values.extend(record["extras"].get(key, "") for key in extras)
        values = [_safe_cell(value) for value in values]
        if record["id"] in by_id:
            sheet.update(range_name=f"A{by_id[record['id']]}", values=[values], value_input_option="RAW")
        else:
            inserts.append(values)
    if inserts:
        sheet.append_rows(inserts, value_input_option="RAW")

    compensation = [dict(row) for row in store.connection.execute("SELECT name,type,amount,updated_at FROM compensation ORDER BY name_key,type")]
    comp_sheet = _worksheet(book, "Compensation", len(compensation) + 1, len(COMP_HEADERS))
    comp_sheet.clear()
    comp_sheet.update(range_name="A1", values=[COMP_HEADERS] + [
        [_safe_cell(item["name"]), item["type"], item["amount"], item["updated_at"]] for item in compensation
    ], value_input_option="RAW")
    return len(records), len(compensation)
