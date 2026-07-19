
from hq_discord import *
from hq_youtube import *
from hq_sheets import *
from hq_database import *
from dateutil import tz, relativedelta

from bot_secrets import YOUTUBE_API_KEY, PLAYLISTS_SPREADSHEET_ID
from enum import auto
from dataclasses import dataclass

def urls_from_read_cell(read_cell: ReadCell) -> list[str]:
    result: list[str] = []
    if len(read_cell.chip_urls):
        result = read_cell.chip_urls
    if len(read_cell.hyperlink):
        result.append(read_cell.hyperlink)
    if not len(result):
        result = read_cell.text.split('\n')
    return result

def find_youtube_video(url: str, row_index: int, playlist_videos: list[PlaylistVideo], user_errors_row: list[str]) -> PlaylistVideo:
    result = PlaylistVideo("", datetime.min, "", "", 0, False)
    split = url.split('watch?v=')
    if len(split) == 2:
        is_found = False
        video_id = split[1]
        for playlist_video in playlist_videos:
            if playlist_video.video_id == video_id:
                is_found = True
                result = playlist_video
                break
        if not is_found:
            user_errors_row.append(f"YouTube URL not found in playlist: `https://www.youtube.com/watch?v={video_id}`")
    else:
        user_errors_row.append(f"Invalid URL: `{url}`. (row {row_index + 4}).")
    return result

def format_sheet_timecode(preface: str) -> str: 
    date = datetime.now(tz=tz.UTC)
    date = date.astimezone(tz.gettz('America/Los_Angeles'))
    timestring = date.strftime("%a, %b %d %Y - %I:%M %p (%S sec) (PST)") 
    return f'{preface}\n{timestring}'

class SortedType(Enum):
    MATCHED = auto()
    UNMATCHED = auto()
    PRIVATE = auto()
    MANUAL_BEGINNING = auto()
    MANUAL_INSERT = auto()

class OutputVideoEntry(NamedTuple):
    sorted_type: SortedType
    track_and_mixname: str
    game_name: str
    playlist_video: PlaylistVideo 

class SheetOptions(NamedTuple):
    group_by_mixname: bool = False

class SortPlaylistVideosResult(NamedTuple):
    ouput_video_entries: list[OutputVideoEntry]
    sheet_options: SheetOptions
    requests: list[dict[str, typing.Any]]
    error_strings: list[str]
    user_errors: list[str]

