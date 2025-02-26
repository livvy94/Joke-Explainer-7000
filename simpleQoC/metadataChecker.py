import requests
from typing import Tuple, List

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
    

def get_playlist_videos(playlist_id, api_key) -> List[str]:
    video_titles = []
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
            video_titles.append(item['snippet']['title'])

        next_page_token = data.get('nextPageToken')
        if not next_page_token:
            break

    return video_titles


def verifyTitle(title: str, channel_name: str, playlist_id: str, api_key: str) -> Tuple[int, str]:
    """
    Verify a title and game name against a given playlist.

    - If the playlist's creator does not match the channel_name, returns a warning
    - If title already exists in playlist, returns a warning.
    - Otherwise, no problem.
    """
    try:
        try:
            playlist_name, channel = get_playlist_details(playlist_id, api_key)
            existing_titles = get_playlist_videos(playlist_id, api_key)

            if channel_name != channel:
                return 1, "Playlist is not from {}".format(channel_name)
    
        except requests.exceptions.Timeout:
            raise MetadataException('Request timed out.')
        except requests.exceptions.TooManyRedirects:
            raise MetadataException('Bad URL.')
        except requests.exceptions.HTTPError as http_err:
            raise MetadataException(f"HTTP error occurred: {http_err}")
        except requests.exceptions.RequestException as e: # Other errors
            raise MetadataException('Unknown URL error. {}'.format(e.strerror))
        
    except MetadataException as e:
        return -1, e.message

    duplicateCheck = title not in existing_titles
    # gameCheck = (game == playlist_name) or any([video.endswith(" - " + game) for video in existing_titles])

    if not duplicateCheck:
        return 1, "Video title already exists in playlist."
    # if not gameCheck:
    #     return 1, "Game name may be incorrect according to playlist."
    
    return 0, "Metadata is OK."


# Example usage
if __name__ == "__main__":
    PLAYLIST_ID = input("Paste the playlist ID: ")
    API_KEY = input("Paste the API key: ")

    name, user = get_playlist_details(PLAYLIST_ID, API_KEY)
    titles = get_playlist_videos(PLAYLIST_ID, API_KEY)
    # for title in titles:
    #     print(title)
    print('Playlist name: {}, by: {}'.format(name, user))
    print('Number of videos: {}'.format(len(titles)))