from simpleQoC.metadata import *
from hq_sheets import *
from bot_secrets import YOUTUBE_API_KEY, PLAYLISTS_SPREADSHEET_ID
from dateutil import parser, tz

import shelve 
FOO_DATABASE = shelve.open("foo", writeback=True)
DELTARUNE_KEY = "DELTARUNE"

class PlaylistVideo(NamedTuple):
    video_id: str 
    date: datetime
    title: str 
    desc: str
    playlist_position: int
    isPrivate: bool

def get_playlist_videos_foo(playlist_id, api_key) -> list[PlaylistVideo]: 
    videos = []
    next_page_token = None

    while True:
        url = f'https://www.googleapis.com/youtube/v3/playlistItems'
        params = {
            'part': 'snippet,status',
            'playlistId': playlist_id,
            'key': api_key,
            'pageToken': next_page_token
        }

        response = requests.get(url, params=params)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        data = response.json()

        if 'error' in data:
            raise MetadataException(f"API Error: {data['error']['message']}")

        for item in data.get('items', []):
            playlist_video = PlaylistVideo(
                item["snippet"]["resourceId"]["videoId"],
                parser.parse(item["snippet"]["publishedAt"]),
                item["snippet"]["title"],
                item["snippet"]["description"],
                item["snippet"]["position"],
                item["status"]["privacyStatus"] == 'private'
            )
            videos.append(playlist_video)

        next_page_token = data.get('nextPageToken')
        if not next_page_token:
            break

    return videos

def rip_title_matches_rip_title(video_track_name: str, official_track_name: str) -> bool:
    result = False
    if (
        official_track_name == video_track_name
        or (
            len(video_track_name) > len(official_track_name) 
            and video_track_name.startswith(official_track_name) 
            and (video_track_name[len(official_track_name):].startswith(" (")
        ))
    ): 
        result = True
    return result 

async def playlist_test() -> bool:

    playlist_videos: list[PlaylistVideo] = [] 
    if DELTARUNE_KEY in FOO_DATABASE:
        playlist_videos = FOO_DATABASE[DELTARUNE_KEY]
    else:
        DELTARUNE_PLAYLIST = "PLL0CQjrcN8D0VeG0AJrHzrq5sRNNWjkDP"
        playlist_videos = get_playlist_videos_foo(DELTARUNE_PLAYLIST, YOUTUBE_API_KEY)
        FOO_DATABASE[DELTARUNE_KEY] = playlist_videos
        FOO_DATABASE.sync()


    class OfficialName(NamedTuple):
        name: str
        alt: str

    official_names: list[OfficialName] = [] 
    credentials = await refresh_credentials()
    await clear_cells(PLAYLISTS_SPREADSHEET_ID, "deltarune", "C3:G", credentials)

    if credentials and credentials.valid:
        sheet_data = await get_raw_sheet_data(PLAYLISTS_SPREADSHEET_ID, "deltarune", 1, 'b', credentials)
        for row in sheet_data:
            if len(row):
                name = row[0]
                alt = ""
                if len(row) >= 2:
                    alt = row[1]
                official_names.append(OfficialName(name, alt))
                
    
    class TrackAndMixname(NamedTuple):
        track: str
        mixname: str
        playlist_video: PlaylistVideo

    sort_dict: dict[OfficialName, list[TrackAndMixname]] = {} 
    unmatched: list[PlaylistVideo] = []
    private : list[PlaylistVideo] = []

    for playlist_video in playlist_videos:
        if playlist_video.isPrivate:
            private.append(playlist_video)
        else:
            video_track_name = playlist_video.title.replace(" - DELTARUNE", "")
            matched_official_name = OfficialName("", "") 
            is_matched_alt = False

            for official_name in official_names:
                if (
                    (len(official_name.name) > len(matched_official_name.name)) 
                    and rip_title_matches_rip_title(video_track_name, official_name.name)
                ): 
                    matched_official_name = official_name

                if ( 
                    len(official_name.alt)
                    and (len(official_name.alt) > len(matched_official_name.alt)) 
                    and rip_title_matches_rip_title(video_track_name, official_name.alt)
                ):
                    matched_official_name = official_name
                    is_matched_alt = True

            if len(matched_official_name.name):
                if matched_official_name not in sort_dict:
                    sort_dict[matched_official_name] = []
                track = matched_official_name.name
                if is_matched_alt:
                    track = matched_official_name.alt
                mixname = playlist_video.title[len(track) + 1:]
                sort_dict[matched_official_name].append(TrackAndMixname(track, mixname, playlist_video))
            else:
                unmatched.append(playlist_video)
    
    sorted_titles: list[PlaylistVideo] = []
    for official_name in official_names:
        if official_name in sort_dict:
            sort_dict[official_name].sort(key=lambda t: t.mixname.lower())
            if len(sort_dict[official_name]) > 1:
                mixless = sort_dict[official_name].pop()
                sort_dict[official_name].insert(0, mixless)
            for track_and_title in sort_dict[official_name]:
                sorted_titles.append(track_and_title.playlist_video)


    print(f"Sorted {len(playlist_videos)} tracks"\
          + f"\n- {len(sorted_titles)} sorted tracks"\
          + f"\n- {len(unmatched)} unmatched tracks"\
          + f"\n- {len(private)} private videos")

    sheet_cells: list[list[str]] = [[], [], [], []]

    sheet_cells[0].append(f'COUNT: {len(unmatched)}') 
    sheet_cells[0].append("") 
    for playlist_video in unmatched:
        video_track_name = playlist_video.title.replace(" - DELTARUNE", "")
        sheet_cells[0].append(f'{video_track_name}') 

    date = datetime.now(tz=tz.UTC)
    date = date.astimezone(tz.gettz('America/Los_Angeles'))
    timestring = date.strftime("%H:%M:%S (PST) - %d/%m/%Y") 

    resulting_order: list[PlaylistVideo] = []
    resulting_order.extend(sorted_titles) 
    resulting_order.extend(unmatched) 
    resulting_order.extend(private) 
    sheet_cells[1].append("") 
    sheet_cells[1].append("") 
    sheet_cells[2].append(f'COUNT: {len(resulting_order)}') 
    sheet_cells[2].append("") 
    for playlist_video in resulting_order:
        video_track_name = playlist_video.title.replace(" - DELTARUNE", "")
        sheet_cells[1].append(f'{(playlist_video.playlist_position + 1):03}') 
        sheet_cells[2].append(f'{video_track_name}') 

    sheet_cells[3].append(timestring) 

    await write_data_to_sheet(PLAYLISTS_SPREADSHEET_ID, "deltarune", sheet_cells, "C3", credentials)

    video_ids_string = "let videoIds = ["
    for i, playlist_video in enumerate(resulting_order):
        video_ids_string += f'"{playlist_video.video_id}"'
        if i != len(resulting_order) - 1:
            video_ids_string += ", " 
    video_ids_string += "]"

    tampermonkey_script = ""
    with open("./playlistSorting/tampermonkeySorting.js", 'r') as file:
        tampermonkey_script = file.read()
    tampermonkey_script += f"\n\n{video_ids_string}\n//Good Luck!"
    with open("tampermonkeyfoo.js", "w") as f:
        f.truncate()
        f.write(tampermonkey_script)

    return True
