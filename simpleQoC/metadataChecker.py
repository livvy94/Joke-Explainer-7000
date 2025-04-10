import re
import requests
from typing import Tuple, List, Dict, Set
import json

import os
from pathlib import Path
from inspect import getsourcefile

PATTERNS_FILE = Path(os.path.abspath(getsourcefile(lambda:0))).parent / 'patterns.json'

class MetadataException(Exception):
    def __init__(self, message, *args):
        self.message = message # without this you may get DeprecationWarning
  
        # allow users initialize misc. arguments as any other builtin Error
        super(MetadataException, self).__init__(message, *args) 


def get_playlist_details(playlist_id, api_key):
    url = 'https://www.googleapis.com/youtube/v3/playlists'
    params = {
        'part': 'snippet',
        'id': playlist_id,
        'key': api_key
    }

    response = requests.get(url, params=params)
    response.raise_for_status()  # Raises an HTTPError for bad responses
    data = response.json()

    if 'error' in data:
        raise MetadataException(f"API Error: {data['error']['message']}")
    elif 'items' in data and len(data['items']) > 0:
        playlist_title = data['items'][0]['snippet']['title']
        playlist_creator = data['items'][0]['snippet']['channelTitle']
        return playlist_title, playlist_creator
    else:
        raise MetadataException("Playlist not found or empty.")
    

