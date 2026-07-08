
import requests
from datetime import datetime
from dateutil import parser
from typing import NamedTuple, Any
from hq_discord import run_blocking 

#NOTE: (Ahmayk) JSON is untyped boooo
class JSONAndErrors(NamedTuple):
    json: Any
    error_strings: list[str]

async def youtube_api_call(url, params) -> JSONAndErrors:
    json = {} 
    error_strings: list[str] = []
    try:
        response = await run_blocking(requests.get, url, params=params)
        response.raise_for_status()
        json = response.json()
    except requests.exceptions.Timeout:
        error_strings.append('Request timed out.')
    except requests.exceptions.TooManyRedirects:
        error_strings.append('Bad URL.')
    except requests.exceptions.HTTPError as http_err:
        error_strings.append(f"HTTP error occurred: {http_err}")
    except requests.exceptions.RequestException as e: # Other errors
        error_strings.append(f'Unknown URL error. {e}')
    except Exception as error:
        error_strings.append(f"ERROR on YouTube API Call: {error}")

    if 'error' in json:
        error_strings.append(f"YouTube API Error: {json['error']['message']}")

    return JSONAndErrors(json, error_strings)


class YouTubePlaylist(NamedTuple):
    title: str
    channel_name: str
    error_strings: list[str]

async def get_playlist_details(playlist_id, api_key) -> YouTubePlaylist:

    title = ""
    channel_name = ""
    error_strings: list[str] = []

    url = 'https://www.googleapis.com/youtube/v3/playlists'
    params = {
        'part': 'snippet',
        'id': playlist_id,
        'key': api_key
    }
    json_and_errors = await youtube_api_call(url, params)
    data = json_and_errors.json
    error_strings.extend(json_and_errors.error_strings)

    if not len(error_strings):
        if 'items' in data and len(data['items']) > 0:
            title = data['items'][0]['snippet']['title']
            channel_name = data['items'][0]['snippet']['channelTitle']
        else:
            error_strings.append(f"Playlist not found.")

    return YouTubePlaylist(title, channel_name, error_strings)
    

class PlaylistVideo(NamedTuple):
    video_id: str 
    date: datetime
    title: str 
    desc: str
    playlist_position: int
    isPrivate: bool

class PlaylistVideosAndErrors(NamedTuple):
    videos: list[PlaylistVideo]
    error_strings: list[str]

async def get_playlist_videos(playlist_id, api_key) -> PlaylistVideosAndErrors: 
    videos = []
    next_page_token = None
    error_strings = []

    while True:
        url = f'https://www.googleapis.com/youtube/v3/playlistItems'
        params = {
            'part': 'snippet,status',
            'playlistId': playlist_id,
            'key': api_key,
            'pageToken': next_page_token
        }

        json_and_errors = await youtube_api_call(url, params)
        data = json_and_errors.json
        error_strings.extend(json_and_errors.error_strings)

        if not len(json_and_errors.error_strings):
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

    return PlaylistVideosAndErrors(videos, error_strings) 