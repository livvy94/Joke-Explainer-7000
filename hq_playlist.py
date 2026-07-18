
from hq_youtube import *
from hq_sheets import *
from dateutil import tz

from bot_secrets import YOUTUBE_API_KEY, PLAYLISTS_SPREADSHEET_ID

import shelve 
FOO_DATABASE = shelve.open("foo", writeback=True)
DELTARUNE_KEY = "DELTARUNE"

class MatchedVideo(NamedTuple):
    track_name: str
    mixname: str
    game_name: str
    playlist_video: PlaylistVideo

class SortPlaylistVideosResult(NamedTuple):
    matched_sorted: list[MatchedVideo]
    unmatched: list[PlaylistVideo]
    private: list[PlaylistVideo]
    requests: list[dict[str, typing.Any]]
    error_strings: list[str]

async def sort_playlist_videos(sheet_name: str, spreadsheet_tab_id, playlist_videos: list[PlaylistVideo], 
                               last_row_index: int, credentials: Credentials) -> SortPlaylistVideosResult:

    error_strings: list[str] = []

    class TrackSheetEntry(NamedTuple):
        track_name: str
        game_name_alt: str
        track_name_alt: str
        youtube_link: str

    track_sheet_entries: list[TrackSheetEntry] = [] 
    sheet_data = RawSheetData([[]], []) 
    if credentials and credentials.valid:
        sheet_data = await get_raw_sheet_data(PLAYLISTS_SPREADSHEET_ID, sheet_name, 4, 'C', credentials)
        error_strings.extend(sheet_data.error_strings)

    if not len(error_strings):
        for row in sheet_data.rows:
            if len(row):
                track_and_mixname = "" 
                game_name_alt = "" 
                track_name_alt = ""
                youtube_link = ""
                first_column = row[0]
                if first_column.startswith("https://"):
                    youtube_link = first_column
                else:
                    track_and_mixname = first_column
                if len(row) >= 2:
                    game_name_alt = row[1]
                if len(row) >= 3:
                    track_name_alt = row[2]
                track_sheet_entries.append(TrackSheetEntry(track_and_mixname, game_name_alt, track_name_alt, youtube_link))
    
    matched_sorted: list[MatchedVideo] = []
    unmatched: list[PlaylistVideo] = []
    private : list[PlaylistVideo] = []
    requests: list[dict[str, typing.Any]] = []

    if not len(error_strings):

        sort_dict: dict[TrackSheetEntry, list[MatchedVideo]] = {} 

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

        for playlist_video in playlist_videos:
            if playlist_video.isPrivate:
                private.append(playlist_video)
            else:
                matched_track_sheet_entry = TrackSheetEntry("", "", "", "") 
                matched_game_name = ""
                is_matched_alt = False
                is_matched_link = False

                for track_sheet_entry in track_sheet_entries:
                    if len(track_sheet_entry.youtube_link) and playlist_video.video_id in track_sheet_entry.youtube_link:
                        matched_track_sheet_entry = track_sheet_entry
                        is_matched_link = True 
                        break
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

                if is_matched_link or len(matched_track_sheet_entry.track_name):
                    track_name = ""
                    game_name = ""
                    mixname = "" 
                    if is_matched_link:
                        track_name = playlist_video.title
                    else:
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
                    matched_sorted.append(matched_video)


        cell_rows: list[list[Cell]] = [[]]

        default_cell = Cell(background_color=ColorRGBFloat(0.95686, 0.8, 0.8))

        total_length = 0
        total_length += len(matched_sorted)
        total_length += len(unmatched)
        total_length += len(private)

        date = datetime.now(tz=tz.UTC)
        date = date.astimezone(tz.gettz('America/Los_Angeles'))
        timestring = date.strftime("%H:%M:%S (PST) - %d/%m/%Y") 

        count_header = [f'COUNT: {len(unmatched)}', "", "", f'COUNT: {total_length}', f'Sheet last sorted: {timestring}']
        cell_rows[0] = cell_bulk_create(count_header, Cell(is_bold=True, background_color=ColorRGBFloat(0.95686, 0.8, 0.8)))

        class SplitTitle(NamedTuple):
            track_and_mixname: str
            game_name: str

        def split_video_title_guess(title: str, sheet_name: str):
            track_and_mixname = title
            game_name = ""
            if title.endswith(f' - {sheet_name}'):
                game_name = sheet_name
            elif " - " in title:
                game_name = title[title.rindex(" - ") + 3:]
            if len(game_name):
                track_and_mixname = title[:-(len(game_name) + 3)]
            return SplitTitle(track_and_mixname, game_name)

        row_index = 1
        for playlist_video in unmatched:
            split_title = split_video_title_guess(playlist_video.title, sheet_name)
            cell_rows.append([])
            strings = [split_title.track_and_mixname, split_title.game_name]
            cell_rows[row_index] = cell_bulk_create(strings, Cell(is_bold=True, background_color=ColorRGBFloat(1, 0.32, 0.32)))
            row_index += 1

        row_index = 1

        for i, matched_video in enumerate(matched_sorted):
            if row_index >= len(cell_rows):
                cell_rows.insert(row_index, [default_cell, default_cell])

            #NOTE: (Ahmayk) all zeros doesn't override default link color for some reason
            cell_format = Cell(background_color=ColorRGBFloat(0.713, 0.843, 0.658), foreground_color=(ColorRGBFloat(0, 0, 0.001)))
            cell_format_position = cell_format
            if (
                (i == 0 and (matched_video.playlist_video.playlist_position != 0))
                or (i > 0 and matched_sorted[i - 1].playlist_video.playlist_position != matched_video.playlist_video.playlist_position - 1)
            ):
                cell_format_position = Cell(background_color=ColorRGBFloat(1, 0.850, 0.4))
            cell_rows[row_index].extend(cell_bulk_create([f'{(matched_video.playlist_video.playlist_position + 1):03}'], cell_format_position))

            video_url = f'https://www.youtube.com/watch?v={matched_video.playlist_video.video_id}'
            linked_trackname = format_hyperlink_formula(video_url, f"{matched_video.track_name} {matched_video.mixname}")
            cell_rows[row_index].extend(cell_bulk_create_formula([linked_trackname], cell_format))
            cell_rows[row_index].extend(cell_bulk_create([matched_video.game_name], cell_format))

            row_index += 1

        unmatched_index_start = row_index - 1
        unmatched_and_private = []
        unmatched_and_private.extend(unmatched)
        private_index_start = len(unmatched) + unmatched_index_start
        unmatched_and_private.extend(private)
        for i, playlist_video in enumerate(unmatched):
            if row_index >= len(cell_rows):
                cell_rows.insert(row_index, [default_cell, default_cell])

            cell_format = Cell(background_color=ColorRGBFloat(1, 0.52, 0.52), foreground_color=(ColorRGBFloat(0, 0, 0.001)))
            if i + unmatched_index_start >= private_index_start: 
                cell_format = Cell(background_color=ColorRGBFloat(0.7, 0.7, 0.7), foreground_color=(ColorRGBFloat(0, 0, 0.001)))

            cell_format_position = cell_format
            if (
                (i == 0 and (playlist_video.playlist_position != unmatched_index_start))
                or (i > 0 and unmatched[i - 1].playlist_position != playlist_video.playlist_position - 1)
            ):
                cell_format_position = Cell(background_color=ColorRGBFloat(1, 0.850, 0.4))
            cell_rows[row_index].extend(cell_bulk_create([f'{(playlist_video.playlist_position + 1):03}'], cell_format_position))

            split_title = split_video_title_guess(playlist_video.title, sheet_name)
            video_url = f'https://www.youtube.com/watch?v={playlist_video.video_id}'
            linked_trackname = format_hyperlink_formula(video_url, split_title.track_and_mixname)
            cell_rows[row_index].extend(cell_bulk_create_formula([linked_trackname], cell_format))
            cell_rows[row_index].extend(cell_bulk_create([split_title.game_name], cell_format))

            row_index += 1

        requests.append(parse_update_cells_clear_request(spreadsheet_tab_id, 3, last_row_index, 3, 8))
        requests.extend(parse_update_cells_requests(spreadsheet_tab_id, cell_rows, 3, 3))

    return SortPlaylistVideosResult(matched_sorted, unmatched, private, requests, error_strings) 



