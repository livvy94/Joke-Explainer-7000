import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from bot_secrets import SPECIALISTS_SPREADSHEET_ID
from hq_strings import * 
from hq_discord import * 
from hq_metadata import desc_to_dict, get_music_from_desc, remove_links
from discord import Guild

from typing import NamedTuple
from datetime import datetime, timezone

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


class RawSheetData(NamedTuple):
    rows: list[list[str]]
    error_strings: list[str]

async def get_raw_sheet_data(spreadsheet_id: str, sheet_name: str, row_start: int, last_column: str, credentials: Credentials) -> RawSheetData: 
    cells: list[list[str]] = []
    error_strings: list[str] = []

    try:
        service = build("sheets", "v4", credentials=credentials)
        output = await run_blocking(
            service.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                ranges=f"{sheet_name}!A{row_start}:{last_column}",
                fields="sheets.data.rowData.values.formattedValue",
                includeGridData=True,
            )
            .execute
        )
        if "rowData" in output["sheets"][0]["data"][0]:
            for rowJson in output["sheets"][0]["data"][0]["rowData"]:
                rowList = []
                for cell in rowJson.get("values", []):
                    rowList.append(cell.get("formattedValue", "").strip())
                cells.append(rowList)
    except Exception as error:
        await log_exception(f"Failed get google sheet data from {sheet_name}", error, error_strings, True)

    return RawSheetData(cells, error_strings) 


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
                "endColumnIndex": ending_column_index,
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


class SpecialistEntry(NamedTuple):
    specialists: str 
    notes: str
    game_title: str
    alternate_game_titles: list[str] 
    composer_name: str
    alternate_composer_names: list[str] 
    source: str
    alternate_source_names: list[str]

class SourceExclusion(NamedTuple):
    track_title: str
    game_title: str
    skip_database_search: bool
    skip_youtube_search_link: bool
    no_results_message: str
    notes: str

class QoCSheetData(NamedTuple):
    specialist_entries: list[SpecialistEntry]
    source_exclusions: list[SourceExclusion]
    error_strings: list[str]

CREDENTIALS = None
SHEET_LAST_UPDATED: datetime = datetime.now(timezone.utc)
QOC_SHEET_DATA: QoCSheetData = QoCSheetData([], [], []) 

class GetQoCSheetDataDesc(NamedTuple):
    bypass_cache: bool = False

async def refresh_credentials() -> Credentials:
    global CREDENTIALS

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
        await log_exception("Failed to set up google sheets credentials", error, [], True)

    return CREDENTIALS


async def should_call_sheet_api(bypass_cache: bool) -> bool:
    try:
        result =True 
        ##NOTE: (Ahmayk) We check to see the last modified time and only fetch new info if the sheet appears to be updated.
        # Google drive doesn't seem to update this very quickly, in testing it can take up to around 5 minutes,
        # but this is 100% worth it for the speed boost since changes to the sheet don't really need to take effect immediatley
        service_drive = build("drive", "v3", credentials=CREDENTIALS)
        file = (
            service_drive.files()
            .get(fileId=SPECIALISTS_SPREADSHEET_ID, fields="id, name, modifiedTime")
            .execute()
        )
        modified_time = datetime.fromisoformat(file["modifiedTime"].replace("Z", "+00:00"))
        global SHEET_LAST_UPDATED 
        # print(f"SHEET_LAST_UPDATED: {str(SHEET_LAST_UPDATED)} modified time: {str(modified_time)}")
        ##NOTE: (Ahmayk) If we do want changes to take effect immedatley (calling !specialist directly for instance) 
        #then bypassing the skip will guarentee that we are showing updated data 
        if modified_time == SHEET_LAST_UPDATED and not bypass_cache:
            result = False 
        SHEET_LAST_UPDATED = modified_time
    except Exception as error:
        await log_exception("Failed to get modified time from google sheet", error, [], True)
    return result


