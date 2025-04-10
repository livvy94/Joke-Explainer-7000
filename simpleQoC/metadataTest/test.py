import unittest
from unittest.mock import patch
import json
import sys
import os
from pathlib import Path
from inspect import getsourcefile

from simpleQoC.metadataChecker import checkMetadata

TEST_DIR = Path(os.path.abspath(getsourcefile(lambda:0))).parent
DEBUG_MODE = False

class TestMetadata(unittest.TestCase):
    """
    Test suits for checkMetadata function
    """
    CHANNEL_NAME = "SiIvaGunner"

    def __init__(self, *args, **kwargs):
        super(TestMetadata, self).__init__(*args, **kwargs)

        with open(TEST_DIR / 'smb2jp.json', 'r', encoding='utf-8') as file:
            self.SMB2JP = json.load(file)
        with open(TEST_DIR / 'smbas.json', 'r', encoding='utf-8') as file:
            self.SMBAS = json.load(file)
        with open(TEST_DIR / 'ssbu.json', 'r', encoding='utf-8') as file:
            self.SSBU = json.load(file)


    @patch('simpleQoC.metadataChecker.get_playlist_videos')
    @patch('simpleQoC.metadataChecker.get_playlist_details')
    def test_metadata_ok(self, mock_details, mock_videos):
        mock_details.return_value = "Super Mario Bros. 2 (JP)", self.CHANNEL_NAME
        mock_videos.return_value = self.SMB2JP

        description = "Castle (Beta Mix) - Super Mario Bros. 2 (JP)\n\nMusic: Castle (Beta Mix)\nComposer: Koji Kondo\nPlaylist: https://www.youtube.com/playlist?list=PLL0CQjrcN8D1eRlsClwtcJM1V1xtZbU1S\nPlatform: Famicom Disk System\n\nPlease read the c"

        code, msgs = checkMetadata(description, self.CHANNEL_NAME, "PLL0CQjrcN8D1eRlsClwtcJM1V1xtZbU1S", None, True)
        for msg in msgs:
            if DEBUG_MODE: print(msg)
        
        self.assertEqual(code, 0)
        self.assertEqual(len(msgs), 0)


    @patch('simpleQoC.metadataChecker.get_playlist_videos')
    @patch('simpleQoC.metadataChecker.get_playlist_details')
    def test_metadata_issue(self, mock_details, mock_videos):
        mock_details.return_value = "Super \u2588\u2588\u2588\u2588\u2588 3D All Stars", self.CHANNEL_NAME
        mock_videos.return_value = self.SMBAS

        description = "S\u258864 Super \u2588\u2588\u2588\u2588\u2588 64 Main Theme - Super \u2588\u2588\u2588\u2588\u2588 4D All Stars\nMusic:  S\u258864 Super \u2588\u2588\u2588\u2588\u2588 64 Main Theme (JP Version)\nComposed by: Koji Kondo\n\nArrangement: my cuh\nPlatlist: https://www.youtube.com/playlist?list=PLL0CQjrcN8D0RpfnKPuj8anigmMCnbJpF\ndummy line’s — lol\nPlatforms:Playstation 2, Xbox Series X/S"

        code, msgs = checkMetadata(description, self.CHANNEL_NAME, "PLL0CQjrcN8D0RpfnKPuj8anigmMCnbJpF", None, True)
        for msg in msgs:
            if DEBUG_MODE: print(msg)
        
        self.assertEqual(code, 1)
        self.assertEqual(len(msgs), 12)
        self.assertTrue("Double space detected in description." in msgs)
        self.assertTrue("There is no **s** in Platform." in msgs)
        self.assertTrue("Typographic apostrophe (``’``) detected. It is recommended that you use typewriter apostrophe(``'``) for consistency." in msgs)
        self.assertTrue("Em dash (``—``) detected. It is recommended that you use en dash (``-``) for consistency." in msgs)
        self.assertTrue("The **S** in PlayStation should be capitalized." in msgs)
        self.assertTrue("We commonly use Xbox Series X|S." in msgs)
        self.assertTrue("Reboot metadata found. Change to regular metadata if this was not intentional." in msgs)
        self.assertTrue("Missing space in ``Platforms`` line." in msgs)
        self.assertTrue("Irregular line without : found in description: \"dummy l...s — lol\"" in msgs)
        self.assertTrue("``Arrangement`` field not present in any existing videos in playlist." in msgs)
        self.assertTrue("``Platlist`` field not present in any existing videos in playlist." in msgs)
        self.assertTrue("Title format does not match existing videos, or Music line is incorrect." in msgs)


    @patch('simpleQoC.metadataChecker.get_playlist_videos')
    @patch('simpleQoC.metadataChecker.get_playlist_details')
    def test_metadata_issue_v2(self, mock_details, mock_videos):
        mock_details.return_value = "Super \u2588\u2588\u2588\u2588\u2588 3D All Stars", self.CHANNEL_NAME
        mock_videos.return_value = self.SMBAS

        description = "Super \u2588\u2588\u2588\u2588\u2588 4D All Stars Music S\u258864 Super \u2588\u2588\u2588\u2588\u2588 64 Main Theme (JP Version)\n\nMusic: S\u258864 Super \u2588\u2588\u2588\u2588\u2588 64 Main Theme (JP Version)\nComposer: Koji Kondo\nPlaylist: https://www.youtube.com/playlist?list=PLL0CQjrcN8D0RpfnKPuj8anigmMCnbJpF\nPlatform: Nintendo Switch\r\n\r\nPlease read the channel description."

        code, msgs = checkMetadata(description, self.CHANNEL_NAME, "PLL0CQjrcN8D0RpfnKPuj8anigmMCnbJpF", None, True)
        for msg in msgs:
            if DEBUG_MODE: print(msg)
        
        self.assertEqual(code, 1)
        self.assertEqual(len(msgs), 1)
        self.assertTrue("Game in title does not match playlist name nor any existing videos." in msgs)


    @patch('simpleQoC.metadataChecker.get_playlist_videos')
    @patch('simpleQoC.metadataChecker.get_playlist_details')
    def test_metadata_issue_v3(self, mock_details, mock_videos):
        mock_details.return_value = "Super \u2588\u2588\u2588\u2588\u2588 3D All Stars", self.CHANNEL_NAME
        mock_videos.return_value = self.SMBAS

        description = "S\u258864 Super \u2588\u2588\u2588\u2588\u2588 64 Main Theme - Super \u2588\u2588\u2588\u2588\u2588 4D All Stars\nMusic:  S\u258864 Super \u2588\u2588\u2588\u2588\u2588 64 Main Theme (JP Version)\nComposed by: Koji Kondo\n\nArrangement: my cuh\nPlatlist: https://www.youtube.com/playlist?list=PLL0CQjrcN8D0RpfnKPuj8anigmMCnbJpF\ndummy line’s — lol\nPlatforms:Playstation 2, Xbox Series X/S"

        code, msgs = checkMetadata(description, self.CHANNEL_NAME, "PLL0CQjrcN8D0RpfnKPuj8anigmMCnbJpF", None, False)
        for msg in msgs:
            if DEBUG_MODE: print(msg)
        
        self.assertEqual(code, 1)
        self.assertEqual(len(msgs), 7)
        self.assertTrue("Double space detected in description." in msgs)
        self.assertTrue("There is no **s** in Platform." in msgs)
        self.assertTrue("Typographic apostrophe (``’``) detected. It is recommended that you use typewriter apostrophe(``'``) for consistency." in msgs)
        self.assertTrue("Em dash (``—``) detected. It is recommended that you use en dash (``-``) for consistency." in msgs)
        self.assertTrue("The **S** in PlayStation should be capitalized." in msgs)
        self.assertTrue("We commonly use Xbox Series X|S." in msgs)
        self.assertTrue("Reboot metadata found. Change to regular metadata if this was not intentional." in msgs)
    

    @patch('simpleQoC.metadataChecker.get_playlist_videos')
    @patch('simpleQoC.metadataChecker.get_playlist_details')
    def test_metadata_announcement(self, mock_details, mock_videos):
        mock_details.return_value = "Announcement", "not siivagunner"
        mock_videos.return_value = self.SSBU

        description = "A Decrypted Announcement [Installer Insanity Out Now!]\n\nInstaller Insanity features arranges from the classic works of keygen music. SGFR has scavenged through plenty of tunes from the depths and has given them a new twist - in celebration of demoscene music! Remember... SGFR does not condone piracy. We only condone music.\n\nGet it now for free: http://sgfr.highquality.rip/sgfr-0009/\nAlbum playlist: https://www.youtube.com/playlist?list=PLL0CQjrcN8D1-lL5iRUT2CNttzP8KxeP9"

        code, msgs = checkMetadata(description, self.CHANNEL_NAME, "PLL0CQjrcN8D1-lL5iRUT2CNttzP8KxeP9", None, True)
        for msg in msgs:
            if DEBUG_MODE: print(msg)
        
        self.assertEqual(code, 0)


if __name__ == '__main__': 
    if len(sys.argv) > 1:
        print('DEBUG MODE ENABLED')
        DEBUG_MODE = True

    unittest.main()
