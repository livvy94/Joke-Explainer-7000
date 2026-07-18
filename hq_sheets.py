import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import typing
from enum import Enum
from typing import NamedTuple

from hq_discord import run_blocking, log_exception, write_log

CREDENTIALS = None

class CredentialsAndErrors(NamedTuple):
    credentials: Credentials | None
    error_strings: list[str]

async def refresh_credentials() -> CredentialsAndErrors:
    global CREDENTIALS
    error_strings: list[str] = []

    # NOTE: (Ahmayk) login required in web browser to access google sheets doc
    # then token.json is created and saves login info
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    try: 
        if os.path.exists("token.json"):
            CREDENTIALS = Credentials.from_authorized_user_file("token.json", scopes)

        if not CREDENTIALS or not CREDENTIALS.valid:
            if CREDENTIALS and CREDENTIALS.expired and CREDENTIALS.refresh_token:
                try:
                    CREDENTIALS.refresh(Request())
                except Exception as error:
                    await write_log(f"Failed to refresh google api token: {str(error)}")

            should_tell_success = False
            if not CREDENTIALS or (CREDENTIALS and not CREDENTIALS.valid):
                should_tell_success = True 
                await write_log("Creating new Google Api token...")
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", scopes)
                CREDENTIALS = flow.run_local_server(port=0)

            with open("token.json", "w") as token:
                token.write(CREDENTIALS.to_json())

            if CREDENTIALS and CREDENTIALS.valid and should_tell_success:
                await write_log("Google API credentials set up successfully.")

    except Exception as error:
        await log_exception("Failed to set up google sheets credentials", error, error_strings, True)

    credentials = None
    if CREDENTIALS and CREDENTIALS.valid:
        credentials = CREDENTIALS
    else:
        await write_log("**Google sheet credentials not valid.**")
        error_strings.append("Google sheet credentials not valid. (Contact bot maintainer)")

    return CredentialsAndErrors(credentials, error_strings)


class SheetInfo(NamedTuple):
    sheet_exists: bool
    spreadsheet_tab_id: int
    spreadsheet_url: str
    row_count: int
    column_count: int
    error_strings: list[str]


async def get_sheet_info(spreadsheet_id: str, sheet_name: str, credentials: Credentials) -> SheetInfo: 
    sheet_exists = False
    spreadsheet_tab_id = 0 
    spreadsheet_url = ""
    row_count = 0
    column_count = 0
    error_strings: list[str] = []
    try:
        service = build("sheets", "v4", credentials=credentials)
        output = await run_blocking(
            service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, ranges=sheet_name)
            .execute
        )
        sheet_exists = True
        spreadsheet_tab_id = int(output['sheets'][0]['properties']['sheetId'])
        spreadsheet_url = output['spreadsheetUrl']
        row_count = output['sheets'][0]['properties']['gridProperties']['rowCount']
        column_count = output['sheets'][0]['properties']['gridProperties']['columnCount']
    except Exception as error:
        if not isinstance(error, HttpError) or "Unable to parse range" not in error.reason:
            await log_exception(f"Google sheet API data call failed for {sheet_name}", error, error_strings, True)

    return SheetInfo(sheet_exists, spreadsheet_tab_id, spreadsheet_url, row_count, column_count, error_strings)


class ReadCell(NamedTuple):
    text: str
    hyperlink: str
    chip_urls: list[str]

class ReadSheetResult(NamedTuple):
    rows: list[list[ReadCell]]
    error_strings: list[str]

async def read_sheet(spreadsheet_id: str, sheet_name: str, range: str, credentials: Credentials) -> ReadSheetResult:
    read_cells: list[list[ReadCell]] = []
    error_strings: list[str] = []

    try:
        service = build("sheets", "v4", credentials=credentials)
        output = await run_blocking(
            service.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                ranges=f"{sheet_name}!{range}",
                fields="sheets.data.rowData.values.formattedValue," \
                        "sheets.data.rowData.values.hyperlink," \
                        "sheets.data.rowData.values.chipRuns",
                includeGridData=True,
            )
            .execute
        )
        if "rowData" in output["sheets"][0]["data"][0]:
            for rowJson in output["sheets"][0]["data"][0]["rowData"]:
                rowList = []
                for cell in rowJson.get("values", []):
                    text = cell["formattedValue"]
                    hyperlink = ""
                    if "hyperlink" in cell:
                        hyperlink = cell["hyperlink"]
                    chip_urls = []
                    if "chipRuns" in cell:
                        for chip_run in cell["chipRuns"]:
                            if 'chip' in chip_run:
                                chip_urls.append(chip_run['chip']['richLinkProperties']['uri'])
                    rowList.append(ReadCell(text, hyperlink, chip_urls))
                read_cells.append(rowList)
    except Exception as error:
        await log_exception(f"Failed get google sheet data from {sheet_name}", error, error_strings, True)

    return ReadSheetResult(read_cells, error_strings) 


