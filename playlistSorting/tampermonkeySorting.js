// ==UserScript==
// @name         #META_NAME
// @namespace    http://tampermonkey.net/
// @version      1960-09-30
// @description  sort shit 
// @author       Joke-Explainer™ 7000
// @match        #META_YOUTUBE_LINK
// @icon         https://www.google.com/s2/favicons?sz=64&domain=youtube.com
// @run-at       document-idle
// @grant        none
// ==/UserScript==

/*

----INSTRUCTIONS FOR USE-----
1. Download the Tampermonkey extention for your browser.
2. Copy and paste this text into a new script file within the extension
3. Go to the playlist page and it will start doing it's thing! Keep your mouse away from the page.
4. When it's done, check that it worked as expected, and disable the script 
   so you won't accidentally run it again in the future. 

Less than 100 videos: Will finish in a few minutes.
More than 100 videos: Will take hours, perhaps all night if the playlist is very long (500+).

If the playlist has +100 videos, the page will need to refresh after moving most videos 
after it gets past 100 (it sorts from top to bottom).
This is required because otherwise the page would quickly leak memory and become unusable.

It's finished when it stops moving for a while and nothing is loading.
You can open the web console to see it printing debug messages while it works if you want to see more information.

TIPS:
- Don't hover your mouse cursor over the page while it's working. This messes with the simulated mouse drag. 
- Keep the tab open. If you're walking away from the computer, you'll probably need to turn off your screensaver, 
  otherwise it may stop running.

*/


function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms))
}

function getVideoTitle(videoElement) {
    let result = "";
    let link = videoElement.querySelector('a[id="video-title"]');
    if (link) {
        result = link.title;
    } else {
        console.log(`Failed to find title in ${videoElement.innerText}`);
    }
    return result;
}

const MSFY_BUTTON = {
    TOP: "top",
    BOTTOM: "bottom"
};

async function msfyMoveVideos(msfyButton, videoElements, totalVideoCount) {
    if (videoElements.length && videoElements.length < totalVideoCount) {
        console.log(`Moving ${videoElements.length} videos to the ${msfyButton}`)
        let videoList = document.querySelector('ytd-item-section-renderer').querySelectorAll('ytd-playlist-video-renderer');
        let elementIndexMap = new Map();
        let movingVideoIds = []; 
        for (let videoElement of videoList) {
            for (let i = 0; i < videoElements.length; i++) {
                if (!elementIndexMap.has(videoElements[i]) && videoElement == videoElements[i]) {
                    elementIndexMap.set(videoElements[i], true);
                    movingVideoIds.push(getVideoId(videoElements[i]));
                }
            }
        }
        document.scrollingElement.scrollTop = 0; 
        if (!document.querySelector('[id^="msfy-bar-"]')) {
            document.querySelector('[id^="msfy-toggle-bar-button-"]').querySelector('yt-icon-button').dispatchEvent(new Event('tap'));
        }
        for (let videoElement of videoElements) {
            videoElement.querySelector(".msfy-video-checkbox").dispatchEvent(new Event('click'));
        }
        await sleep(50);
        document.querySelector('[id^="msfy-bar-"]').querySelector('[id^="menu"]').dispatchEvent(new Event('tap'))
        let button = null;
        while (!button) {
            button = document.querySelector(`[id^="msfy-action-move-to-${msfyButton}"]`)
            if (!button) {
                console.log(`Waiting for msfy button...`)
                await sleep(50);
            }
        }
        button.dispatchEvent(new Event('tap'))
        while (true) {
            let playlistVideos = document.querySelector('ytd-item-section-renderer');
            videoList = playlistVideos.querySelectorAll('ytd-playlist-video-renderer');
            let isMoved = true;
            if (msfyButton == MSFY_BUTTON.TOP) {
                for (let i = 0; i < movingVideoIds.length; i++) {
                    if (getVideoId(videoList[i]) != movingVideoIds[i]) {
                        isMoved = false
                        break;
                    }
                }
            }
            if (msfyButton == MSFY_BUTTON.BOTTOM) {
                //NOTE: (Ahmayk) YouTube does a terrible job reporting this back to us
                //so just YOLO it lol. We only do this right before a page refresh anyway
                //if it doesn't work we'll just try again next time
                sleep(3000);
                isMoved = true 
            }
            if (isMoved) {
                console.log(`Videos were moved!`)
                break;
            }
            console.log(`Waiting for videos to appear moved...`)
            await sleep(50);
        }
    }
}

