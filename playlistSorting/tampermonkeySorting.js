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

let numVideosPrevious = 0;
async function reloadIfVideosUnloaded(totalVideos, playlistVideos) {
    playlistVideos = document.querySelector('ytd-item-section-renderer');
    let numVideos = playlistVideos.querySelectorAll('ytd-playlist-video-renderer').length;
    console.log(`Bef Loaded: ${numVideosPrevious}\nNow Loaded: ${numVideos}`);
    if (numVideos != totalVideos && numVideos != (totalVideos - 2) && ((numVideos < numVideosPrevious) || (numVideos % 100 != 0))) {
        console.log("RESTARTING!")
        await sleep(1000);
        location.reload();
        await sleep(9999999999999);
    }
    numVideosPrevious = numVideos;
}

async function clickMenuButton(menuString, videoItem, videoId) {
    let openMenuButton = videoItem.querySelector(`yt-icon-button`);
    if (openMenuButton) {
        openMenuButton.dispatchEvent(new MouseEvent('click'));
        let menuItems = [];
        let moveButton = [];
        while (!menuItems.length || !moveButton.length) {
            await sleep(100);
            menuItems = document.querySelectorAll('ytd-menu-service-item-renderer');
            moveButton = Array.from(menuItems).filter(e => e.textContent.includes(menuString))
        }
        moveButton[0].dispatchEvent(new MouseEvent('click'));
        await sleep(500)
        console.log(`Moved ${videoId} (${menuString})`);
        return true;
    } else {
        console.error(`Failed to find menu button for ${videoId}`);
        return false;
    }
}

let fireMouseEvent = (type, elem, centerX, centerY) => {
    let event = new MouseEvent(type, {
        view: window,
        bubbles: true,
        cancelable: true,
        clientX: centerX,
        clientY: centerY
    });
    elem.dispatchEvent(event);
};