class BatchValuesGetResult(NamedTuple):
    batches: list[list[list[str]]]
    error_strings: list[str]

async def batch_get_values_from_sheet(spreadsheet_id: str, ranges: list[str], credentials: Credentials) -> BatchValuesGetResult:

    batches: list[list[list[str]]] = []
    error_strings: list[str] = []

    try:
        service = build("sheets", "v4", credentials=credentials)
        output = await run_blocking(
            service.spreadsheets().values().batchGet(
                spreadsheetId=spreadsheet_id,
                ranges=ranges
            ).execute
        )

        if "valueRanges" in output:
            for value_range_data in output["valueRanges"]:
                rowList = []
                for cell in value_range_data.get("values", []):
                    rowList.append(cell)
                batches.append(rowList)
    except Exception as error:
        await log_exception(f"Failed get google sheet data", error, error_strings, True)

    return BatchValuesGetResult(batches, error_strings) 


def parse_create_sheet_request(name: str) -> dict[str, typing.Any]:
    result = {
        'addSheet': {
            'properties': {
                'title': name,
            }
        }
    }
    return result

class ColorRGBFloat(NamedTuple):
    r: float
    g: float
    b: float

class WRAP_STRATEGY(Enum):
    NULL = 0 
    OVERFLOW_CELL = "OVERFLOW_CELL"
    CLIP = "CLIP"
    WRAP = "WRAP"

class Cell(NamedTuple):
    text: str = "" 
    formula_text: str = ""
    font_size: int = 0
    is_bold: bool = False
    foreground_color: ColorRGBFloat = ColorRGBFloat(0, 0, 0)
    background_color: ColorRGBFloat = ColorRGBFloat(0, 0, 0)
    wrap_strategy: WRAP_STRATEGY = WRAP_STRATEGY.NULL 

def cell_bulk_create(texts: list[str], format_cell: Cell) -> list[Cell]:
    result = []
    for text in texts:
        result.append(
            Cell(
                text=text,
                font_size=format_cell.font_size,
                is_bold=format_cell.is_bold,
                foreground_color=format_cell.foreground_color,
                background_color=format_cell.background_color,
                wrap_strategy=format_cell.wrap_strategy,
            )
        )
    return result

def cell_bulk_create_formula(formula_texts: list[str], format_cell: Cell) -> list[Cell]:
    result = []
    for formula_text in formula_texts:
        result.append(
            Cell(
                formula_text=formula_text,
                font_size=format_cell.font_size,
                is_bold=format_cell.is_bold,
                foreground_color=format_cell.foreground_color,
                background_color=format_cell.background_color,
                wrap_strategy=format_cell.wrap_strategy,
            )
        )
    return result

def format_hyperlink_formula(url: str, text: str) -> str:
    url = url.replace('"', '""')
    text = text.replace('"', '""')
    return f'=HYPERLINK("{url}", "{text}")'


