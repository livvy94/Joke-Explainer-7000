
from hq_discord import *
from hq_youtube import *
from hq_sheets import *
from dateutil import tz

from bot_secrets import YOUTUBE_API_KEY, PLAYLISTS_SPREADSHEET_ID
from enum import auto

import shelve 
FOO_DATABASE = shelve.open("foo", writeback=True)
DELTARUNE_KEY = "DELTARUNE"


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

class SortPlaylistVideosResult(NamedTuple):
    ouput_video_entries: list[OutputVideoEntry]
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

        read_sheet_result = await read_sheet(PLAYLISTS_SPREADSHEET_ID, sheet_name, "M4:O", credentials)
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

        for i, row_read_cell in enumerate(read_sheet_result.rows):
            if len(row_read_cell):
                urls = urls_from_read_cell(row_read_cell[0])
                for url in urls:
                    user_errors_row = []
                    if not url.startswith("https://"):
                        user_errors_row.append(f"`{url}` is not a YouTube URL. (row {i + 4}).")
                    playlist_video = find_youtube_video(url, i, playlist_videos, user_errors_row)
                    user_errors.extend(user_errors_row)
                    if not len(user_errors_row):
                        place_at_beginning_videos.append(playlist_video)
                        if playlist_video in playlist_videos_to_sort:
                            playlist_videos_to_sort.remove(playlist_video)
                        
            if len(row_read_cell) > 1:
                url_list = urls_from_read_cell(row_read_cell[1]) 
                url_place_before = "" 
                if len(row_read_cell) >= 3:
                    url_place_befores = urls_from_read_cell(row_read_cell[2])
                    if len(url_place_befores) > 1:
                        user_errors_row.append(f"Only one link allowed in Place Before cell (row {i + 4}).")
                    if len(url_place_befores) == 1:
                        url_place_before = url_place_befores[0]
                url_place_after = ""
                if len(row_read_cell) == 4:
                    url_place_afters = urls_from_read_cell(row_read_cell[3])
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

        unmatched: list[PlaylistVideo] = []
        private : list[PlaylistVideo] = []

        def video_matches(track_sheet_entry_name: str, video_title: str, game_name_string_with_dash: str):
            if (
                (video_title.startswith(track_sheet_entry_name))
            ):
                if (
                    video_title[:len(track_sheet_entry_name)] == track_sheet_entry_name
                    or (
                        len(video_title[:len(game_name_string_with_dash)]) > len(track_sheet_entry_name) 
                        and (video_title[len(track_sheet_entry_name):].startswith(" ("))
                    )
                ):
                    return True
            return False

        class MatchedVideo(NamedTuple):
            track_name: str
            mixname: str
            game_name: str
            playlist_video: PlaylistVideo

        sort_dict: dict[TrackSheetEntry, list[MatchedVideo]] = {} 

        for playlist_video in playlist_videos_to_sort:
            if playlist_video.isPrivate:
                private.append(playlist_video)
            else:
                matched_track_sheet_entry = TrackSheetEntry("", "", "") 
                matched_game_name = ""
                is_matched_alt = False

                for track_sheet_entry in track_sheet_entries:
                    game_name = sheet_name
                    if len(track_sheet_entry.game_name_alt):
                        game_name = track_sheet_entry.game_name_alt
                    game_name_string_with_dash = f" - {game_name}"
                    if playlist_video.title.endswith(game_name_string_with_dash):
                        if (
                            (len(track_sheet_entry.track_name) > len(matched_track_sheet_entry.track_name))
                            and video_matches(track_sheet_entry.track_name, playlist_video.title, game_name_string_with_dash)
                        ):
                            matched_track_sheet_entry = track_sheet_entry
                            matched_game_name = game_name
                            is_matched_alt = False

                        if ( 
                            len(track_sheet_entry.track_name_alt)
                            and (len(track_sheet_entry.track_name_alt) > len(matched_track_sheet_entry.track_name_alt)) 
                            and video_matches(track_sheet_entry.track_name_alt, playlist_video.title, game_name_string_with_dash)
                        ):
                            matched_track_sheet_entry = track_sheet_entry
                            matched_game_name = game_name
                            is_matched_alt = True

                    elif track_sheet_entry.track_name == playlist_video.title: 
                        matched_track_sheet_entry = track_sheet_entry
                        matched_game_name = ""
                        is_matched_alt = False
                    elif len(track_sheet_entry.track_name_alt) and track_sheet_entry.track_name_alt == playlist_video.title: 
                        matched_track_sheet_entry = track_sheet_entry
                        matched_game_name = ""
                        is_matched_alt = True 

                if len(matched_track_sheet_entry.track_name):
                    track_name = matched_track_sheet_entry.track_name
                    track_and_mixname = matched_track_sheet_entry.track_name
                    if is_matched_alt:
                        track_and_mixname = matched_track_sheet_entry.track_name_alt

                    game_name = sheet_name 
                    if len(matched_track_sheet_entry.game_name_alt):
                        game_name = matched_track_sheet_entry.game_name_alt

                    game_name_string_with_dash = f" - {game_name}"
                    track_name_and_mixname = playlist_video.title[:-len(game_name_string_with_dash)]
                    mixname = track_name_and_mixname[len(track_and_mixname) + 1:]
                    
                    if matched_track_sheet_entry not in sort_dict:
                        sort_dict[matched_track_sheet_entry] = []
                    sort_dict[matched_track_sheet_entry].append(MatchedVideo(track_name, mixname, matched_game_name, playlist_video))
                else:
                    unmatched.append(playlist_video)

        def sort_mixnames(mixname: str) -> str:
            if len(mixname):
                if mixname[0] == "(":
                    mixname = mixname[1:]
                if mixname[-1] == ")":
                    mixname = mixname[:-1]
            return mixname.casefold()
        
        for track_sheet_entry in track_sheet_entries:
            if track_sheet_entry in sort_dict:
                sort_dict[track_sheet_entry].sort(key=lambda m: sort_mixnames(m.mixname))
                for matched_video in sort_dict[track_sheet_entry]:
                    output_video_entry = OutputVideoEntry(SortedType.MATCHED, f"{matched_video.track_name} {matched_video.mixname}", 
                                                          matched_video.game_name, matched_video.playlist_video)
                    output_video_entries.append(output_video_entry)

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

        requests.append(parse_update_cells_clear_request(spreadsheet_tab_id, 3, last_row_index, 3, 8))
        requests.extend(parse_update_cells_requests(spreadsheet_tab_id, cell_rows, 3, 3))

        text = format_sheet_timecode('Sheet last sorted')
        time_cells = [Cell(text=text, is_bold=True, background_color=ColorRGBFloat(0.9, 0.9, 0.9))]
        requests.extend(parse_update_cells_requests(spreadsheet_tab_id, [time_cells], 0, 3))

    return SortPlaylistVideosResult(output_video_entries, requests, error_strings, user_errors) 



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
        if len(sheet_info.error_strings) or not credentials_and_errors.credentials:
            return await send_if_errors(f"Failed to connect to google sheets API", credentials_and_errors.error_strings, channel)

        sheet_info = await get_sheet_info(PLAYLISTS_SPREADSHEET_ID, youtube_playlist.title, credentials_and_errors.credentials)
        if len(sheet_info.error_strings):
            return await send_if_errors(f"Failed to get sheet info for `{youtube_playlist.title}`", sheet_info.error_strings, channel)

    return_message = "" 
    start_button_label = ""
    return_message += f"\nThe **{youtube_playlist.title}** playlist has **{youtube_playlist.video_count} videos**."
    if sheet_info.sheet_exists:
        return_message += f"\nA spreadsheet exists for **{youtube_playlist.title}** {sheet_info.spreadsheet_url}.\nPress the button to sort the track names in the spreadsheet using videos currently on the channel!" 
        start_button_label = "Get videos and sort track names"
        start_buttn_style = discord.ButtonStyle.primary
    else:
        return_message += f"\nNo spreadsheet found for **{youtube_playlist.title}**.\nPress the button to create one using videos currently on the channel!" 
        start_button_label = "Get videos and create spreadsheet"
        start_buttn_style = discord.ButtonStyle.green

    ##NOTE: (Ahmayk) There's probably a better way to use buttons without dealing with
    # this inheritance bullshit, but the library only intends for you to use them this way I think,
    # and it would have taken more time to understand this library's nonsense than to implement 
    # a better solution so inheritance bullshit it is
    class SortView(discord.ui.View):
        def __init__(self, sorting_sheet_id: int, sorting_sheet_url: str, 
                     playlist_videos: list[PlaylistVideo], sort_playlist_videos_result: SortPlaylistVideosResult):
            super().__init__()
            self.sorting_sheet_id: int = sorting_sheet_id
            self.sorting_sheet_url: str = sorting_sheet_url
            self.playlist_videos: list[PlaylistVideo] = playlist_videos 
            self.last_sort_playlist_videos_result: SortPlaylistVideosResult = sort_playlist_videos_result
            self.timeout = 60*60

        @discord.ui.button(label='Sort track names in spreadsheet', style=discord.ButtonStyle.primary)
        async def sortButton(self, interaction: discord.Interaction, button: discord.ui.Button):
            try:
                await interaction.response.edit_message(content="Sorting...", view=None)

                async with channel.typing():
                    return_message = "Ooops! Error!"
                    error_strings = []

                    last_row_index = 0
                    sheet_info = await get_sheet_info(PLAYLISTS_SPREADSHEET_ID, youtube_playlist.title, credentials_and_errors.credentials)
                    if not len(sheet_info.error_strings):
                        last_row_index = sheet_info.row_count - 1
                        error_strings.extend(sheet_info.error_strings)

                    if not len(sheet_info.error_strings):
                        sort_playlist_videos_result = await sort_playlist_videos(youtube_playlist.title, self.sorting_sheet_id, self.playlist_videos, last_row_index, credentials_and_errors.credentials)
                        self.last_sort_playlist_videos_result = sort_playlist_videos_result
                        error_strings.extend(sort_playlist_videos_result.error_strings)

                        batch_update_response = await send_sheet_batch_update(PLAYLISTS_SPREADSHEET_ID, sort_playlist_videos_result.requests, credentials_and_errors.credentials)
                        error_strings.extend(batch_update_response.error_strings)

                    if not len(error_strings):
                        return_message = f"Sorted! {self.sorting_sheet_url}"

                    await interaction.message.edit(content=return_message, view=self)

                    await send_if_errors("Errors occured during sorting", error_strings, interaction.channel)
            except Exception as error:
                await send_crash(f'ERROR on playlistsort button:', error, interaction.channel)

        @discord.ui.button(label='Generate Tampermonkey Script', style=discord.ButtonStyle.red)
        async def scriptButton(self, interaction: discord.Interaction, button: discord.ui.Button):
            try:
                error_strings = [] 

                text = format_sheet_timecode('Tampermonkey Script Last Exported:')
                time_cells = [Cell(text=text, is_bold=True, background_color=ColorRGBFloat(0.9, 0.9, 0.9))]
                requests = parse_update_cells_requests(self.sorting_sheet_id, [time_cells], 0, 6)
                batch_update_response = await send_sheet_batch_update(PLAYLISTS_SPREADSHEET_ID, requests, credentials_and_errors.credentials)
                error_strings.extend(batch_update_response.error_strings)

                resulting_order: list[PlaylistVideo] = []
                for ouput_video_entry in self.last_sort_playlist_videos_result.ouput_video_entries:
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
                tampermonkey_script = tampermonkey_script.replace("#META_NAME", f'Playlist Sort - {youtube_playlist.title}') 
                tampermonkey_script = tampermonkey_script.replace("#META_YOUTUBE_LINK", f'https://*.youtube.com/playlist?list={playlist_id}') 
                tampermonkey_script = tampermonkey_script.replace("#META_VIDEO_IDS", video_ids_string) 

                filename = "tampermonkeyscript.js"
                with open(filename, "w") as f:
                    f.truncate()
                    f.write(tampermonkey_script)

                with open(filename, "rb") as f:
                    await interaction.channel.send(file=discord.File(f, filename))
                    await interaction.response.edit_message(content='Script sent!', view=self)

                await send_if_errors("Errors occured", error_strings, interaction.channel)

            except Exception as error:
                await send_crash(f'ERROR on playlistsort button:', error, interaction.channel)



    class StartButton(discord.ui.View):
        @discord.ui.button(label=start_button_label, style=start_buttn_style)
        async def button(self, interaction: discord.Interaction, button: discord.ui.Button):
            try:
                waiting_message = "Getting videos and creating sheet. This may take a moment..."
                if sheet_info.sheet_exists:
                    waiting_message = "Getting videos and sorting sheet. This may take a moment.."
                await interaction.response.edit_message(content=waiting_message, view=None)

                async with channel.typing():
                    return_message = "Oops! Error?"
                    error_strings = [] 

                    ##TODO: (Ahmayk) cache purposefully and repull if outdated (prevent spamming same playlist wasting credits)
                    if playlist_id in FOO_DATABASE:
                        playlist_videos = FOO_DATABASE[playlist_id]
                    else:
                        playlist_videos_and_errors = await get_playlist_videos(playlist_id, YOUTUBE_API_KEY)
                        playlist_videos = playlist_videos_and_errors.videos
                        error_strings.extend(playlist_videos_and_errors.error_strings)
                        FOO_DATABASE[playlist_id] = playlist_videos 
                        FOO_DATABASE.sync()

                    reformat_sheet = False
                    
                    requests = []
                    sorting_sheet_id = 0 
                    sorting_sheet_url = "" 
                    if not len(error_strings):
                        if sheet_info.sheet_exists:
                            sorting_sheet_id = sheet_info.spreadsheet_tab_id 
                            sorting_sheet_url = f'https://docs.google.com/spreadsheets/d/{PLAYLISTS_SPREADSHEET_ID}?gid={sheet_info.spreadsheet_tab_id}'
                        else:
                            create_sheet_request = parse_create_sheet_request(youtube_playlist.title)
                            batch_update_response = await send_sheet_batch_update(PLAYLISTS_SPREADSHEET_ID, [create_sheet_request], credentials_and_errors.credentials)
                            error_strings.extend(batch_update_response.error_strings)
                            if not len(batch_update_response.error_strings) and batch_update_response.response:
                                properties = batch_update_response.response['replies'][0]['addSheet']['properties']
                                sorting_sheet_id = properties['sheetId']
                                sorting_sheet_url = f'https://docs.google.com/spreadsheets/d/{PLAYLISTS_SPREADSHEET_ID}?gid={sorting_sheet_id}'
                                reformat_sheet = True

                    if not len(error_strings) and reformat_sheet:
                        cell_rows: list[list[Cell]] = [[], [], []]
                        playlist_link = f'https://www.youtube.com/playlist?list={playlist_id}'
                        linked_trackname = format_hyperlink_formula(playlist_link, youtube_playlist.title)
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
                            "",
                            "",
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
                            "",
                            "",
                        ]
                        cell_rows[2].extend(cell_bulk_create(texts, Cell(background_color=ColorRGBFloat(0.850, 0.823, 0.913), wrap_strategy=WRAP_STRATEGY.WRAP)))
                        texts = [
                            "YouTube URLs in this column will be placed in this order at the beginning of the playlist.",
                        ]
                        cell_rows[2].extend(cell_bulk_create(texts, Cell(background_color=ColorRGBFloat(0.988, 0.898, 0.803), wrap_strategy=WRAP_STRATEGY.WRAP)))
                        texts = [
                            "One or more Youtube URLs, seperated by newlines (press CTL-Enter to enter newline), will be placed either before or after a youtube URL to the right.",
                            "A single YouTube URL. The list of YouTube URLS in the previous column will be placed BEFORE the first occurance of this URL.",
                            "A single YouTube URL. Same as previous column, but placed AFTER.",
                        ]
                        cell_rows[2].extend(cell_bulk_create(texts, Cell(background_color=ColorRGBFloat(1, 0.949, 0.8), wrap_strategy=WRAP_STRATEGY.WRAP)))

                        requests = parse_update_cells_requests(sorting_sheet_id, cell_rows, 0, 0)

                        requests.append(parse_update_dimension_properties_request(sorting_sheet_id, 300, SHEET_DIMENSION.COLUMNS, 0, 0))
                        requests.append(parse_update_dimension_properties_request(sorting_sheet_id, 225, SHEET_DIMENSION.COLUMNS, 1, 2))
                        requests.append(parse_update_dimension_properties_request(sorting_sheet_id, 325, SHEET_DIMENSION.COLUMNS, 3, 13))
                        requests.append(parse_update_dimension_properties_request(sorting_sheet_id, 225, SHEET_DIMENSION.COLUMNS, 4, 4))
                        requests.append(parse_update_dimension_properties_request(sorting_sheet_id, 55,  SHEET_DIMENSION.COLUMNS, 5, 5))
                        requests.append(parse_update_dimension_properties_request(sorting_sheet_id, 225, SHEET_DIMENSION.COLUMNS, 7, 7))
                        requests.append(parse_update_dimension_properties_request(sorting_sheet_id, 200, SHEET_DIMENSION.COLUMNS, 8, 8))
                        requests.append(parse_update_dimension_properties_request(sorting_sheet_id, 100, SHEET_DIMENSION.COLUMNS, 9, 10))
                        requests.append(parse_update_dimension_properties_request(sorting_sheet_id, 255, SHEET_DIMENSION.COLUMNS, 12, 15))

                    last_row_index = 0
                    sheet_info_new = await get_sheet_info(PLAYLISTS_SPREADSHEET_ID, youtube_playlist.title, credentials_and_errors.credentials)
                    if not len(sheet_info_new.error_strings):
                        last_row_index = sheet_info_new.row_count - 1
                        error_strings.extend(sheet_info_new.error_strings)

                    sort_playlist_videos_result = SortPlaylistVideosResult([], [], [], []) 
                    if not len(error_strings):
                        sort_playlist_videos_result = await sort_playlist_videos(youtube_playlist.title, sorting_sheet_id, playlist_videos, last_row_index, credentials_and_errors.credentials)
                        requests.extend(sort_playlist_videos_result.requests)
                        error_strings.extend(sort_playlist_videos_result.error_strings)

                    if not len(error_strings):
                        batch_update_response = await send_sheet_batch_update(PLAYLISTS_SPREADSHEET_ID, requests, credentials_and_errors.credentials)
                        error_strings.extend(batch_update_response.error_strings)
                        if not len(error_strings):
                            return_message = f"Here are buttons! {sorting_sheet_url}"

                    view = None
                    if not len(error_strings):
                        view = SortView(sorting_sheet_id, sorting_sheet_url, playlist_videos, sort_playlist_videos_result)
                    await interaction.message.edit(content=return_message, view=view)

                await send_if_errors("Errors occured", error_strings, interaction.channel)

                if view:
                    await view.wait()
            except Exception as error:
                await send_crash(f'ERROR on playlistsort button:', error, interaction.channel)


    view = StartButton()
    await channel.send(return_message, view=view)
    await view.wait()