async def sort_playlist_videos(sheet_name: str, spreadsheet_tab_id: int, playlist_videos: list[PlaylistVideo], 
                               last_row_index: int, credentials: Credentials) -> SortPlaylistVideosResult:

    error_strings: list[str] = []
    user_errors: list[str] = []

    batch_values_get_result: BatchValuesGetResult = BatchValuesGetResult([], []) 
    read_sheet_result: ReadSheetResult = ReadSheetResult([], [])
    if credentials and credentials.valid:
        batch_values_get_result = await batch_get_values_from_sheet(PLAYLISTS_SPREADSHEET_ID, [f"{sheet_name}!A4:C"], credentials)
        error_strings.extend(batch_values_get_result.error_strings)
        if len(batch_values_get_result.batches) != 1:
            error_strings.append(f"Unexpected response from google drive API: {len(batch_values_get_result.batches)} batches. (Expected 1)")

        read_sheet_result = await read_sheet(PLAYLISTS_SPREADSHEET_ID, sheet_name, "K4:O", credentials)
        error_strings.extend(read_sheet_result.error_strings)

    class TrackSheetEntry(NamedTuple):
        track_name: str
        game_name_alt: str
        track_name_alt: str

    class ManualInsertEntry(NamedTuple):
        videos: list[PlaylistVideo]
        video_before: PlaylistVideo
        video_after: PlaylistVideo

    output_video_entries: list[OutputVideoEntry] = []
    requests: list[dict[str, typing.Any]] = []
    sheet_options = SheetOptions()

    track_sheet_entries: list[TrackSheetEntry] = []
    place_at_beginning_videos: list[PlaylistVideo] = []
    manual_insert_entries: list[ManualInsertEntry] = []
    if not len(error_strings):
        for row in batch_values_get_result.batches[0]:
            if len(row):
                track_and_mixname = row[0] 
                game_name_alt = "" 
                track_name_alt = ""
                if len(row) >= 2:
                    game_name_alt = row[1]
                if len(row) >= 3:
                    track_name_alt = row[2]
                track_sheet_entries.append(TrackSheetEntry(track_and_mixname, game_name_alt, track_name_alt))

        playlist_videos_to_sort: list[PlaylistVideo] = []
        playlist_videos_to_sort.extend(playlist_videos)

        group_by_mixname = False

        for i, row_read_cell in enumerate(read_sheet_result.rows):

            if  i == 0 and len(row_read_cell) and len(row_read_cell[0].text):
                group_by_mixname = True

            if len(row_read_cell) >= 3:
                urls = urls_from_read_cell(row_read_cell[2])
                for url in urls:
                    user_errors_row: list[str] = []
                    playlist_video = find_youtube_video(url, i, playlist_videos, user_errors_row)
                    user_errors.extend(user_errors_row)
                    if not len(user_errors_row):
                        place_at_beginning_videos.append(playlist_video)
                        if playlist_video in playlist_videos_to_sort:
                            playlist_videos_to_sort.remove(playlist_video)
                        
            if len(row_read_cell) >= 4:
                url_list = urls_from_read_cell(row_read_cell[3]) 
                url_place_before = "" 
                user_errors_row = []
                if len(row_read_cell) >= 5:
                    url_place_befores = urls_from_read_cell(row_read_cell[4])
                    if len(url_place_befores) > 1:
                        user_errors_row.append(f"Only one link allowed in Place Before cell (row {i + 4}).")
                    if len(url_place_befores) == 1:
                        url_place_before = url_place_befores[0]
                url_place_after = ""
                if len(row_read_cell) == 6:
                    url_place_afters = urls_from_read_cell(row_read_cell[5])
                    if len(url_place_afters) > 1:
                        user_errors_row.append(f"Only one link allowed in Place After cell (row {i + 4}).")
                    if len(url_place_afters) == 1:
                        url_place_before = url_place_afters[0]

                user_errors_row = []
                if not len(url_place_before) and not len(url_place_after):
                    user_errors_row.append(f"No before or after URL specified for row {i + 4}.")
                elif len(url_place_before) and not url_place_before.startswith("https://"):
                    user_errors_row.append(f"`{url_place_before}` is not a YouTube URL. (row {i + 4}).")
                elif len(url_place_after) and not url_place_after.startswith("https://"):
                    user_errors_row.append(f"`{url_place_after}` is not a YouTube URL. (row {i + 4}).")

                if len(url_place_before) and len(url_place_after):
                    user_errors_row.append(f"Can't have both BEFORE and AFTER URLs. (row {i + 4}).")

                for url in url_list:
                    if not url_place_before.startswith("https://"):
                        user_errors_row.append(f"`{url}` is not a YouTube URL. (row {i + 4}).")
                        break

                video_list = []
                video_before =  PlaylistVideo("", datetime.min, "", "", 0, False)
                video_after =  PlaylistVideo("", datetime.min, "", "", 0, False)
                if not len(user_errors_row):
                    for url in url_list:
                        video_list.append(find_youtube_video(url, i, playlist_videos, user_errors_row))
                    if len(url_place_before):
                        video_before = find_youtube_video(url_place_before, i, playlist_videos, user_errors_row)
                    if len(url_place_after):
                        video_after = find_youtube_video(url_place_after, i, playlist_videos, user_errors_row)

                user_errors.extend(user_errors_row)
                if not len(user_errors_row):
                    manual_insert_entries.append(ManualInsertEntry(video_list, video_before, video_after))
                    for video in video_list:
                        if video in playlist_videos_to_sort:
                            playlist_videos_to_sort.remove(video)

        sheet_options = SheetOptions(group_by_mixname)

        unmatched: list[PlaylistVideo] = []
        private : list[PlaylistVideo] = []

        class MatchedVideo(NamedTuple):
            track_name: str
            mixname: str
            game_name: str
            playlist_video: PlaylistVideo

        def video_matches(track_sheet_entry_name: str, playlist_video: PlaylistVideo, game_name_string_with_dash: str) -> MatchedVideo | None:
            result = None
            if (
                (playlist_video.title.startswith(track_sheet_entry_name))
                and (
                    playlist_video.title[:len(track_sheet_entry_name)] == track_sheet_entry_name
                    or (
                        len(playlist_video.title[:len(game_name_string_with_dash)]) > len(track_sheet_entry_name) 
                        and (playlist_video.title[len(track_sheet_entry_name):].startswith(" ("))
                    )
                ) 
            ):
                track_name_and_mixname = playlist_video.title[:-len(game_name_string_with_dash)]
                mixname = track_name_and_mixname[len(track_sheet_entry_name) + 1:]
                if not len(mixname) or (mixname.startswith('(') and mixname.endswith(')')):
                    result = MatchedVideo(track_sheet_entry_name, mixname, game_name_string_with_dash[3:], playlist_video)

            return result

        sort_dict: dict[TrackSheetEntry, list[MatchedVideo]] = {} 

        for playlist_video in playlist_videos_to_sort:
            if playlist_video.isPrivate:
                private.append(playlist_video)
            else:
                matched_video: MatchedVideo | None = None
                matched_track_sheet_entry = TrackSheetEntry("", "", "") 

                for track_sheet_entry in track_sheet_entries:
                    game_name = sheet_name
                    if len(track_sheet_entry.game_name_alt):
                        game_name = track_sheet_entry.game_name_alt
                    game_name_string_with_dash = f" - {game_name}"

                    if playlist_video.title.endswith(game_name_string_with_dash):
                        if (len(track_sheet_entry.track_name) > len(matched_track_sheet_entry.track_name)):
                            new_matched_video = video_matches(track_sheet_entry.track_name, playlist_video, game_name_string_with_dash)
                            if (new_matched_video):
                                matched_video = new_matched_video
                                matched_track_sheet_entry = track_sheet_entry

                        if ( 
                            len(track_sheet_entry.track_name_alt)
                            and (len(track_sheet_entry.track_name_alt) > len(matched_track_sheet_entry.track_name_alt)) 
                        ):
                            new_matched_video = video_matches(track_sheet_entry.track_name_alt, playlist_video, game_name_string_with_dash)
                            if (new_matched_video):
                                matched_video = new_matched_video
                                matched_track_sheet_entry = track_sheet_entry

                    elif track_sheet_entry.track_name == playlist_video.title: 
                        matched_track_sheet_entry = track_sheet_entry
                    elif len(track_sheet_entry.track_name_alt) and track_sheet_entry.track_name_alt == playlist_video.title: 
                        matched_track_sheet_entry = track_sheet_entry

                if len(matched_track_sheet_entry.track_name) and matched_video:
                    if matched_track_sheet_entry not in sort_dict:
                        sort_dict[matched_track_sheet_entry] = []
                    sort_dict[matched_track_sheet_entry].append(matched_video)
                else:
                    unmatched.append(playlist_video)

        def sort_mixnames(mixname: str) -> str:
            if len(mixname):
                if mixname[0] == "(":
                    mixname = mixname[1:]
                if mixname[-1] == ")":
                    mixname = mixname[:-1]
            return mixname.casefold()

        def playlist_video_to_split_guess(playlist_video: PlaylistVideo, sorted_type: SortedType) -> OutputVideoEntry:
            track_and_mixname = playlist_video.title 
            game_name = ""
            if playlist_video.title.endswith(f' - {sheet_name}'):
                game_name = sheet_name
            elif " - " in playlist_video.title:
                game_name = playlist_video.title[playlist_video.title.rindex(" - ") + 3:]
            if len(game_name):
                track_and_mixname = playlist_video.title[:-(len(game_name) + 3)]
            return OutputVideoEntry(sorted_type, track_and_mixname, game_name, playlist_video)

        unmatched_output_video_entries: list[OutputVideoEntry] = []
        for playlist_video in unmatched: 
            output_video_entry = playlist_video_to_split_guess(playlist_video, SortedType.UNMATCHED)
            unmatched_output_video_entries.append(output_video_entry)
        
        if sheet_options.group_by_mixname:

            class MixnameEntry(NamedTuple):
                track_sheet_entry: TrackSheetEntry | None
                output_video_entry: OutputVideoEntry

            mixname_dict: dict[str, list[MixnameEntry]] = {} 

            for track_sheet_entry in track_sheet_entries:
                if track_sheet_entry in sort_dict:
                    for matched_video in sort_dict[track_sheet_entry]:
                        output_video_entry = OutputVideoEntry(SortedType.MATCHED, f"{matched_video.track_name} {matched_video.mixname}", 
                                                            matched_video.game_name, matched_video.playlist_video)
                        mixname_entry = MixnameEntry(track_sheet_entry, output_video_entry)
                        if matched_video.mixname not in mixname_dict:
                            mixname_dict[matched_video.mixname] = []
                        mixname_dict[matched_video.mixname].append(mixname_entry)

            for output_video_entry in unmatched_output_video_entries:
                mixname_guess = ""
                index_mixname_guess_start = output_video_entry.track_and_mixname.find(" (")
                if index_mixname_guess_start > 0:
                    index_mixname_guess_end = output_video_entry.track_and_mixname.rfind(")",  index_mixname_guess_start)
                    if index_mixname_guess_end > 0:
                        mixname_guess = output_video_entry.track_and_mixname[index_mixname_guess_start + 1:index_mixname_guess_end + 1]
                if mixname_guess not in mixname_dict:
                    mixname_dict[mixname_guess] = []
                mixname_dict[mixname_guess].append(MixnameEntry(None, output_video_entry))

            mixnames_sorted = list(sorted(mixname_dict.keys(), key=sort_mixnames))
            for mixname in mixnames_sorted:
                for track_sheet_entry in track_sheet_entries:
                    for mixname_entry in mixname_dict[mixname]:
                        if mixname_entry.track_sheet_entry == track_sheet_entry:
                            output_video_entries.append(mixname_entry.output_video_entry)

                for mixname_entry in mixname_dict[mixname]:
                    if not mixname_entry.track_sheet_entry:
                        output_video_entries.append(mixname_entry.output_video_entry)
        else:
            for track_sheet_entry in track_sheet_entries:
                if track_sheet_entry in sort_dict:
                    sort_dict[track_sheet_entry].sort(key=lambda m: sort_mixnames(m.mixname))
                    for matched_video in sort_dict[track_sheet_entry]:
                        output_video_entry = OutputVideoEntry(SortedType.MATCHED, f"{matched_video.track_name} {matched_video.mixname}", 
                                                            matched_video.game_name, matched_video.playlist_video)
                        output_video_entries.append(output_video_entry)

            output_video_entries.extend(unmatched_output_video_entries)

        for playlist_video in private:
            output_video_entries.append(OutputVideoEntry(SortedType.PRIVATE, playlist_video.title, "", playlist_video))

        beginning_output_entries = []
        for playlist_video in place_at_beginning_videos:
            output_video_entry = playlist_video_to_split_guess(playlist_video, SortedType.MANUAL_BEGINNING) 
            beginning_output_entries.append(output_video_entry)
        temp = beginning_output_entries
        temp.extend(output_video_entries)
        output_video_entries = temp 

        for manual_insert_entry in manual_insert_entries:

            id_to_match = manual_insert_entry.video_before.video_id
            if len(manual_insert_entry.video_after.video_id):
                id_to_match = manual_insert_entry.video_after.video_id

            anchor_output_video = None 
            for i, output_video_entry in enumerate(output_video_entries):
                if output_video_entry.playlist_video.video_id == id_to_match:
                    anchor_output_video = output_video_entry
                    break

            user_errors_entry = []
            #TODO: (Ahmayk) there could be some nonsense here if we try to place videos that
            #aren't in the ordering yet, will need to loop through the list
            if not anchor_output_video: 
                user_errors_entry.append(f"YouTube URL not found in sorted output: `https://www.youtube.com/watch?v={id_to_match}`")

            if not len(user_errors_entry) and anchor_output_video:
                for playlist_video in manual_insert_entry.videos:
                    anchor_index = output_video_entries.index(anchor_output_video)
                    if manual_insert_entry.video_after.video_id:
                        anchor_index += 1
                    output_video_entry = playlist_video_to_split_guess(playlist_video, SortedType.MANUAL_INSERT) 
                    output_video_entries.insert(anchor_index, output_video_entry)

            user_errors.extend(user_errors_entry)

        cell_rows: list[list[Cell]] = [[]]

        default_cell = Cell(background_color=ColorRGBFloat(0.95686, 0.8, 0.8))

        count_header = [f'COUNT: {len(unmatched)}', "", "", f'COUNT: {len(output_video_entries)}', ""]
        cell_rows[0] = cell_bulk_create(count_header, Cell(is_bold=True, background_color=ColorRGBFloat(0.95686, 0.8, 0.8)))

        row_index = 1
        for output_video_entry in unmatched_output_video_entries:
            cell_rows.append([])
            strings = [output_video_entry.track_and_mixname, output_video_entry.game_name]
            cell_rows[row_index] = cell_bulk_create(strings, Cell(is_bold=True, background_color=ColorRGBFloat(1, 0.32, 0.32)))
            row_index += 1

        row_index = 1
        for i, output_video_entry in enumerate(output_video_entries):
            if row_index >= len(cell_rows):
                cell_rows.insert(row_index, [default_cell, default_cell])

            background_color = ColorRGBFloat(0.713, 0.843, 0.658)
            if output_video_entry.sorted_type == SortedType.UNMATCHED:
                background_color = ColorRGBFloat(1, 0.52, 0.52)
            elif output_video_entry.sorted_type == SortedType.PRIVATE:
                background_color = ColorRGBFloat(0.7, 0.7, 0.7)
            elif output_video_entry.sorted_type == SortedType.MANUAL_BEGINNING:
                background_color = ColorRGBFloat(1, 0.6, 0)
            elif output_video_entry.sorted_type == SortedType.MANUAL_INSERT:
                background_color = ColorRGBFloat(1, 0.949, 0.8)

            #NOTE: (Ahmayk) all zeros doesn't override default link color for some reason
            cell_format = Cell(background_color=background_color, foreground_color=(ColorRGBFloat(0, 0, 0.001)), wrap_strategy=WRAP_STRATEGY.CLIP)
            cell_format_position = cell_format
            if (
                (i == 0 and (output_video_entry.playlist_video.playlist_position != 0))
                or (i > 0 and output_video_entries[i - 1].playlist_video.playlist_position != output_video_entry.playlist_video.playlist_position - 1)
            ):
                cell_format_position = Cell(background_color=ColorRGBFloat(1, 0.850, 0.4))
            cell_rows[row_index].extend(cell_bulk_create([f'{(output_video_entry.playlist_video.playlist_position + 1):03}'], cell_format_position))

            video_url = f'https://www.youtube.com/watch?v={output_video_entry.playlist_video.video_id}'
            linked_trackname = format_hyperlink_formula(video_url, output_video_entry.track_and_mixname)
            cell_rows[row_index].extend(cell_bulk_create_formula([linked_trackname], cell_format))
            cell_rows[row_index].extend(cell_bulk_create([output_video_entry.game_name], cell_format))

            row_index += 1

        def push_options_on_off(option_bool: bool, row_index: int, cell_rows: list[list[Cell]]):
            if len(cell_rows) < row_index + 1:
                cell_rows.insert(row_index, [default_cell, default_cell, default_cell, default_cell, default_cell])
            if option_bool:
                cell_rows[row_index].append(Cell(text="ON", background_color=ColorRGBFloat(0, 1, 1), font_size=12, is_bold=True))
            else:
                cell_rows[row_index].append(Cell(text="OFF", background_color=ColorRGBFloat(0.717, 0.717, 0.717)))

        push_options_on_off(sheet_options.group_by_mixname, 0, cell_rows)

        requests.append(parse_update_cells_clear_request(spreadsheet_tab_id, 3, last_row_index, 3, 8))
        requests.extend(parse_update_cells_requests(spreadsheet_tab_id, cell_rows, 3, 3))

        text = format_sheet_timecode('Sheet last sorted')
        time_cells = [Cell(text=text, is_bold=True, background_color=ColorRGBFloat(0.9, 0.9, 0.9))]
        requests.extend(parse_update_cells_requests(spreadsheet_tab_id, [time_cells], 0, 3))

    return SortPlaylistVideosResult(output_video_entries, sheet_options, requests, error_strings, user_errors) 


