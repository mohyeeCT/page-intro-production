import unittest

import pandas as pd

from utils.sheets import load_sheet, write_results_batch


class FakeSpreadsheet:
    def __init__(self):
        self.batch_payload = None

    def values_batch_update(self, payload):
        self.batch_payload = payload


class FakeWorksheet:
    def __init__(self, values):
        self._values = values
        self.spreadsheet = FakeSpreadsheet()

    def get_all_values(self):
        return self._values

    def row_values(self, row):
        return self._values[0]


class FakeClient:
    def __init__(self, worksheet):
        self._worksheet = worksheet

    def open_by_url(self, url):
        return self

    def get_worksheet(self, index):
        return self._worksheet

    def worksheet(self, name):
        return self._worksheet


class IntroSheetTests(unittest.TestCase):
    def test_load_sheet_preserves_headers_and_blank_cells(self):
        ws = FakeWorksheet([["URL", "H1"], ["https://example.com", ""]])
        df, _ws = load_sheet(FakeClient(ws), "https://sheet")

        self.assertEqual(list(df.columns), ["URL", "H1"])
        self.assertEqual(df.iloc[0]["H1"], "")

    def test_write_results_batches_new_headers(self):
        ws = FakeWorksheet([["URL"]])
        df = pd.DataFrame([{"intro_copy": "Copy"}])

        write_results_batch(ws, df, {"intro_copy": "Intro Copy"})

        data = ws.spreadsheet.batch_payload["data"]
        self.assertEqual(data[0]["values"], [["Intro Copy"]])
        self.assertEqual(data[1]["values"], [["Copy"]])


if __name__ == "__main__":
    unittest.main()
