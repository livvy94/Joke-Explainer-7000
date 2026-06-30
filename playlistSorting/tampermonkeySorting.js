// ==UserScript==
// @name         Playlist Sorter
// @namespace    http://tampermonkey.net/
// @version      2026-06-28
// @description  sort shit 
// @author       You
// @match        https://*.youtube.com/playlist*
// @icon         https://www.google.com/s2/favicons?sz=64&domain=youtube.com
// @grant        none
// @run-at       document-idle
// ==/UserScript==

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms))
}

async function searchForVideoInPage(videoId, playlistVideos) {
    let result = null;
    while (true) {
        result = playlistVideos.querySelector(`ytd-playlist-video-renderer:has([href*="/watch?v=${videoId}"])`);
        if (result) {
            break;
        }
        document.scrollingElement.scrollTop = document.scrollingElement.scrollHeight;
        await sleep(250);
        let spinnerIcon = document.querySelector('tp-yt-paper-spinner[active]');
        if (!spinnerIcon) {
            let numVideos = playlistVideos.querySelectorAll('ytd-playlist-video-renderer').length;
            console.log(`Videos loaded: ${numVideos}`);
        }
    }
    return result;
}

async function clickMenuButton(menuString, videoItem, videoId, playlistVideos) {
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
    let playlistVideos = document.querySelector('ytd-item-section-renderer');
    let numMoved = 0;
    for (let i = 0; i < videoIds.length; i++) {

        let errorString = ""
        let videoItem = await searchForVideoInPage(videoIds[i], playlistVideos);
        if (!videoItem) {
            errorString = `Video not found: ${videoIds[i]}`;
        }

        if (!errorString.length) {
            if (i == 0) {
                if (await clickMenuButton("Move to top", videoItem, videoIds[i], playlistVideos)) {
                    numMoved++;
                }
            }
            else if (i == videoIds.length - 1) {
                if (await clickMenuButton("Move to bottom", videoItem, videoIds[i], playlistVideos)) {
                    numMoved++;
                }
            }
            else {

                let previousVideoItem = await searchForVideoInPage(videoIds[i - 1], playlistVideos);
                if (!previousVideoItem) {
                    errorString = `Previous video not found while processing ${videoIds[i]}`
                }

                let replaceVideoItem = null; 
                if (!errorString.length) {
                    replaceVideoItem = previousVideoItem.nextElementSibling;
                    if (!replaceVideoItem) {
                        errorString = `Next sibling not found while processing ${videoIds[i]}`
                    }
                }

                let elemDrag = null; 
                let elemDrop = null; 
                if (!errorString.length) {
                    elemDrag = videoItem.querySelector('yt-icon#reorder');
                    await sleep(2000);
                    elemDrop = replaceVideoItem.querySelector('a#thumbnail');
                    await sleep(2000);
                    if (!elemDrag) {
                        errorString += "Drag element not found";
                    }
                    if (!elemDrop) {
                        if (errorString.length) errorString += '\n';
                        errorString += "Drop element not found";
                    }
                }

                if (!errorString.length) {
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

                    // start dragging process over to drop target
                    fireMouseEvent("dragstart", elemDrag, center1X, center1Y);
                    fireMouseEvent("drag", elemDrag, center1X, center1Y);
                    fireMouseEvent("mousemove", elemDrag, center1X, center1Y);
                    fireMouseEvent("drag", elemDrag, center2X, center2Y);
                    fireMouseEvent("mousemove", elemDrop, center2X, center2Y);

                    // trigger dragging process on top of drop target
                    fireMouseEvent("mouseenter", elemDrop, center2X, center2Y);
                    fireMouseEvent("dragenter", elemDrop, center2X, center2Y);
                    fireMouseEvent("mouseover", elemDrop, center2X, center2Y);
                    fireMouseEvent("dragover", elemDrop, center2X, center2Y);

                    // release dragged element on top of drop target
                    fireMouseEvent("drop", elemDrop, center2X, center2Y);
                    fireMouseEvent("dragend", elemDrag, center2X, center2Y);
                    fireMouseEvent("mouseup", elemDrag, center2X, center2Y);

                    console.log(`Moved ${videoIds[i]}`);
                    numMoved++;
                    await sleep(5000);
                }
            }
        }

        if (errorString.length) {
            console.error(errorString);
        }

        if (numMoved >= 50) {
            location.reload(true);
        }
    }
}

let videoIds = ["QmWCQXdg8O0", "yuJR4De31Ck", "r-e1dHyMukA", "Gc9N9estofY", "SyoTWIcwSL8", "VLtSA-rS3wI", "fzK9VXo9q6s", "SkZaqJoC6xY", "2sGaacd5wKA", "ktWtnpFCQqk", "T1NG-ZA-RcU", "us_NdEAdOKM", "69ptbA6T_wk", "G4PS_mQme4o", "6gn_duvLPUY", "sycwquJiqVM", "p7EIklBQ3OM", "Zeo3qCE2dfY", "sqwycArILrY", "zHep2hoY_xw", "z0MwCaJmxvM", "egnG2zO0sOQ", "ns6dXJt_Cek", "f9W8SuFTSuY", "R5lRaxbrmbk", "7z7-zsfAwJ4", "3HNus5bqBOE", "ax3cyLa9k64", "yMMRlkqNLKc", "HMlRWjndXh0"]
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