async def start_interactive_playlist_gen(input_youtube_playlist_link: str, channel: TextChannel | Thread):

    instructions = "Send a playlist link an I'll get or generate a playlist you can use to define the order of the playlist for sorting." 
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

        credentials = await refresh_credentials()
        sheet_info = await get_sheet_info(PLAYLISTS_SPREADSHEET_ID, youtube_playlist.title, credentials)
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
                return_message = "Ooops! Error!"
                error_strings = []

                last_row_index = 0
                sheet_info = await get_sheet_info(PLAYLISTS_SPREADSHEET_ID, youtube_playlist.title, credentials)
                if not len(sheet_info.error_strings):
                    last_row_index = sheet_info.row_count - 1
                    error_strings.extend(sheet_info.error_strings)

                if not len(sheet_info.error_strings):
                    sort_playlist_videos_result = await sort_playlist_videos(youtube_playlist.title, self.sorting_sheet_id, self.playlist_videos, last_row_index, credentials)
                    self.last_sort_playlist_videos_result = sort_playlist_videos_result
                    error_strings.extend(sort_playlist_videos_result.error_strings)

                    batch_update_response = await send_sheet_batch_update(PLAYLISTS_SPREADSHEET_ID, sort_playlist_videos_result.requests, credentials)
                    error_strings.extend(batch_update_response.error_strings)

                if not len(error_strings):
                    return_message = f"Sorted! {self.sorting_sheet_url}"

                await interaction.response.edit_message(content=return_message, view=self)

                await send_if_errors("Errors occured during sorting", error_strings, interaction.channel)
            except Exception as error:
                await send_crash(f'ERROR on playlistsort button:', error, interaction.channel)

        @discord.ui.button(label='Generate Tampermonkey Script', style=discord.ButtonStyle.red)
        async def scriptButton(self, interaction: discord.Interaction, button: discord.ui.Button):
            try:
                resulting_order: list[PlaylistVideo] = []
                for matched_video in self.last_sort_playlist_videos_result.matched_sorted:
                    resulting_order.append(matched_video.playlist_video) 
                resulting_order.extend(self.last_sort_playlist_videos_result.unmatched) 
                resulting_order.extend(self.last_sort_playlist_videos_result.private) 

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

                    requests = []
                    sorting_sheet_id = 0 
                    sorting_sheet_url = "" 
                    if not len(error_strings):
                        if sheet_info.sheet_exists:
                            sorting_sheet_id = sheet_info.spreadsheet_tab_id 
                            sorting_sheet_url = f'https://docs.google.com/spreadsheets/d/{PLAYLISTS_SPREADSHEET_ID}?gid={sheet_info.spreadsheet_tab_id}'
                        else:
                            create_sheet_request = parse_create_sheet_request(youtube_playlist.title)
                            batch_update_response = await send_sheet_batch_update(PLAYLISTS_SPREADSHEET_ID, [create_sheet_request], credentials)
                            error_strings.extend(batch_update_response.error_strings)
                            if not len(error_strings) and batch_update_response.response:
                                properties = batch_update_response.response['replies'][0]['addSheet']['properties']
                                sorting_sheet_id = properties['sheetId']
                                sorting_sheet_url = f'https://docs.google.com/spreadsheets/d/{PLAYLISTS_SPREADSHEET_ID}?gid={sorting_sheet_id}'

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
                                    "Ouput: Unmatched Track Name",
                                    "Ouput: Unmatched Game Name",
                                    "# Now",
                                    "Output: Resulting Order, Track Name",
                                    "Output: Resulting Order, Game name",
                                ]
                                cell_rows[1].extend(cell_bulk_create(texts, Cell(font_size=14, background_color=ColorRGBFloat(0.866, 0.494, 0.419), wrap_strategy=WRAP_STRATEGY.WRAP)))
                                texts = [
                                    "List track names HERE without their mixnames to define the ordering of the OST. Capitalization matters! Color does not. Accepts track names OR a YouTube link.",
                                    "If a track belongs to an alterate game release (Ex: Sonic Mania Plus, Mario Kart 8 Deluxe) list the game name here.",
                                    "If a track has an alternate spelling, list it here. A video with this track name will be sorted alongside the primary track name (the first column)."
                                ]
                                cell_rows[2].extend(cell_bulk_create(texts, Cell(background_color=ColorRGBFloat(0.952, 0.952, 0.952), wrap_strategy=WRAP_STRATEGY.WRAP)))
                                texts = [
                                    "AUTO POPULATED COLUMN.\nVideo track names that were not matched to a track in the \"Track Name Order\" row. When this column is empty, all videos are properly sorted!",
                                    "AUTO POPULATED COLUMN.\nVideo game names with the previous column.",
                                    "Current order",
                                    "AUTO POPULATED COLUMN.\nThe resulting sorted order, track name. Ordered as: \n(1) (Green) Matched videos, sorted\n(2) (Red) Unmatched videos, unsorted\n(3) (Gray) Private videos",
                                    "AUTO POPULATED COLUMN.\nThe resulting sorted order. Game name is shown here is track is matched. If unmatched, full video title is kept in previous column.",
                                ]
                                cell_rows[2].extend(cell_bulk_create(texts, Cell(background_color=ColorRGBFloat(0.917, 0.6, 0.6), wrap_strategy=WRAP_STRATEGY.WRAP)))

                                requests = parse_update_cells_requests(sorting_sheet_id, cell_rows, 0, 0)

                                requests.append(parse_update_dimension_properties_request(sorting_sheet_id, 300, SHEET_DIMENSION.COLUMNS, 0, 0))
                                requests.append(parse_update_dimension_properties_request(sorting_sheet_id, 225, SHEET_DIMENSION.COLUMNS, 1, 2))
                                requests.append(parse_update_dimension_properties_request(sorting_sheet_id, 325, SHEET_DIMENSION.COLUMNS, 3, 7))
                                requests.append(parse_update_dimension_properties_request(sorting_sheet_id, 225, SHEET_DIMENSION.COLUMNS, 4, 4))
                                requests.append(parse_update_dimension_properties_request(sorting_sheet_id, 55,  SHEET_DIMENSION.COLUMNS, 5, 5))

                    last_row_index = 0
                    sheet_info_new = await get_sheet_info(PLAYLISTS_SPREADSHEET_ID, youtube_playlist.title, credentials)
                    if not len(sheet_info_new.error_strings):
                        last_row_index = sheet_info_new.row_count - 1
                        error_strings.extend(sheet_info_new.error_strings)

                    sort_playlist_videos_result = SortPlaylistVideosResult([], [], [], [], []) 
                    if not len(error_strings):
                        sort_playlist_videos_result = await sort_playlist_videos(youtube_playlist.title, sorting_sheet_id, playlist_videos, last_row_index, credentials)
                        requests.extend(sort_playlist_videos_result.requests)
                        error_strings.extend(sort_playlist_videos_result.error_strings)

                        batch_update_response = await send_sheet_batch_update(PLAYLISTS_SPREADSHEET_ID, requests, credentials)
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