def parse_update_cells_requests(spreadsheet_tab_id: int, cell_rows: list[list[Cell]], 
                                starting_row_index: int, starting_column_index: int) -> list[dict[str, typing.Any]]:
    requests = []

    for i, cell_row in enumerate(cell_rows):
        cell_data_row = []
        for cell in cell_row:
            cell_data: dict[str, typing.Any] = {}
            
            if len(cell.text):
                cell_data["userEnteredValue"] = {}
                cell_data["userEnteredValue"]["stringValue"] = cell.text

            if len(cell.formula_text):
                if "userEnteredValue" not in cell_data:
                    cell_data["userEnteredValue"] = {}
                cell_data['userEnteredValue']['formulaValue'] = cell.formula_text

            cell_format: dict[str, typing.Any] = {}
            has_forground_color = (
                cell.foreground_color.r or cell.foreground_color.g or cell.foreground_color.b
            )
            if cell.font_size or cell.is_bold or has_forground_color:
                cell_format["textFormat"] = {}
                if has_forground_color:
                    cell_format["textFormat"]["foregroundColorStyle"] = {
                        "rgbColor": {
                            "red": cell.foreground_color.r,
                            "green": cell.foreground_color.g,
                            "blue": cell.foreground_color.b
                        }
                    } 
                if cell.font_size:
                    cell_format["textFormat"]["fontSize"] = cell.font_size
                if cell.is_bold:
                    cell_format["textFormat"]["bold"] = cell.is_bold

            if (cell.background_color.r
                or cell.background_color.g
                or cell.background_color.b
            ):
                cell_format["backgroundColorStyle"] = {
                    "rgbColor": {
                        "red": cell.background_color.r,
                        "green": cell.background_color.g,
                        "blue": cell.background_color.b
                    }
                }

            if cell.wrap_strategy:
                cell_format["wrapStrategy"] = str(cell.wrap_strategy.value)

            if len(cell_format):
                cell_data["userEnteredFormat"] = cell_format
            cell_data_row.append(cell_data)

        request = {
            "updateCells": {
                "rows": {
                    "values": cell_data_row
                },
                "fields": "*",
                "start": {
                    "sheetId": spreadsheet_tab_id,
                    "rowIndex": starting_row_index + i,
                    "columnIndex": starting_column_index
                }
            }
        }
        requests.append(request)

    return requests 


def parse_update_cells_clear_request(spreadsheet_tab_id: int, 
                                     starting_row_index: int, ending_row_index: int,
                                     starting_column_index: int, ending_column_index: int) -> dict[str, typing.Any]:
    result = {
        "updateCells": {
            "fields": "*",
            "range": {
                "sheetId": spreadsheet_tab_id,
                "startRowIndex": starting_row_index,
                "endRowIndex": ending_row_index,
                "startColumnIndex": starting_column_index,
                ##NOTE: (Ahmayk) endIndex is expecting expecting the row/column after the last one (exclusive) for some reason,
                # but that's confusing so our API just does what is more intuitive and does inclusive.
                "endColumnIndex": ending_column_index + 1,
            }
        }
    }
    return result


class SHEET_DIMENSION(Enum):
    ROWS = "ROWS"
    COLUMNS = "COLUMNS"

def parse_update_dimension_properties_request(sheet_id: int, pixel_size: int, sheet_dimension: SHEET_DIMENSION, 
                                              start_index: int, end_index: int) -> dict[str, typing.Any]:
    result = {
        "updateDimensionProperties": {
            "properties": {
                "pixelSize": pixel_size,
            },
            "fields": "pixelSize",
            "range": {
                "sheetId": sheet_id,
                "dimension": sheet_dimension.value,
                "startIndex": start_index,
                ##NOTE: (Ahmayk) endIndex is expecting expecting the row/column after the last one (exclusive) for some reason,
                # but that's confusing so our API just does what is more intuitive and does inclusive.
                "endIndex": end_index + 1
            }
        }
    }
    return result


class BatchUpdateResponse(NamedTuple):
    response: typing.Any | None
    error_strings: list[str]

async def send_sheet_batch_update(spreadsheet_id: str, requests: list[dict[str, typing.Any]],
                                    credentials: Credentials) -> BatchUpdateResponse:
    response = None
    error_strings: list[str] = []
        
    try:
        service = build("sheets", "v4", credentials=credentials)
        response = await run_blocking(
            service.spreadsheets()
            .batchUpdate(
                spreadsheetId=spreadsheet_id,
                body = {"requests": requests}
            )
            .execute
        )
    except Exception as error:
        await log_exception(f"Sending google sheets batch requests failed", error, error_strings, True)

    return BatchUpdateResponse(response, error_strings) 


async def clear_cells(spreadsheet_id: str, sheet_name: str, 
                      range: str, credentials: Credentials) -> bool:
    result = False
    try:
        service = build("sheets", "v4", credentials=credentials)
        output = await run_blocking(
            service.spreadsheets()
            .values()
            .clear(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!{range}"
            )
            .execute
        )
        print(f"Cells cleared: {output.get('clearedRange')}")
        result = True
    except Exception as error:
        await log_exception(f"Failed to clear google sheet cells in {sheet_name}", error, [], True)
    return result


