import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def get_gspread_client(sa_info: dict) -> gspread.Client:
    creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return gspread.authorize(creds)


def load_sheet(gc: gspread.Client, sheet_url: str, worksheet_name: str = None):
    spreadsheet = gc.open_by_url(sheet_url)
    if worksheet_name:
        ws = spreadsheet.worksheet(worksheet_name)
    else:
        ws = spreadsheet.get_worksheet(0)
    data = ws.get_all_records()
    df = pd.DataFrame(data)
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
        if col_header not in headers:
            headers.append(col_header)
            col_index = len(headers)
            ws.update_cell(1, col_index, col_header)
        else:
            col_index = headers.index(col_header) + 1

        col_letter = gspread.utils.rowcol_to_a1(1, col_index)[:-1]
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