//NOTE: (Ahmayk) This is just under 100 videos, as this does not trigger YouTube to reload the playlist entires
let chunkSize = 95;

function getVideoId(videoElement) {
    let result = ""
    let link = videoElement.querySelector(`a`).href;
    let linkSplit = link.split("watch?v=")
    if (linkSplit.length > 1) {
        result = linkSplit[1].slice(0, 11) 
    }
    return result
}

function getSortIndexesOfVideoElement(videoElement, videoIds) {
    let result = [];
    let firstBottomChunkVideoID = getVideoId(videoElement);
    for (let i = 0; i < videoIds.length; i++) {
        if (videoIds[i] == firstBottomChunkVideoID) {
            result.push(i);
        }
    }
    return result;
}

function alertIfPlaylistSorted(topSortedStats, totalVideoCount) {
    let result = false;
    if (topSortedStats.firstPlaylistIndex == 0 
        && topSortedStats.lastPlaylistIndex == totalVideoCount - 1) {
        alert("The playlist is sorted! Please disable this script so you don't run it again later by accident.")
        result = true;
    }
    return result;
}

function getTopSortedStats(videoList, videoIds) {
    let firstVideoElements = document.querySelector('ytd-item-section-renderer').querySelectorAll(`ytd-playlist-video-renderer:has([href*="/watch?v=${videoIds[0]}"])`);
    let firstPlaylistIndexes = [];
    let lastPlaylistIndexes = [];
    let lastSortIndexes = [];
    for (let i = 0; i < firstVideoElements.length; i++) {
        firstPlaylistIndexes[i] = Array.prototype.indexOf.call(videoList, firstVideoElements[i]);
        lastPlaylistIndexes[i] = firstPlaylistIndexes[i];
        lastSortIndexes[i] = 0;
        for (let playlistIndex = firstPlaylistIndexes[i] + 1, sortIndex = 1;
            (playlistIndex < videoList.length) && (sortIndex < videoIds.length);
            playlistIndex++, sortIndex++) 
        {
            let videoItem = videoList[playlistIndex].querySelector(`[href*="/watch?v=${videoIds[sortIndex]}"]`);
            if (!videoItem) {
                break;
            }
            lastPlaylistIndexes[i] = playlistIndex;
            lastSortIndexes[i] = sortIndex;
        }
    }
    let longestSortIndex = lastSortIndexes.reduce((a, b) => Math.max(a, b));
    let longestArrayIndex = lastSortIndexes.indexOf(longestSortIndex);

    let result = {};
    result.firstPlaylistIndex = firstPlaylistIndexes[longestArrayIndex];
    result.lastPlaylistIndex = lastPlaylistIndexes[longestArrayIndex];
    result.lastSortIndex = lastSortIndexes[longestArrayIndex];
    return result;
}