@dataclass
class PlaylistButtonState:
    sheet_exists_on_start: bool
    spreadsheet_tab_id: int
    playlist_id: str 
    youtube_playlist: YouTubePlaylist
    playlist_videos: list[PlaylistVideo]
    last_sort_playlist_videos_result: SortPlaylistVideosResult


async def sort_button_callback(interaction: discord.Interaction, button_state: PlaylistButtonState, button: discord.ui.Button):

    if button.view:
        for child in button.view.children:
            child.disabled = True

    await interaction.response.edit_message(content="Sorting...", view=button.view)

    error_strings = []
    async with interaction.channel.typing():
        return_message = "Ooops! Error!"

        credentials_and_errors = await refresh_credentials()
        error_strings.extend(credentials_and_errors.error_strings)

        if not len(error_strings):
            last_row_index = 0
            sheet_info = await get_sheet_info(PLAYLISTS_SPREADSHEET_ID, button_state.youtube_playlist.title, credentials_and_errors.credentials)
            error_strings.extend(sheet_info.error_strings)
            if not len(sheet_info.error_strings):
                last_row_index = sheet_info.row_count - 1

        if not len(error_strings):
            sort_playlist_videos_result = await sort_playlist_videos(button_state.youtube_playlist.title, button_state.spreadsheet_tab_id,
                                                                     button_state.playlist_videos, last_row_index,
                                                                     credentials_and_errors.credentials)
            error_strings.extend(sort_playlist_videos_result.error_strings)
            button_state.last_sort_playlist_videos_result = sort_playlist_videos_result

        if not len(error_strings):
            batch_update_response = await send_sheet_batch_update(PLAYLISTS_SPREADSHEET_ID, sort_playlist_videos_result.requests,
                                                                  credentials_and_errors.credentials)
            error_strings.extend(batch_update_response.error_strings)

        if not len(error_strings):
            if button.view:
                for child in button.view.children:
                    child.disabled = False

            return_message = f"Sorted!"

        await interaction.message.edit(content=return_message, view=button.view)

    await send_if_errors("Errors occured during sorting", error_strings, interaction.channel)