async def get_qoc_sheet_data(desc: GetQoCSheetDataDesc) -> QoCSheetData: 

    global CREDENTIALS
    global QOC_SHEET_DATA 

    qoc_sheet_data = QOC_SHEET_DATA 
    error_strings: list[str] = []

    if not CREDENTIALS or not CREDENTIALS.valid or CREDENTIALS.expired:
        await refresh_credentials()

    if not CREDENTIALS or not CREDENTIALS.valid:
        error_strings.append("**Google sheet credentials not valid.**")

    if CREDENTIALS and CREDENTIALS.valid:

        call_sheet_api = await should_call_sheet_api(desc.bypass_cache)

        if call_sheet_api or not QOC_SHEET_DATA:

            specialist_entries: list[SpecialistEntry] = []

            game_sheet_data = await get_raw_sheet_data(SPECIALISTS_SPREADSHEET_ID, "Game Strict Rules", 3, 'D', CREDENTIALS)
            error_strings.extend(game_sheet_data.error_strings)
            for row in game_sheet_data.rows:
                if len(row) > 1:
                    game_title = row[0] 
                    specialists = row[1]
                    alternate_game_titles: list[str] = [] 
                    if len(row) > 2:
                        names = row[2].split("/")
                        for name in names:
                            alternate_game_titles.append(name.strip())
                    notes = "" 
                    if len(row) > 3:
                        notes = row[3]
                    specialist_entries.append(SpecialistEntry(specialists, notes, game_title, alternate_game_titles, "", [], "", []))

            if not len(error_strings):
                composer_sheet_data = await get_raw_sheet_data(SPECIALISTS_SPREADSHEET_ID, "Composer Strict Rules", 3, 'D', CREDENTIALS)
                error_strings.extend(composer_sheet_data.error_strings)
                for row in composer_sheet_data.rows:
                    if len(row) > 1:
                        composer_string = row[0]
                        specialists = row[1]
                        alternate_composer_names = []
                        if len(row) > 2:
                            names = row[2].split("/") 
                            for name in names:
                                alternate_composer_names.append(name.strip())
                        notes = "" 
                        if len(row) > 3:
                            notes = row[3]
                        specialist_entries.append(SpecialistEntry(specialists, notes, "", [], composer_string, alternate_composer_names, "", []))

            if not len(error_strings):
                source_sheet_data = await get_raw_sheet_data(SPECIALISTS_SPREADSHEET_ID, "Source Strict Rules", 3, 'D', CREDENTIALS)
                error_strings.extend(source_sheet_data.error_strings)
                for row in source_sheet_data.rows:
                    if len(row) > 1:
                        source_string = row[0]
                        specialists = row[1]
                        alternate_source_names = []
                        if len(row) > 2:
                            names = row[2].split("/") 
                            for name in names:
                                alternate_source_names.append(name.strip())
                        notes = "" 
                        if len(row) > 3:
                            notes = row[3]
                        specialist_entries.append(SpecialistEntry(specialists, notes, "", [], "", [], source_string, alternate_source_names))

            source_exclusions: list[SourceExclusion] = []
            if not len(error_strings):
                source_exclusion_sheet_data = await get_raw_sheet_data(SPECIALISTS_SPREADSHEET_ID, "Source Exclusions", 3, 'F', CREDENTIALS)
                error_strings.extend(source_exclusion_sheet_data.error_strings)
                for row in source_exclusion_sheet_data.rows:
                    if len(row) > 1 and len(row[1]):
                        track_title = row[0] 
                        game_title = row[1]
                        skip_database_search = False
                        if len(row) > 2:
                            skip_database_search = (row[2] == 'TRUE')
                        skip_youtube_search_link = False
                        if len(row) > 3:
                            skip_youtube_search_link = (row[3] == 'TRUE')
                        no_results_message = ""
                        if len(row) > 4:
                            no_results_message = row[4]
                        notes = ""
                        if len(row) > 5:
                            notes = row[5]
                        source_exclusions.append(SourceExclusion(track_title, game_title, skip_database_search, skip_youtube_search_link, no_results_message, notes))

            if not len(error_strings):
                qoc_sheet_data = QoCSheetData(specialist_entries, source_exclusions, error_strings)
                QOC_SHEET_DATA = qoc_sheet_data 

    return qoc_sheet_data 


def search_specialists(submissionText: str, qoc_sheet_data: QoCSheetData, guild: Guild) -> str:
    result = ""

    title = get_raw_rip_title(submissionText)
    if title is None: 
        title = submissionText

    description = get_rip_description(submissionText)
    desc_dict, msgs = desc_to_dict(description, 1)
    track_string = get_music_from_desc(desc_dict)
    game_and_track_pairs = parseTitle(title, ' - ', track_string)

    sources_input = submissionText 
    chunks = submissionText.split('```')
    if len(chunks) >= 2:
        sources_input = chunks[2]
        sources_input += get_raw_rip_author(submissionText)

    sources_input = remove_links(sources_input)
    sources_input = sources_input.lower()

    composer_inputs = [] 
    composer_matches = ["Composer", "Composer", "Arrangement"]
    for match in composer_matches:
        if match in desc_dict:
            composer_inputs.append(desc_dict[match].lower())
    if not len(composer_inputs):
        composer_inputs.append(submissionText.lower())

    stop_emoji = '🛑'
    for e in guild.emojis:
        if e.name.lower() == "stop":
            stop_emoji = str(e)

    for specialist_entry in qoc_sheet_data.specialist_entries:

        is_match = False 
        for game_and_track_pair in game_and_track_pairs:
            if len(specialist_entry.game_title) and specialist_entry.game_title.lower() == game_and_track_pair.game_name.lower():
                result += f'\n{stop_emoji} {specialist_entry.game_title}: **{specialist_entry.specialists}**'
                break

            for alternate_title in specialist_entry.alternate_game_titles:
                if len(alternate_title) and alternate_title.lower() in game_and_track_pair.game_name.lower():
                    is_match = True
                    result += f'\n{stop_emoji} {specialist_entry.game_title}: **{specialist_entry.specialists}**'
                    if alternate_title.lower() not in specialist_entry.game_title.lower():
                        result += f' [{alternate_title}]'
                    break

        if is_match:
            continue

        if len(sources_input):
            if len(specialist_entry.source) and specialist_entry.source.lower() in sources_input:
                result += f'\n{stop_emoji} {specialist_entry.source}: **{specialist_entry.specialists}**'
                continue

        for alternate_source_name in specialist_entry.alternate_source_names:
            if len(alternate_source_name) and alternate_source_name.lower() in sources_input:
                is_match = True
                result += f'\n{stop_emoji} {specialist_entry.source}: **{specialist_entry.specialists}**'
                if alternate_source_name not in specialist_entry.source:
                    result += f' [{alternate_source_name}]'
                break

        if is_match:
            continue

        if len(composer_inputs):
            for composer_input in composer_inputs:
                if len(specialist_entry.composer_name) and specialist_entry.composer_name.lower() in composer_input:
                    result += f'\n{stop_emoji} {specialist_entry.composer_name}: **{specialist_entry.specialists}**'
                    is_match = True
                    break

                for alternate_composer_name in specialist_entry.alternate_composer_names:
                    if len(alternate_composer_name) and alternate_composer_name.lower() in composer_input:
                        is_match = True
                        result += f'\n{stop_emoji} {specialist_entry.composer_name}: **{specialist_entry.specialists}**'
                        if alternate_composer_name not in specialist_entry.composer_name:
                            result += f' [{alternate_composer_name}]'
                        break
                if is_match:
                    break

    result = result.strip()

    return result
