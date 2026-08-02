// ==UserScript==
// @name         smash temp 
// @namespace    http://tampermonkey.net/
// @version      1960-09-30
// @description  sort shit 
// @author       Joke-Explainer™ 7000
// @match        https://*.youtube.com/playlist?*
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

function getSortIndexOfVideoIdInPlaylist(videoId, videoIds, videoElement) {
    let result = -1;
    if (videoId.length > 0) {
        result = Array.prototype.indexOf.call(videoIds, videoId);
        if (result < 0) {
            alert(`Unrecognized video in playlist: ${getVideoTitle(videoElement)}. Please generate a new script.`)
        }
    }
    return result
}


async function sortPlaylist(videoIds) {
    let numMoved = 0;

    let playlistVideos = null; 

    for (let playlistIndex = 0; playlistIndex < videoIds.length; playlistIndex++) {

        let errorString = ""

        playlistVideos = document.querySelector('ytd-item-section-renderer');
        let videoItem = playlistVideos.querySelector(`ytd-playlist-video-renderer:has([href*="/watch?v=${videoIds[playlistIndex]}"])`);
        if (playlistIndex > videoIds.length - 1) {
            break;
        }

        if (!videoItem) {
            errorString = `Video not found: ${videoIds[playlistIndex]}`;
            alert(errorString)
        }

        let numMovedPrev = numMoved;
        if (!errorString.length) {

            let videoList = playlistVideos.querySelectorAll('ytd-playlist-video-renderer');
            let videoItemPlaylistIndex = Array.prototype.indexOf.call(videoList, videoItem);
            if (videoItemPlaylistIndex != playlistIndex) {

                if (playlistIndex == 0) {
                    if (await clickMenuButton("Move to top", videoItem, videoIds[playlistIndex])) {
                        numMoved++;
                    }
                }
                else {

                    let replaceVideoItem = null 
                    if (!errorString.length) {
                        replaceVideoItem = Array.prototype.at.call(videoList, playlistIndex);
                        if (!replaceVideoItem) {
                            errorString = `replaceVideoItem not found while processing ${videoIds[playlistIndex]}`
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

                    let videoTitleDrag = getVideoTitle(videoItem); 
                    let videoTitleDrop = getVideoTitle(replaceVideoItem); 

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
                        videoItem = playlistVideos.querySelector(`ytd-playlist-video-renderer:has([href*="/watch?v=${videoIds[playlistIndex]}"])`);
                        videoItemPlaylistIndex = Array.prototype.indexOf.call(videoList, videoItem);
                        if (videoItemPlaylistIndex != playlistIndex)
                        {
                            console.log(`Index doesn't match, video may have missed. Expected ${playlistIndex}, is ${videoItemPlaylistIndex}`);
                        }
                        console.log(`Moved ${videoTitleDrag} to position ${playlistIndex + 1}`);
                        numMoved++;
                        await sleep(2000);
                    }
                }
            }
        }

        if (errorString.length) {
            console.error(errorString);
        }
    }
}

function getVideoId(videoElement) {
    let result = ""
    let link = videoElement.querySelector(`a`).href;
    let linkSplit = link.split("watch?v=")
    if (linkSplit.length > 1) {
        result = linkSplit[1].slice(0, 11) 
    }
    else {
        alert(`Failed to find videoID in videoElement: ${getVideoTitle(videoElement)}. YouTube may have changed the layout of this page..`)
    }
    return result
}

function msfytoggle(openorclose) {
    while (!document.querySelector('[id^="msfy-bar-"]') || (window.getComputedStyle(document.querySelector('[id^="msfy-bar-"]')).display != openorclose)) {
        document.querySelector('[id^="msfy-toggle-bar-button-"]').querySelector('yt-icon-button').dispatchEvent(new Event('tap'));
    }
}

async function chunk_and_sort(videoIds) {

    let stop_execution = false 

    let totalVideos = 0;
    let xpath = "//span[contains(@class, 'ytAttributedStringHost') and contains(., ' videos')]";
    let matchingElement = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    if (matchingElement) {
        totalVideos = Number(matchingElement.textContent.split(' ')[0]);
    }
    if (totalVideos == null)  {
        alert("Failed to find Total number of Videos. YouTube may have changed it's layout. This code probably need to be updated!")
        stop_execution = true
    }

    let playlistVideos = document.querySelector('ytd-item-section-renderer');
    let videoList = [] 
    if (!stop_execution) {
        while (totalVideos != playlistVideos.querySelectorAll('ytd-playlist-video-renderer').length) {
            document.scrollingElement.scrollTop = document.scrollingElement.scrollHeight;
            //TODO: (Ahmayk) do we need this?
            let spinnerIcon = document.querySelector('tp-yt-paper-spinner[active]');
            await sleep(250);
        }

        videoList = playlistVideos.querySelectorAll('ytd-playlist-video-renderer');
        if (!videoList.length) {
            alert("No videos found in playlist! YouTube may have changed it's layout. This code probably needs to be updated!")
            stop_execution = true
        }
    }

    let topSortedFirstVideoElement = null;
    let topSortedFirstPlaylistIndex = 0;

    let topSortedLastVideoElement = null;
    let topSortedLastPlaylistIndex = 0;

    if (!stop_execution) {
        let firstVideoItem = playlistVideos.querySelector(`ytd-playlist-video-renderer:has([href*="/watch?v=${videoIds[0]}"])`);
        if (firstVideoItem) {
            topSortedFirstVideoElement = firstVideoItem;
            topSortedLastVideoElement = firstVideoItem;
            topSortedFirstPlaylistIndex = Array.prototype.indexOf.call(videoList, firstVideoItem);
            topSortedLastPlaylistIndex = topSortedFirstPlaylistIndex
            for (let playlistIndex = topSortedFirstPlaylistIndex + 1, sortIndex = 1;
                (playlistIndex < totalVideos) && (sortIndex < videoIds.length);
                playlistIndex++, sortIndex++) 
            {
                let videoItem = videoList[playlistIndex].querySelector(`[href*="/watch?v=${videoIds[sortIndex]}"]`);
                if (!videoItem) {
                    break;
                }
                topSortedLastPlaylistIndex = playlistIndex;
                topSortedLastVideoElement = videoItem;
            }
        } else {
            alert(`First video in sort order not found in playlist: ${videoIds[0]}. Please generate a new script.`);
            stop_execution = true
        }
    }

    if (!stop_execution && topSortedFirstPlaylistIndex == 0 &&  topSortedLastPlaylistIndex == totalVideos - 1) {
        alert("The playlist is sorted! Please disable this script so you don't run it again later by accident.")
        stop_execution = true
    }

    let firstBottomChunkPlaylistIndex = totalVideos - 1;
    let firstBottomChunkVideoID = "";
    let firstBottomChunkSortIndex = 0;
    let lastBottomSortedVideoSortIndex = 0;
    if (!stop_execution) {
        let lastVideoElement = videoList[videoList.length - 1];
        firstBottomChunkVideoID = getVideoId(lastVideoElement);
        firstBottomChunkSortIndex = getSortIndexOfVideoIdInPlaylist(firstBottomChunkVideoID, videoIds, lastVideoElement)
        lastBottomSortedVideoSortIndex = firstBottomChunkSortIndex;
        if (firstBottomChunkSortIndex == -1) {
            stop_execution = true
        }
    }

    let chunkSize = 100;
    let nextChunkSortIndexStart = 0;
    if (!stop_execution) {
        for (let playlistVideoIndex = firstBottomChunkPlaylistIndex - 1, sortVideoIndexBottom = firstBottomChunkSortIndex - 1;
             (playlistVideoIndex < totalVideos) && (sortVideoIndexBottom >= 0);
             playlistVideoIndex--, sortVideoIndexBottom--) 
        {
            let videoID = getVideoId(videoList[playlistVideoIndex]);
            if (videoID != videoIds[sortVideoIndexBottom]) {
                break;
            }
            firstBottomChunkPlaylistIndex = playlistVideoIndex;
            firstBottomChunkSortIndex = sortVideoIndexBottom
        }

        if (topSortedLastPlaylistIndex > topSortedLastPlaylistIndex) {
            let videoId = getVideoId(topSortedLastVideoElement);
            nextChunkSortIndexStart = getSortIndexOfVideoIdInPlaylist(videoId, videoIds, topSortedLastVideoElement) + 1;
            if (nextChunkSortIndexStart == -1) {
                stop_execution = true
            }
        }

        if (nextChunkSortIndexStart == firstBottomChunkSortIndex) {
            nextChunkSortIndexStart = lastBottomSortedVideoSortIndex + 1; 
        }
    }

    let tempSortIndexMin = 999999;
    let tempSortMap = new Map();
    if (!stop_execution) {
        for (let playlistIndex = 0; playlistIndex < Math.min(totalVideos, chunkSize); playlistIndex++) {
            let videoElement = videoList[playlistIndex];
            let videoID = getVideoId(videoElement);
            let sortIndex = getSortIndexOfVideoIdInPlaylist(videoID, videoIds, videoElement)
            if (sortIndex == -1) {
                stop_execution = true;
                break;
            }
            tempSortMap.set(sortIndex, videoElement)
            tempSortIndexMin = Math.min(sortIndex, tempSortIndexMin);
        }
    }

    if (!stop_execution) {

        let tempSortIndexMax = tempSortIndexMin;
        for (let sortIndex = tempSortIndexMin + 1; sortIndex < Math.min(totalVideos, chunkSize); sortIndex++) {
            if (!(sortIndex instanceof tempSortMap)) {
                break;
            }
            tempSortIndexMax = sortIndex;
        }
        let lastTempSortAreaPlaylistIndex = tempSortMap.get(tempSortIndexMin, tempSortIndexMax);

        if (tempSortIndexMin == nextChunkSortIndexStart) {
            let foo = 3
            await msfytoggle("none")
            let videoIdsToSort = videoIds.slice(tempSortIndexMin, tempSortIndexMax) 
            if (tempSortIndexMin == tempSortIndexMax) {
                videoIdsToSort.push(videoIds[tempSortIndexMin])
            }
            await sortPlaylist(videoIdsToSort);
            await msfytoggle("block")
            await sleep(1000)
    
            while (totalVideos != playlistVideos.querySelectorAll('ytd-playlist-video-renderer').length) {
                document.scrollingElement.scrollTop = document.scrollingElement.scrollHeight;
                await sleep(2000)
            }
    
            for (let playlistIndex = 0; playlistIndex < videoIdsToSort.length + 10; playlistIndex++) {
                let videoID = getVideoId(videoList[playlistIndex]);
                if (videoIdsToSort.includes(videoID)) {
                    videoList[playlistIndex].querySelector(".msfy-video-checkbox").dispatchEvent(new Event('click'));
                    await sleep(10);
                }
            }

            await msfytoggle("block");
            await sleep(500);
            while (!document.querySelector('[id^="msfy-action-move-to-bottom"]')) {
                document.querySelector('[id^="msfy-bar-"]').querySelector('[id^="menu"]').dispatchEvent(new Event('tap'))
                await sleep(1000);
            }
            document.querySelector('[id^="msfy-action-move-to-bottom"]').dispatchEvent(new Event('tap'))
        } else {
            for (let playlistIndex = 0; playlistIndex < totalVideos; playlistIndex++) {
                let videoElement = videoList[playlistIndex];
                let videoID = getVideoId(videoElement);
                let sortIndex = getSortIndexOfVideoIdInPlaylist(videoID, videoIds, videoElement)
                if (sortIndex >= nextChunkSortIndexStart && sortIndex <= nextChunkSortIndexStart + chunkSize) {
                    videoElement.querySelector(".msfy-video-checkbox").dispatchEvent(new Event('click'));
                    await sleep(10);
                }
            }

            await msfytoggle("block");
            await sleep(500);
            while (!document.querySelector('[id^="msfy-action-move-to-top"]')) {
                document.querySelector('[id^="msfy-bar-"]').querySelector('[id^="menu"]').dispatchEvent(new Event('tap'))
                await sleep(1000);
            }
            document.querySelector('[id^="msfy-action-move-to-top"]').dispatchEvent(new Event('tap'))
        }
    }

    if (!stop_execution) {
        playlistVideos = document.querySelector('ytd-item-section-renderer');
        let numVideos = playlistVideos.querySelectorAll('ytd-playlist-video-renderer').length;
        await sleep(2000);
        location.reload();
        await sleep(9999999);
    }
}

let videoIdsog = ["6oglz1oZP2o", "rm6c03N0HkM", "Jl-jP-qLlf0", "AsK4beTqFNE", "pCas579rdZI", "ggB0gzJ9Nqg", "Jf1VWwMfguQ", "qLbBQioG1_o", "rNm3MD8xCZk", "80IUAXznod0", "3cRm92AR2uc", "tPvHtl2HgPg", "vmZ5W3KDm7M", "pwzl8A2nUpo", "vWdRp6xgJGI", "DmaJd5SAeE8", "j38Nx5ADD-Q", "QFtWFPdF8YQ", "AThNViFCAAQ", "rEnb0ydVbIg", "282YHfUWKqs", "bAVX6LMrcyU", "dbbMbjOY0dM", "lAw00GvDKIs", "_sme63lfbqo", "GfPnnjH76MY", "-c7bzoFWhiY", "qUMn_0z6yNw", "B3wdz6agRFw", "YJTZUdPdvYk", "c7BQoZpOzo4", "pf6s7xkMHLA", "M_IxoOmwfbo", "Ibg4Jp3v6go", "Op1HwGdCwvo", "j-SepxDW9RE", "uw7sHwUAUAY", "xw1-IRlYWcw", "iRFC6JsPUrY", "mjxOQUBxylI", "KfYXsfCGv58", "3BDH2Z6HwAI", "QA1WVHymOQE", "XDFEjlatZg0", "5OLWJlEOcXw", "yeZ6B0XsmyM", "BqhYiL8VhHU", "q-D_su_mSFg", "7ZbvSeALptw", "yYHT5wldypQ", "WnkpzX6pDCw", "kHj00c4cgT8", "7daql0w6XWg", "3Bg1Bl1vni0", "-PLdnP33Yhc", "RAwtF1TZDAU", "AOVLkn1nH-c", "d4Bn-SJqldk", "q7ED0T24o-U", "QVfLS-BD_Q0", "bBk-P4te_t4", "3RLSsMJsE8U", "dTREBALZzLI", "HTOuYU3PFuI", "-jZVIKDwUHI", "YpldYlCjqMg", "9kXaZUPwCwg", "RBjCZpuLruY", "9s5Uf_KDVsQ", "ooHmcCoNJTU", "AjXCxzhol-0", "yEVMDBC2jBY", "qaz57HhKW54", "B8RPa4-NAGk", "GRvm059HqlA", "yQJF_bdfE3c", "5u7i0GayNqg", "VuAMhJAeEys", "afGa4pBDfhI", "zBPg69iDwbM", "3JDLcnhRDY8", "pcRPBKItkJc", "Z3GvlQXhNcA", "FoQqn3xOpZs", "HVtdeF2WCdg", "R7YvzGyEkOE", "kXHGpZ5ng6Y", "Ed8g8kIxBQU", "RlBASv6yHSw", "VlOzO31xm2w", "P-XniU0ElMA", "FY_MZHFH9vE", "EgXWnJKvRPQ", "uERAYQ_rQEw", "84ltHAqjN8g", "i-GZB5w6fAs", "J28NxCySimw", "vKYxtTz-Tu4", "1S8SHuR1574", "-mxQ7_BF4w4", "RUpm2Lw2nFA", "2ZdNdjSHMnc", "8eDPu8z8n28", "6uHEqAiDal8", "LyfRdrny2kY", "9Ne_cgHuvVs", "u9RkQH24W-U", "1AmkUytFX3E", "71XmZQr5RBw", "9vZlzks5wTs", "8d3KuETNh-c", "L21x9VKRHOU", "J8f5aW5UXdU", "ytb3-Sjb4jw", "xSGOAzD3bLc", "ko5WC0pA2ag", "4aajtc0KZTg", "ZEU8Aeo_T0Y", "tQjsp0_hh3Y", "g6RUEddyjQ8", "8v0NlldzfrI", "evcjlpCaBCc", "64gOmGfR7UM", "ZpkjAsQwxdw", "bxU138Yev4E", "ibp2eJm335o", "-TGG34nItI0", "61z5iPMxNzM", "uUHv59nKQgk", "7ASZc4ZeGR4", "JXu7PCKXTh8", "Uys7GnF-mhg", "DeTEGqsaD_I", "xlO622Ex8hQ", "dbDUqrixpyU", "wXe2OWSnKXI", "Wu9Tpw-vlNo", "ElPpB2Ie9dA", "1tm6MgkuhV8", "6rGrS2cFvc0", "CGyZOKr-dpA", "YEB7oZqkhI8", "j8n-B18IoXI", "iRj6Mo1A9_A", "Q0dwHrIAK0Y", "yNWhgnsuo8c", "dcxebiAEOEM", "eyR6eOGwvWo", "qzjYljC1qe8", "nwhx017twss", "vqQSzJeYFuI", "hRVBzmwdL48", "AxVBcWqjE9s", "-2mPqVs4CLI", "IbxM__X7MuM", "ttZi2WWzsJg", "KMsmhtiUY3c", "2ACNqqiBdiQ", "pvfAhoOWR2c", "nm-3jo9oFjU", "BzXNgh-4qlM", "h0ZCmX4U8YM", "JTFGl1_aiM0", "uDhiSSN6HIA", "FKFzaV2TOb0", "-qALH7IT0U0", "uGdCYeM6vmQ", "F_oj0lCXHnc", "6Aq64lNjfbw", "JMhZKXIFUik", "nb8CDiTc83g", "BPudobyHOHg", "KStHMeOoaGg", "cYEbTSbouKs", "Q2sjya-Wyc0", "uUzF1iSIHYk", "n-5NYqVfYtg", "TPhcwaXXvzQ", "XYuLNCxCwu8", "1veP8NzKpms", "7RNVK3JPwEA", "C09OyQ2CHSY", "0R_aEKjt7y0", "K4htnFhdHD8", "-FyZyQ08nHk", "fXSxcBMe60c", "r0YCSey604M", "-iuSTNdoBLw", "LltG3xiOmH4", "FljCKx4y3X0", "I3XzUKQ7Kpg", "HExQQ8rYxy8", "r1uzFdMB71Q", "YFhCvke7FJo", "Waexn86uksk", "IZJnKK1NbiA", "lWBov-FDJaI", "HTJqJHoeLn0", "m6IgprLFbfY", "moPuFJQxe54", "Vck0WTuwiLI", "-svgerGvk-M", "D8M2skkjkIo", "7xnAaaBO81U", "YapBLMYY6ks", "ZbFgBgZMA00", "oMago80OA9o", "_Q5F5-8UElE", "8kHD3FTsX5Q", "hJC9ca1hc84", "ZHHr7HX64i8", "YTFhNsb8ue8", "xBRhIsJZ2eU", "KRKLSAp8rh8", "Mn76Dz9C-Yo", "zQrjuLuFRvI", "VFMDtxxuMYc", "2mHbVdQGLd8", "-fDnj3p1d6o", "b1dfagrUdCo", "DgNop_NtDx4", "EW-Wp-AEa54", "RChUPyDwUTg", "ACjFffPPc78", "k2J_zHVTas0", "dksFnrGYCqw", "5xFnd1eFi1E", "JuY5kWzObdU", "m7vG4ho4B_k", "tvW0xoyOLvM", "ofiOQKXb1ko", "tKlYJDli5rQ", "LzhEt2EImBM", "4r2lXCe_R-I", "m7udS8qUMwk", "ERaUUBt6rIk", "CAbMEAmLCvY", "79Ey7pvO27w", "P64r0p0a63g", "599pjioNkLc", "5ldY2ChpK0M", "6949Wi2doGE", "_UKPnwISg2g", "92h8iACG2QQ", "JnYTFZRuojQ", "0RBUZyEZWeI", "HofLJL7uaB8", "zLW-0dwX8YQ", "vA7Xyh5YKwA", "9AkOPIg66pU", "WDTglkh9CGA", "5d-S2kKPlkc", "VOTimTXDjWo", "ZTb_lH1LEVA", "lPea6vvu0J0"]
 
const runCallback = () => {
    const element = document.querySelector('ytd-item-section-renderer');
    const msfy = document.querySelector('[id^="msfy-toggle-bar-button-"]');
    if (element && msfy) {
        chunk_and_sort(videoIdsog)
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