async def script_button_callback(interaction: discord.Interaction, button_state: PlaylistButtonState, button: discord.ui.Button):
    error_strings = [] 

    credentials_and_errors = await refresh_credentials()
    error_strings.extend(credentials_and_errors.error_strings)

    if not len(error_strings):
        text = format_sheet_timecode('Tampermonkey Script Last Exported:')
        time_cells = [Cell(text=text, is_bold=True, background_color=ColorRGBFloat(0.9, 0.9, 0.9))]
        requests = parse_update_cells_requests(button_state.spreadsheet_tab_id, [time_cells], 0, 6)
        batch_update_response = await send_sheet_batch_update(PLAYLISTS_SPREADSHEET_ID, requests, credentials_and_errors.credentials)
        error_strings.extend(batch_update_response.error_strings)

    if not len(error_strings):
        resulting_order: list[PlaylistVideo] = []
        for ouput_video_entry in button_state.last_sort_playlist_videos_result.ouput_video_entries:
            resulting_order.append(ouput_video_entry.playlist_video) 

        video_ids_string = "let videoIds = ["
        for i, playlist_video in enumerate(resulting_order):
            video_ids_string += f'"{playlist_video.video_id}"'
            if i != len(resulting_order) - 1:
                video_ids_string += ", " 
        video_ids_string += "]"

        tampermonkey_script = ""
        with open("./playlistSorting/tampermonkeySorting.js", 'r') as file:
            tampermonkey_script = file.read()
        tampermonkey_script = tampermonkey_script.replace("#META_NAME", f'Playlist Sort - {button_state.youtube_playlist.title}') 
        tampermonkey_script = tampermonkey_script.replace("#META_YOUTUBE_LINK", f'https://*.youtube.com/playlist?list={button_state.playlist_id}') 
        tampermonkey_script = tampermonkey_script.replace("#META_VIDEO_IDS", video_ids_string) 

        filename = "tampermonkeyscript.js"
        with open(filename, "w") as f:
            f.truncate()
            f.write(tampermonkey_script)

        with open(filename, "rb") as f:
            await interaction.channel.send(file=discord.File(f, filename))
            await interaction.response.edit_message(content='Script sent!')

    await send_if_errors("Errors occured", error_strings, interaction.channel)