async function sortPlaylist(videoIds) {
    let numMoved = 0;
    let numVideosLoadesPrevious = 0;

    let totalVideos = 0;
    let xpath = "//span[contains(@class, 'ytAttributedStringHost') and contains(., ' videos')]";
    let matchingElement = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    if (matchingElement) {
        totalVideos = Number(matchingElement.textContent.split(' ')[0]);
    }
    if (totalVideos == null)  {
        console.error("Failed to find total videos");
    }

    let playlistVideos = null; 

    for (let videoIndex = 0; videoIndex < videoIds.length; videoIndex++) {

        let errorString = ""

        let videoItem = null;
        playlistVideos = document.querySelector('ytd-item-section-renderer');
        while (true) {
            videoItem = playlistVideos.querySelector(`ytd-playlist-video-renderer:has([href*="/watch?v=${videoIds[videoIndex]}"])`);
            if (videoItem) {
                break;
            }
            let numVideos = playlistVideos.querySelectorAll('ytd-playlist-video-renderer').length;
            if (totalVideos == numVideos) {
                console.log(`Video id not found: ${videoIds[videoIndex]}`)
                videoIndex++;
                if (videoIndex > videoIds.length - 1) {
                    break;
                }
            }
            document.scrollingElement.scrollTop = document.scrollingElement.scrollHeight;
            let spinnerIcon = document.querySelector('tp-yt-paper-spinner[active]');
            await sleep(250);
            await reloadIfVideosUnloaded(totalVideos, playlistVideos);
        }
        if (videoIndex > videoIds.length - 1) {
            break;
        }

        if (!videoItem) {
            errorString = `Video not found: ${videoIds[videoIndex]}`;
        }


        let numMovedPrev = numMoved;
        if (!errorString.length) {

            await reloadIfVideosUnloaded(totalVideos, playlistVideos);
            let videoList = playlistVideos.querySelectorAll('ytd-playlist-video-renderer');
            let index = Array.prototype.indexOf.call(videoList, videoItem);
            if (index != videoIndex) {

                if (videoIndex == 0) {
                    if (await clickMenuButton("Move to top", videoItem, videoIds[videoIndex])) {
                        numMoved++;
                    }
                }
                else if (videoIndex == videoIds.length - 1) {
                    if (await clickMenuButton("Move to bottom", videoItem, videoIds[videoIndex])) {
                        numMoved++;
                    }
                }
                else {

                    let replaceVideoItem = null 
                    if (!errorString.length) {
                        replaceVideoItem = Array.prototype.at.call(videoList, videoIndex);
                        if (!replaceVideoItem) {
                            errorString = `replaceVideoItem not found while processing ${videoIds[videoIndex]}`
                        }
                    }

                    let elemDrag = null; 
                    let elemDrop = null; 
                    if (!errorString.length) {
                        elemDrag = videoItem.querySelector('yt-icon#reorder');
                        elemDrop = replaceVideoItem.querySelector('a#thumbnail');
                        if (!elemDrag) {
                            errorString += "Drag element not found";
                        }
                        if (!elemDrop) {
                            if (errorString.length) errorString += '\n';
                            errorString += "Drop element not found";
                        }
                    }

                    let videoTitleDrag = null; 
                    if (!errorString.length) {
                        let link = videoItem.querySelector('a[id="video-title"]');
                        if (link) {
                            videoTitleDrag = link.title;
                        } else {
                            errorString = `Failed to find title in ${videoItem}`;
                        }
                    }

                    let videoTitleDrop = null; 
                    if (!errorString.length) {
                        let link = replaceVideoItem.querySelector('a[id="video-title"]');
                        if (link) {
                            videoTitleDrop = link.title;
                        } else {
                            errorString = `Failed to find title in ${replaceVideoItem}`;
                        }
                    }

                    if (!errorString.length) {

                        console.log(`Dragging ${videoTitleDrag} => ${videoTitleDrop}`);

                        elemDrop.scrollIntoView({ behavior: 'auto', block: 'center' });
                        await sleep(500);

                        let pos = elemDrag.getBoundingClientRect();
                        let center1X = Math.floor((pos.left + pos.right) / 2);
                        let center1Y = Math.floor((pos.top + pos.bottom) / 2);
                        pos = elemDrop.getBoundingClientRect();
                        let center2X = Math.floor((pos.left + pos.right) / 2);
                        let center2Y = Math.floor((pos.top + pos.bottom) / 2);

                        // mouse over dragged element and mousedown
                        fireMouseEvent("mousemove", elemDrag, center1X, center1Y);
                        fireMouseEvent("mouseenter", elemDrag, center1X, center1Y);
                        fireMouseEvent("mouseover", elemDrag, center1X, center1Y);
                        fireMouseEvent("mousedown", elemDrag, center1X, center1Y);
                        await sleep(100);

                        // start dragging process over to drop target
                        fireMouseEvent("dragstart", elemDrag, center1X, center1Y);
                        fireMouseEvent("drag", elemDrag, center1X, center1Y);
                        fireMouseEvent("mousemove", elemDrag, center1X, center1Y);
                        fireMouseEvent("drag", elemDrag, center2X, center2Y);
                        fireMouseEvent("mousemove", elemDrop, center2X, center2Y);
                        await sleep(100);

                        // trigger dragging process on top of drop target
                        fireMouseEvent("mouseenter", elemDrop, center2X, center2Y);
                        fireMouseEvent("dragenter", elemDrop, center2X, center2Y);
                        fireMouseEvent("mouseover", elemDrop, center2X, center2Y);
                        fireMouseEvent("dragover", elemDrop, center2X, center2Y);
                        await sleep(100);

                        // release dragged element on top of drop target
                        fireMouseEvent("drop", elemDrop, center2X, center2Y);
                        fireMouseEvent("dragend", elemDrag, center2X, center2Y);
                        fireMouseEvent("mouseup", elemDrag, center2X, center2Y);

                        await sleep(250);

                        playlistVideos = document.querySelector('ytd-item-section-renderer');
                        let videoList = playlistVideos.querySelectorAll('ytd-playlist-video-renderer');
                        videoItem = playlistVideos.querySelector(`ytd-playlist-video-renderer:has([href*="/watch?v=${videoIds[videoIndex]}"])`);
                        index = Array.prototype.indexOf.call(videoList, videoItem);
                        if (index != videoIndex)
                        {
                            console.log(`Index doesn't match, video may have missed. Expected ${videoIndex}, is ${index}`);
                        }
                        console.log(`Moved ${videoTitleDrag} to position ${videoIndex + 1}`);
                        numMoved++;
                        await sleep(2000);
                    }
                }
            }
        }

        if (errorString.length) {
            console.error(errorString);
        }

        if (numMovedPrev < numMoved) {
            await reloadIfVideosUnloaded(totalVideos, playlistVideos);
        }
    }

    if ((numMoved > 0) && totalVideos > 90) {
        console.log("RESTARTING! (finished maybe? Checking everything again)")
        await sleep(1000);
        location.reload();
        await sleep(9999999999999);
    }

    console.log("All videos confirmed to be sorted! Hopefully that worked...")
}

#META_VIDEO_IDS

const runCallback = () => {
    const element = document.querySelector('ytd-item-section-renderer');
    if (element) {
        sortPlaylist(videoIds)
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