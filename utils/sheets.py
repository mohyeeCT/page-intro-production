import pandas as pd

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _rowcol_to_a1(row: int, col: int) -> str:
    letters = ""
    while col:
        col, remainder = divmod(col - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


def get_gspread_client(sa_info: dict):
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return gspread.authorize(creds)


def load_sheet(gc, sheet_url: str, worksheet_name: str = None):
    spreadsheet = gc.open_by_url(sheet_url)
    if worksheet_name:
        ws = spreadsheet.worksheet(worksheet_name)
    else:
        ws = spreadsheet.get_worksheet(0)
    values = ws.get_all_values()
    if not values:
        return pd.DataFrame(), ws
    headers = values[0]
    rows = values[1:]
    width = len(headers)
    normalised_rows = [row + [""] * (width - len(row)) for row in rows]
    df = pd.DataFrame(normalised_rows, columns=headers)
    return df, ws


def write_results_batch(ws, df: pd.DataFrame, result_col_map: dict):
    """
    Writes result columns back to the sheet using batch API calls.
    result_col_map: { df_column_key: sheet_header_name }
    Never uses cell-by-cell updates.
    """
    headers = ws.row_values(1)
    all_updates = []

    for col_key, col_header in result_col_map.items():
        if col_key not in df.columns:
            continue
        if col_header not in headers:
            headers.append(col_header)
            col_index = len(headers)
            all_updates.append({
                "range": _rowcol_to_a1(1, col_index),
                "values": [[col_header]]
            })
        else:
            col_index = headers.index(col_header) + 1

        col_letter = _rowcol_to_a1(1, col_index)[:-1]
        values = df[col_key].tolist()
        range_name = f"{col_letter}2:{col_letter}{len(values) + 1}"
        all_updates.append({
            "range": range_name,
            "values": [[str(v) if pd.notna(v) else ""] for v in values]
        })

    if all_updates:
        ws.spreadsheet.values_batch_update({
            "valueInputOption": "RAW",
            "data": all_updates
        })