async def start_button_callback(interaction: discord.Interaction, button_state: PlaylistButtonState, button: discord.ui.Button):
    waiting_message = "Getting videos and creating sheet. This may take a moment..."
    if button_state.sheet_exists_on_start:
        waiting_message = "Getting videos and sorting sheet. This may take a moment.."
    await interaction.response.edit_message(content=waiting_message, view=None)

    message = None
    view = None
    async with interaction.channel.typing():
        return_message = "Oops! Error?"
        error_strings = [] 

        if button.custom_id == 'start_button_cache' and button_state.playlist_id in PLAYLIST_VIDEO_CACHE:
            button_state.playlist_videos = PLAYLIST_VIDEO_CACHE[button_state.playlist_id].playlist_videos
        else:
            playlist_videos_and_errors = await get_playlist_videos(button_state.playlist_id, YOUTUBE_API_KEY)
            button_state.playlist_videos = playlist_videos_and_errors.videos
            error_strings.extend(playlist_videos_and_errors.error_strings)
            if not len(playlist_videos_and_errors.error_strings):
                await set_playlist_video_cache(button_state.playlist_id, button_state.playlist_videos)

        reformat_sheet = False 

        credentials_and_errors = await refresh_credentials()
        error_strings.extend(credentials_and_errors.error_strings)
        
        requests = []
        if not len(error_strings) and not button_state.sheet_exists_on_start:
            create_sheet_request = parse_create_sheet_request(button_state.youtube_playlist.title)
            batch_update_response = await send_sheet_batch_update(PLAYLISTS_SPREADSHEET_ID, [create_sheet_request], credentials_and_errors.credentials)
            error_strings.extend(batch_update_response.error_strings)
            if not len(batch_update_response.error_strings) and batch_update_response.response:
                properties = batch_update_response.response['replies'][0]['addSheet']['properties']
                button_state.spreadsheet_tab_id = properties['sheetId']
                reformat_sheet = True

        if not len(error_strings) and reformat_sheet:
            cell_rows: list[list[Cell]] = [[], [], []]
            playlist_link = f'https://www.youtube.com/playlist?list={button_state.playlist_id}'
            linked_trackname = format_hyperlink_formula(playlist_link, button_state.youtube_playlist.title)
            cell_rows[0].append(Cell(formula_text=linked_trackname, font_size=32))

            texts = [
                "Track Name Order",
                "Alternate Game Name",
                "Alternate Track Name"
            ]
            cell_rows[1].extend(cell_bulk_create(texts, Cell(font_size=14, background_color=ColorRGBFloat(0.811, 0.886, 0.952), wrap_strategy=WRAP_STRATEGY.WRAP)))
            texts = [
                "Ouput:\nUnmatched Track Name",
                "Ouput:\nUnmatched Game Name",
                "#",
                "Output:\nResulting Order, Track Name",
                "Output:\nResulting Order, Game name",
                "Output:\nSettings used",
            ]
            cell_rows[1].extend(cell_bulk_create(texts, Cell(font_size=14, background_color=ColorRGBFloat(0.866, 0.494, 0.419), wrap_strategy=WRAP_STRATEGY.WRAP)))
            texts = [
                "Options",
                "On or Off",
                "Info",
            ]
            cell_rows[1].extend(cell_bulk_create(texts, Cell(font_size=14, background_color=ColorRGBFloat(0.705, 0.654, 0.839), wrap_strategy=WRAP_STRATEGY.WRAP)))
            texts = [
                "Place at Beginning",
            ]
            cell_rows[1].extend(cell_bulk_create(texts, Cell(font_size=14, background_color=ColorRGBFloat(1, 0.6, 0), wrap_strategy=WRAP_STRATEGY.WRAP)))
            texts = [
                "List of YouTube URLs",
                "Place BEFORE",
                "Place AFTER",
            ]
            cell_rows[1].extend(cell_bulk_create(texts, Cell(font_size=14, background_color=ColorRGBFloat(1, 0.898, 0.6), wrap_strategy=WRAP_STRATEGY.WRAP)))

            texts = [
                "List track names HERE without their mixnames to define the ordering of the OST. Capitalization matters! Color does not.",
                "If a track belongs to an alternate game release (Ex: Sonic Mania Plus, Mario Kart 8 Deluxe) list the game name here.",
                "If a track has an alternate spelling, list it here. A video with this track name will be sorted alongside the primary track name (the first column)."
            ]
            cell_rows[2].extend(cell_bulk_create(texts, Cell(background_color=ColorRGBFloat(0.952, 0.952, 0.952), wrap_strategy=WRAP_STRATEGY.WRAP)))
            texts = [
                "Video track names that were not matched to a track in the \"Track Name Order\" row. When this column is empty, all videos are properly sorted!\nAUTO POPULATED COLUMN",
                "AUTO POPULATED COLUMN",
                "Current order",
                "The resulting sorted order, track name. Ordered as: \n(1) (Green) Matched videos, sorted\n(2) (Red) Unmatched videos, unsorted\n(3) (Gray) Private videos.\nAUTO POPULATED COLUMN",
                "AUTO POPULATED COLUMN",
                "Settings used in last sort, corresponding to right column.\nAUTO POPULATED COLUMN",
            ]
            cell_rows[2].extend(cell_bulk_create(texts, Cell(background_color=ColorRGBFloat(0.917, 0.6, 0.6), wrap_strategy=WRAP_STRATEGY.WRAP)))
            texts = [
                "Options to control sorting behavior",
                "Any text = On. Empty = Off\n(Checkboxes aren't readable the google sheets API so this is a workaround lol)",
                "Info about the option",
            ]
            cell_rows[2].extend(cell_bulk_create(texts, Cell(background_color=ColorRGBFloat(0.850, 0.823, 0.913), wrap_strategy=WRAP_STRATEGY.WRAP)))
            texts = [
                "YouTube URLs in this column will be placed in this order at the beginning of the playlist. You can also enter text with a hyperlink (eg copy & paste from the red Output Track Name Column) or convert the link into a chip (the thing that comes up when you press tab after entering a URL)",
            ]
            cell_rows[2].extend(cell_bulk_create(texts, Cell(background_color=ColorRGBFloat(0.988, 0.898, 0.803), wrap_strategy=WRAP_STRATEGY.WRAP)))
            texts = [
                "One or more Youtube URLs. Will be placed either before or after a youtube URL to the right.",
                "A single YouTube URL. The list of YouTube URLS in the previous column will be placed BEFORE the first occurance of this URL.",
                "A single YouTube URL. Same as previous column, but placed AFTER. You can't have a before and an after in the same row.",
            ]
            cell_rows[2].extend(cell_bulk_create(texts, Cell(background_color=ColorRGBFloat(1, 0.949, 0.8), wrap_strategy=WRAP_STRATEGY.WRAP)))

            requests = parse_update_cells_requests(button_state.spreadsheet_tab_id, cell_rows, 0, 0)

            option_rows: list[list[Cell]] = [[]]
            format_cell_label = Cell(background_color=ColorRGBFloat(0.811, 0.886, 0.952), font_size=12, is_bold=True, wrap_strategy=WRAP_STRATEGY.WRAP)
            format_cell_desc = Cell(background_color=ColorRGBFloat(0.811, 0.886, 0.952), wrap_strategy=WRAP_STRATEGY.WRAP)
            option_rows[0].extend(cell_bulk_create(["Group by Mixname"], format_cell_label))
            option_rows[0].append(Cell())
            option_rows[0].extend(cell_bulk_create(["Tracks are grouped by mixname instead of grouping all track names, starting with mixless tracks."], format_cell_desc))
            requests.extend(parse_update_cells_requests(button_state.spreadsheet_tab_id, option_rows, 3, 9))

            requests.append(parse_update_dimension_properties_request(button_state.spreadsheet_tab_id, 300, SHEET_DIMENSION.COLUMNS, 0, 0))
            requests.append(parse_update_dimension_properties_request(button_state.spreadsheet_tab_id, 225, SHEET_DIMENSION.COLUMNS, 1, 2))
            requests.append(parse_update_dimension_properties_request(button_state.spreadsheet_tab_id, 325, SHEET_DIMENSION.COLUMNS, 3, 13))
            requests.append(parse_update_dimension_properties_request(button_state.spreadsheet_tab_id, 225, SHEET_DIMENSION.COLUMNS, 4, 4))
            requests.append(parse_update_dimension_properties_request(button_state.spreadsheet_tab_id, 55,  SHEET_DIMENSION.COLUMNS, 5, 5))
            requests.append(parse_update_dimension_properties_request(button_state.spreadsheet_tab_id, 225, SHEET_DIMENSION.COLUMNS, 7, 7))
            requests.append(parse_update_dimension_properties_request(button_state.spreadsheet_tab_id, 200, SHEET_DIMENSION.COLUMNS, 8, 10))
            requests.append(parse_update_dimension_properties_request(button_state.spreadsheet_tab_id, 325, SHEET_DIMENSION.COLUMNS, 12, 12))
            requests.append(parse_update_dimension_properties_request(button_state.spreadsheet_tab_id, 255, SHEET_DIMENSION.COLUMNS, 13, 15))

        last_row_index = 0
        sheet_info_new = await get_sheet_info(PLAYLISTS_SPREADSHEET_ID, button_state.youtube_playlist.title, credentials_and_errors.credentials)
        if not len(sheet_info_new.error_strings):
            last_row_index = sheet_info_new.row_count - 1
            error_strings.extend(sheet_info_new.error_strings)

        if not len(error_strings):
            sort_playlist_videos_result = await sort_playlist_videos(button_state.youtube_playlist.title, button_state.spreadsheet_tab_id, button_state.playlist_videos, last_row_index, credentials_and_errors.credentials)
            requests.extend(sort_playlist_videos_result.requests)
            error_strings.extend(sort_playlist_videos_result.error_strings)
            button_state.last_sort_playlist_videos_result = sort_playlist_videos_result

        if not len(error_strings):
            batch_update_response = await send_sheet_batch_update(PLAYLISTS_SPREADSHEET_ID, requests, credentials_and_errors.credentials)
            error_strings.extend(batch_update_response.error_strings)
            if not len(error_strings):
                sorting_sheet_url = f'https://docs.google.com/spreadsheets/d/{PLAYLISTS_SPREADSHEET_ID}?gid={button_state.spreadsheet_tab_id}'
                return_message = f"Here are buttons! {sorting_sheet_url}"

        if not len(error_strings):
            sort_button = JEButton(
                label = "Sort track names in spreadsheet",
                style = discord.ButtonStyle.primary,
                custom_id = 'sort_button',
                callback = sort_button_callback,
                button_state = button_state 
            )
            script_button = JEButton(
                label = "Generate Tampermonkey Script",
                style = discord.ButtonStyle.red,
                custom_id = 'script_button',
                callback = script_button_callback,
                button_state = button_state 
            )

            view = JEView(timeout_in_seconds=60*60)
            view.add_item(sort_button)
            view.add_item(script_button)
        message = await interaction.message.edit(content=return_message, view=view)

    await send_if_errors("Errors occured", error_strings, interaction.channel)

    if view and message:
        await view.wait_then_disable(message)