async function chunk_and_sort(videoIds) {

    let stop_execution = false 

    let totalVideoCount = 0;
    let xpath = "//span[contains(@class, 'ytAttributedStringHost') and contains(., ' videos')]";
    let matchingElement = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    if (matchingElement) {
        totalVideoCount = Number(matchingElement.textContent.split(' ')[0]);
    }
    if (totalVideoCount == null)  {
        alert("ABORTING: Failed to find Total number of Videos. YouTube may have changed it's layout. This code probably need to be updated!")
        stop_execution = true
    }

    if (totalVideoCount != videoIds.length) {
        alert(`ABORTING: The number of expected videos in the playlist (${totalVideoCount}) does not match the number of videos in this script's sorted list (${videoIds.length}). Please generate a new script.`)
        stop_execution = true
    }

    await sleep(2000);

    let playlistVideos = document.querySelector('ytd-item-section-renderer');
    let videoList = [] 
    if (!stop_execution) {
        while (totalVideoCount != playlistVideos.querySelectorAll('ytd-playlist-video-renderer').length) {
            document.scrollingElement.scrollTop = document.scrollingElement.scrollHeight;
            //TODO: (Ahmayk) do we need this?
            let spinnerIcon = document.querySelector('tp-yt-paper-spinner[active]');
            await sleep(100);
        }
        videoList = playlistVideos.querySelectorAll('ytd-playlist-video-renderer');
        if (!videoList.length) {
            alert("ABORTING: No videos found in playlist! YouTube may have changed its layout. This code probably needs to be updated!")
            stop_execution = true
        }
    }

    videoList = playlistVideos.querySelectorAll('ytd-playlist-video-renderer');
    if (!stop_execution) {
        let playlsitIndexMap = new Map();
        for (let sortIndex = 0; sortIndex < videoIds.length; sortIndex++) {
            let videoElement = null;
            for (let playlistIndex = 0; playlistIndex < videoList.length; playlistIndex++) {
                if (!playlsitIndexMap.has(playlistIndex) 
                    && getVideoId(videoList[playlistIndex]) == videoIds[sortIndex]) 
                {
                    videoElement = videoList[playlistIndex];
                    playlsitIndexMap.set(playlistIndex, true);
                    break;
                }
            }
            if (!videoElement) {
                alert(`ABORTING: Failed to find video in playlist with id: ${videoIds[sortIndex]}. Please generate a new script.`);
                stop_execution = true
                break;
            }
        }
    }

    if (!stop_execution) {
        let unrecognizedVideos = [];
        for (let videoElement of videoList) {
            let videoId = getVideoId(videoElement);
            if (!videoId.length) {
                alert(`ABORTING: Failed to find videoID in video HTML: ${getVideoTitle(videoElement)}. YouTube may have changed the layout of this page. This code probably needs to be updated!`);
                stop_execution = true;
                break;
            }
            if (!videoIds.some(v => v == videoId)) {
                unrecognizedVideos.push(videoElement)
            }
        }
        if (unrecognizedVideos.length) {
            let titles = unrecognizedVideos.map(v => getVideoTitle(v).join("\n- "))
            alert(`ABORTING: Unrecognized video in playlist. \n- ${titles}\n\nPlease generate a new script.`)
            stop_execution = true
        }
    }

    let topSortedStats = {};
    if (!stop_execution) {
        topSortedStats = getTopSortedStats(videoList, videoIds);
        if (alertIfPlaylistSorted(topSortedStats, totalVideoCount)) {
            stop_execution = true;
        }
    }

    let nextChunkSortIndexStart = 0;
    let needsMoveToTop = false;
    let nextSortingAreaElements = [];
    let usedShortcut = false;
    let sortIndexMax = 0;
    if (!stop_execution) {

        let firstSortIndexes = [];
        let lastSortIndexes = [];
        let sortIndexDistances = [];
        let matchingSortIndexes = getSortIndexesOfVideoElement(videoList[videoList.length - 1], videoIds);
        for (let i = 0; i < matchingSortIndexes.length; i++) {
            firstSortIndexes[i] = matchingSortIndexes[i];
            lastSortIndexes[i] = matchingSortIndexes[i];
            sortIndexDistances[i] = 0;
            for (let playlistIndex = totalVideoCount - 2, sortIndex = matchingSortIndexes[i] - 1;
                (playlistIndex < totalVideoCount) && (sortIndex >= 0);
                playlistIndex--, sortIndex--) 
            {
                let videoID = getVideoId(videoList[playlistIndex]);
                if (videoID != videoIds[sortIndex]) {
                    break;
                }
                firstSortIndexes[i] = sortIndex
                sortIndexDistances[i]++;
            }
        }
        let longestSequence = sortIndexDistances.reduce((a, b) => Math.max(a, b));
        let longestSequenceIndex = sortIndexDistances.indexOf(longestSequence);
        let firstBottomChunkSortIndex = firstSortIndexes[longestSequenceIndex];
        let lastBottomSortedVideoSortIndex = lastSortIndexes[longestSequenceIndex];

        if (topSortedStats.lastSortIndex > 0) {
            nextChunkSortIndexStart = topSortedStats.lastSortIndex + 1;
        }

        if (nextChunkSortIndexStart == firstBottomChunkSortIndex) 
        {
            nextChunkSortIndexStart = lastBottomSortedVideoSortIndex + 1; 
        }

        let playlsitIndexMap = new Map();
        let sortAreaFirstPlaylistIndex = 0;
        sortIndexMax = nextChunkSortIndexStart;;
        for (let sortIndex = nextChunkSortIndexStart;
            sortIndex < nextChunkSortIndexStart + chunkSize;
            sortIndex++
        ) {
            let videoElement = null;
            let chosenPlaylistIndex = 0;
            for (let playlistIndex = 0; playlistIndex < videoList.length; playlistIndex++) {
                if (!playlsitIndexMap.has(playlistIndex) 
                    && getVideoId(videoList[playlistIndex]) == videoIds[sortIndex]) 
                {
                    nextSortingAreaElements.push(videoList[playlistIndex]);
                    playlsitIndexMap.set(playlistIndex, true);
                    if (playlistIndex > 95) {
                        needsMoveToTop = true;
                    }
                    sortIndexMax = Math.max(sortIndexMax, sortIndex);
                    if (sortIndex == nextChunkSortIndexStart) {
                        sortAreaFirstPlaylistIndex = playlistIndex;
                    }
                    break;
                }
            }
        }
        let shortcutSectionVideoElements = [];
        for (let i = 0; i < videoList.length; i++)
        {
            if (getVideoId(videoList[i + sortAreaFirstPlaylistIndex]) != videoIds[i + nextChunkSortIndexStart]) {
                break;
            } 
            shortcutSectionVideoElements.push(videoList[i + nextChunkSortIndexStart])
        }
        if (shortcutSectionVideoElements.length > chunkSize) {
            await msfyMoveVideos(MSFY_BUTTON.BOTTOM, shortcutSectionVideoElements, totalVideoCount);
            usedShortcut = true;
        }
    }

    if (!stop_execution && !usedShortcut) {

        if (needsMoveToTop) {
            await msfyMoveVideos(MSFY_BUTTON.TOP, nextSortingAreaElements, totalVideoCount);
        }

        let videoIdsToSort = videoIds.slice(nextChunkSortIndexStart, sortIndexMax + 1) 
        let currentSortIndex = videoIdsToSort.length - 1;
        while (currentSortIndex >= 0) {
            videoList = document.querySelector('ytd-item-section-renderer').querySelectorAll('ytd-playlist-video-renderer');
            let videoElements = [];
            for (let i = Math.min(totalVideoCount, chunkSize) - 1; i >= 0; i--) {
                if (getVideoId(videoList[i]) == videoIdsToSort[currentSortIndex]) {
                    videoElements.push(videoList[i]);
                    currentSortIndex--;
                    if (currentSortIndex < 0) {
                        break;
                    }
                }
            }

            if (videoElements.length) {
                let isInOrder = true;
                for (let i = 0; i < videoElements.length; i++) {
                    if (videoList[i] != videoElements[i]) {
                        isInOrder = false;
                        break;
                    }
                }
                if (!isInOrder) {
                    await msfyMoveVideos(MSFY_BUTTON.TOP, videoElements, totalVideoCount);
                }
            } else {
                alert(`Video not found during sorting: ${videoIdsToSort[currentSortIndex]}`);
            }
        }

        videoList = document.querySelector('ytd-item-section-renderer').querySelectorAll('ytd-playlist-video-renderer');
        let videoElementsToMove = [];
        for (let playlistIndex = 0; playlistIndex < videoIdsToSort.length; playlistIndex++) {
            let videoID = getVideoId(videoList[playlistIndex]);
            if (videoIdsToSort.includes(videoID)) {
                videoElementsToMove.push(videoList[playlistIndex]);
            }
        }
        await msfyMoveVideos(MSFY_BUTTON.BOTTOM, videoElementsToMove, totalVideoCount);
    }

    if (!stop_execution && totalVideoCount < 95) {
        let newTopSortedStats = getTopSortedStats(videoList, videoIds);
        if (alertIfPlaylistSorted(newTopSortedStats, totalVideoCount)) {
            stop_execution = true;
        }
    }

    if (!stop_execution) {
        location.reload();
        await sleep(9999999);
    }
}

#META_VIDEO_IDS
 
const runCallback = () => {
    const element = document.querySelector('ytd-item-section-renderer');
    const msfy = document.querySelector('[id^="msfy-toggle-bar-button-"]');
    if (element && msfy) {
        chunk_and_sort(videoIds)
        return true;
    }
    return false;
};
runCallback()
const observer = new MutationObserver(() => {
    if (runCallback()) {
        observer.disconnect();
    }
});
const root = document.documentElement || document;
observer.observe(root, { childList: true, subtree: true });
setTimeout(() => observer.disconnect(), 30000);