def get_playlist_videos(playlist_id, api_key) -> List[Dict[str, str]]:
    videos = []
    next_page_token = None

    while True:
        url = f'https://www.googleapis.com/youtube/v3/playlistItems'
        params = {
            'part': 'snippet',
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
            videos.append({k: item['snippet'][k] for k in ['title', 'description']})

        next_page_token = data.get('nextPageToken')
        if not next_page_token:
            break

    return videos


def remove_links(text):
    # Regular expression pattern to match URLs
    url_pattern = r'http[s]?://\S+|www\.\S+|https?://\S+'
    # Replace all matches with "[link]"
    return re.sub(url_pattern, '[link]', text)


def desc_to_dict(description: str, start_line: int) -> Tuple[Dict[str, str], Set[str]]:
    """
    Convert a description text to dictionary.
    The description should be in the format "A: B\netc."
    """
    desc = {}
    messages = set()
    for line in description.splitlines()[start_line:]:
        if len(line) == 0:
            # Let's just ignore empty lines. Most of the time they're going to be intentional, otherwise they're very easy to spot
            continue
        try:
            key, value = line.split(':', 1)
            if len(value) > 0:
                if value[0] == ' ': value = value[1:]
                else: messages.add(f'Missing space in `{key}` line.')
        except ValueError:
            # ignore last line if ppl decide to put channel desc
            if line != description.splitlines()[-1]:
                line_short = line if len(line) < 15 else f'{line[:7]}...{line[-7:]}'
                messages.add(f'Irregular line without : found in description: "{line_short}"')
            continue
        desc[key] = value
    
    return desc, messages


def crosscheck_description_key(key: str, video_descs: List[str], threshold: float):
    """
    Check if key is present in existing video descriptions, e.g. at least 50%.
    If not, it is likely there is a typo in the key, e.g. "Platlist"
    """
    # return sum([key in desc_to_dict(desc.replace('\r', '').split('\n\n')[0], 0)[0].keys() for desc in video_descs]) / len(video_descs) > threshold
    return sum([key in desc for desc in video_descs]) / len(video_descs) > threshold


def checkMetadata(description: str, channel_name: str, playlist_id: str, api_key: str, advanced: bool) -> Tuple[int, List[str]]:
    """
    Perform metadata checking.

    Types of metadata errors detected:
    - Linked playlist is not from `channel_name`
    - Title (first line of description) already exists in playlist
    - Any patterns in `patterns.json` under "MISTAKE"
    - [Advanced] Any field in `description`, e.g. "Music:", that does not appear in more than 50% of videos in playlist
    - [Advanced] Title does not match any regex patterns in `patterns.json` under "TITLE", given the track name in description
    - [Advanced] Game name does not match playlist name, or any videos in playlist
    """
    messages = set()
    desc_lines = description.splitlines()
    title = desc_lines[0]

    # Parse description for more in-depth metadata checking
    desc, adv_messages = desc_to_dict(description, 1)

    # If the Playlist field exists but it is empty and playlist_id is not empty,
    # likely a rare case of the Joke line containing a playlist not intended as for the rip.
    if 'Playlist' in desc.keys() and len(desc['Playlist']) == 0 and len(playlist_id) > 0:
        playlist_id = ""

    # Check metadata based on provided playlist ID
    if len(playlist_id) > 0:
        try:
            try:
                playlist_name, channel = get_playlist_details(playlist_id, api_key)
                videos = get_playlist_videos(playlist_id, api_key)
        
            except requests.exceptions.Timeout:
                raise MetadataException('Request timed out.')
            except requests.exceptions.TooManyRedirects:
                raise MetadataException('Bad URL.')
            except requests.exceptions.HTTPError as http_err:
                raise MetadataException(f"HTTP error occurred: {http_err}")
            except requests.exceptions.RequestException as e: # Other errors
                raise MetadataException('Unknown URL error. {}'.format(e))
            
        except MetadataException as e:
            messages.add(remove_links(e.message))
            return -1, messages

        if channel_name != channel:
            # Playlist source check
            messages.add("Playlist is not from {} (found playlist from {})".format(channel_name, channel))
        else:
            # Duplicate title check
            if title in [video['title'] for video in videos]:
                messages.add("Video title already exists in playlist.")
    else:
        playlist_name = None
        videos = []

    # Check metadata by patterns
    with open(PATTERNS_FILE, 'r', encoding='utf-8') as file:
        patterns = json.load(file)

        # Common mistake patterns
        for p in patterns["MISTAKE"]:
            if p["pattern"] in description:
                if "message" in p.keys(): messages.add(p["message"])
                if "adv_message" in p.keys(): adv_messages.add(p["adv_message"])

        if len(desc) == 0 or list(desc.keys())[0].lower() != 'music':
            # If the first description line is not "Music:", assume the metadata is intentionally unusual
            # just return nothing?
            return 0, []
        else:
            # Compare desc with existing videos
            for key in desc.keys():
                # ignore ones already covered by patterns.json
                if (key + ":") in [p["pattern"] for p in patterns["MISTAKE"]]:
                    continue
                threshold = 0.5
                if not crosscheck_description_key(key, [video['description'] for video in videos], threshold):
                    adv_messages.add(f'`{key}` field not present in at least {int(100*threshold)}% of existing videos in playlist.')
            # Compare desc['Music'] and title
            try:
                track = desc['Music']
            except KeyError:
                track = desc[list(desc.keys())[0]]

            game = None
            for p in patterns["TITLE"]:
                match = re.match(p.replace('[[TRACK]]', re.escape(track)), title)
                if match:
                    existing_titles = [video['title'] for video in videos]

                    # Check that at least 50% of existing videos have the same title formatting
                    if len(existing_titles) > 0 and sum([re.match(p.replace('[[TRACK]]', r'(?P<track>[^\n]*)'), t) is not None for t in existing_titles]) / len(existing_titles) < 0.5:
                        continue
                    
                    # Check game name
                    game = match.group('game')
                    if (game != playlist_name) and not any([video.endswith(" - " + game) for video in existing_titles]):
                        adv_messages.add('Game in title does not match playlist name nor any existing videos.')
            
            if game is None:
                adv_messages.add('Title format does not match {}; check for typos or missing mixnames.'.format('existing videos' if len(videos) > 0 else 'any known pattern'))
    
    if advanced: messages = messages.union(adv_messages)
    return len(messages) > 0, messages


# Example usage
if __name__ == "__main__":
    PLAYLIST_ID = input("Paste the playlist ID: ")
    API_KEY = input("Paste the API key: ")

    name, user = get_playlist_details(PLAYLIST_ID, API_KEY)
    videos = get_playlist_videos(PLAYLIST_ID, API_KEY)

    print('Playlist name: {}, by: {}'.format(name, user))
    print('Number of videos: {}'.format(len(videos)))