async def start_interactive_playlist_gen(input_youtube_playlist_link: str, channel: TextChannel | Thread):

    instructions = "Send a playlist link and I'll get or generate a playlist you can use to define the order of the playlist for sorting." 
    if not len(input_youtube_playlist_link):
        return await send(instructions, channel)

    playlist_id = extract_playlist_id(input_youtube_playlist_link)
    if not len(playlist_id):
        return await send(f"Invalid playlist link: `{input_youtube_playlist_link}`. {instructions}", channel)

    youtube_playlist = YouTubePlaylist() 
    sheet_info = SheetInfo(False, 0, "", 0, 0, [])
    async with channel.typing():
        youtube_playlist = await get_playlist_details(playlist_id, YOUTUBE_API_KEY)
        if len(youtube_playlist.error_strings):
            return await send_if_errors(f"Failed to get info from YouTube about `{input_youtube_playlist_link}`", youtube_playlist.error_strings, channel)

        credentials_and_errors = await refresh_credentials()
        if len(credentials_and_errors.error_strings) or not credentials_and_errors.credentials:
            return await send_if_errors(f"Failed to connect to google sheets API", credentials_and_errors.error_strings, channel)

        sheet_info = await get_sheet_info(PLAYLISTS_SPREADSHEET_ID, youtube_playlist.title, credentials_and_errors.credentials)
        if len(sheet_info.error_strings):
            return await send_if_errors(f"Failed to get sheet info for `{youtube_playlist.title}`", sheet_info.error_strings, channel)

    button_state = PlaylistButtonState(
        sheet_info.sheet_exists,
        sheet_info.spreadsheet_tab_id,
        playlist_id,
        youtube_playlist,
        [],
        SortPlaylistVideosResult([], SheetOptions(), [], [], [])
    )

    return_message = f"\nThe **{youtube_playlist.title}** playlist has **{youtube_playlist.video_count} videos**."
    buttons: list[JEButton] = []
    if sheet_info.sheet_exists:
        return_message += f"\nA spreadsheet exists for **{youtube_playlist.title}** {sheet_info.spreadsheet_url}.\nPress the button to sort the track names in the spreadsheet using videos currently on the channel!" 

        if playlist_id in PLAYLIST_VIDEO_CACHE:
            playlist_video_cache_entry = PLAYLIST_VIDEO_CACHE[playlist_id]
            expire_time = get_config("playlist_videos_cache_time")
            datetime_now = datetime.now(timezone.utc)
            if (datetime_now - playlist_video_cache_entry.time) < timedelta(seconds=expire_time):
                rd = relativedelta.relativedelta(datetime_now, playlist_video_cache_entry.time)
                cache_string = f'(from {rd.hours} hours ago)'
                if rd.hours <= 1:
                    cache_string = f'(from {rd.minutes} minutes ago)'
                buttons.append(JEButton(
                    label=f"Sort track names using playlist cache {cache_string}",
                    style=discord.ButtonStyle.primary,
                    custom_id='start_button_cache',
                    callback = start_button_callback,
                    button_state = button_state 
                ))

        buttons.append(JEButton(
            label="Get video titles from YouTube and sort track names",
            style=discord.ButtonStyle.primary,
            custom_id='start_button_nocache',
            callback = start_button_callback,
            button_state = button_state 
        ))

        ##TODO: (Ahmayk) reset sheet formatting button

    else:
        return_message += f"\nNo spreadsheet found for **{youtube_playlist.title}**.\nPress the button to create one using videos currently on the channel!" 
        buttons.append(JEButton(
            label="Get video titles from YouTube and create spreadsheet",
            style=discord.ButtonStyle.green,
            custom_id='start_button',
            callback = start_button_callback,
            button_state = button_state 
        ))


    view = JEView(timeout_in_seconds=60*15)
    for button in buttons:
        view.add_item(button)
    message = await channel.send(return_message, view=view)
    await view.wait_then_disable(message)