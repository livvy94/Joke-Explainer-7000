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
// @grant        GM_log
// @grant        GM_openInTab
// @grant        window.close
// ==/UserScript==

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms))
}

let numVideosPrevious = 0;
async function reloadIfVideosUnloaded() {
    let playlistVideos = document.querySelector('ytd-item-section-renderer');
    let numVideos = playlistVideos.querySelectorAll('ytd-playlist-video-renderer').length;
    console.log(`Bef Loaded: ${numVideosPrevious}\nNow Loaded: ${numVideos}`);
    if (numVideos < numVideosPrevious) {
        console.log("RESTARTING!")
        await sleep(5000);
        location.reload();
        await sleep(9999999999999);
    }
    numVideosPrevious = numVideos;
}

async function searchForVideoInPage(videoId) {
    let result = null;
    await sleep(10);
    await reloadIfVideosUnloaded();
    while (true) {
        let playlistVideos = document.querySelector('ytd-item-section-renderer');
        result = playlistVideos.querySelector(`ytd-playlist-video-renderer:has([href*="/watch?v=${videoId}"])`);
        if (result) {
            break;
        }
        document.scrollingElement.scrollTop = document.scrollingElement.scrollHeight;
        let spinnerIcon = document.querySelector('tp-yt-paper-spinner[active]');
        await sleep(250);
        await reloadIfVideosUnloaded();
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
    let numMoved = 0;
    let numVideosLoadesPrevious = 0;
    for (let i = 0; i < videoIds.length; i++) {

        let errorString = ""
        let videoItem = await searchForVideoInPage(videoIds[i]);
        if (!videoItem) {
            errorString = `Video not found: ${videoIds[i]}`;
        }

        await reloadIfVideosUnloaded();

        if (!errorString.length) {

            let playlistVideos = document.querySelector('ytd-item-section-renderer');
            let videoList = playlistVideos.querySelectorAll('ytd-playlist-video-renderer');
            let index = Array.prototype.indexOf.call(videoList, videoItem);
            if (index != i) {

                if (i == 0) {
                    if (await clickMenuButton("Move to top", videoItem, videoIds[i])) {
                        numMoved++;
                    }
                }
                else if (i == videoIds.length - 1) {
                    if (await clickMenuButton("Move to bottom", videoItem, videoIds[i])) {
                        numMoved++;
                    }
                }
                else {

                    let replaceVideoItem = null 
                    if (!errorString.length) {
                        replaceVideoItem = Array.prototype.at.call(videoList, i);
                        if (!replaceVideoItem) {
                            errorString = `Next sibling not found while processing ${videoIds[i]}`
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

                    if (!errorString.length) {

                        console.log(`Dragging ${videoItem.outerText.split('\n')[0]} => ${replaceVideoItem.outerText.split('\n')[0]}`)

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

                        while (true) {
                            await sleep(250);
                            let playlistVideos = document.querySelector('ytd-item-section-renderer');
                            let videoList = playlistVideos.querySelectorAll('ytd-playlist-video-renderer');
                            videoItem = playlistVideos.querySelector(`ytd-playlist-video-renderer:has([href*="/watch?v=${videoIds[i]}"])`);
                            index = Array.prototype.indexOf.call(videoList, videoItem);
                            if (index == i)
                            {
                                break;
                            }
                            console.log(`Waiting for video to be moved`);
                        }

                        console.log(`Moved ${videoItem.innerText.split('\n')[0]}`);
                        numMoved++;
                        await sleep(3000);
                    }
                }
            }
        }

        if (errorString.length) {
            console.error(errorString);
        }

        await reloadIfVideosUnloaded();
    }
}

let videoIds = ["QmWCQXdg8O0", "yuJR4De31Ck", "r-e1dHyMukA", "Gc9N9estofY", "SyoTWIcwSL8", "VLtSA-rS3wI", "fzK9VXo9q6s", "SkZaqJoC6xY", "2sGaacd5wKA", "ktWtnpFCQqk", "T1NG-ZA-RcU", "us_NdEAdOKM", "69ptbA6T_wk", "G4PS_mQme4o", "6gn_duvLPUY", "sycwquJiqVM", "p7EIklBQ3OM", "Zeo3qCE2dfY", "sqwycArILrY", "zHep2hoY_xw", "z0MwCaJmxvM", "egnG2zO0sOQ", "ns6dXJt_Cek", "f9W8SuFTSuY", "R5lRaxbrmbk", "7z7-zsfAwJ4", "3HNus5bqBOE", "ax3cyLa9k64", "yMMRlkqNLKc", "HMlRWjndXh0", "YUr5h-thqtk", "akScCCwPX-8", "GDKtXm07iCg", "UPjGCjpIaA4", "Y4IQn2KUsEk", "0F9rPHJlkLA", "YOVbhom3Q0U", "7USvxTudkGQ", "r6kurinHCMQ", "sSWighf7K-M", "Fq5WcnoJNxs", "kWjYnXiup6o", "bcpKFaMYwIc", "CGvj-PrLNf8", "CvaltQJ_rWg", "4Fsd1Ilnnt4", "qHhTrSWnPuo", "lgJcSw1Rh2c", "le1hsYXaqDM", "KEaFCrFDTLk", "K6rkhw5U-rs", "1YKz6Jj-S8k", "V2RT8zSB2mo", "Bw9jP_RvdI0", "T0Pm9nDgj6Q", "nH8-oWKlJiY", "nmU13uStBkk", "uY8hz6USA6E", "1H1V_3W3k3w", "9ULhtCAiLb4", "EYld4X-Kfvs", "JtL_tQi5o6s", "9GIE7xS6NA8", "iVRml52gnFI", "oImikFhwLz0", "AEHJCP7F93E", "L1b_unkPFi8", "vnYthCrR_Vs", "WaWadq7ujPA", "PM1p7F-imLc", "NPCudJ833hY", "lA2-lYmtasc", "YKy46s6f23M", "3lfG4mygubY", "waLB8ePFzV0", "sm21VG-PDzQ", "IdtikjDd_20", "IQSZ6fQwKQQ", "0bapPVf29Mw", "rQ0N-n75e5g", "PeCIZOPo92I", "75cX1TUjmNY", "9-kS3jEzVeg", "H8VBbgqxbls", "OFjwuxDLPkI", "jIg90DF8B8A", "vO0XmEmgkQo", "6SR-71IWAko", "iEo20Q1vJzo", "OyN3N7B6axU", "Z1951c6OTnY", "5mS5l77Zjdw", "aTfLSc_SNOs", "L3wqtBfmKWk", "KfRQyEb6oRU", "jtSZ7oWuu8c", "H2qwWxU5Ec8", "KqWVddrlJts", "rJZ3bBoDzHo", "v6NtVO6rcsg", "lkHJlG_ZX_s", "1lag6506IlA", "UgRCA6jces8", "CwD_TvePkDw", "EE7z8OHOq6Y", "BYUIUxGPX9s", "tjrdnKNo150", "P46AgoYbhf4", "qZ6-Y_cwkXw", "BwvL9ZqXNTM", "gQbp1tAtKwM", "GBqeJavZB9Y", "aafjiZ2Nhz0", "381Q7tp9CdE", "Y6dRsllCWKU", "QYjTj3noN4U", "pp0Yr3H0q8s", "wp3BK4uzr0o", "l_oONUwHywY", "hz0eGHk8B3I", "WNyljAXjCbE", "VR43zQahlzI", "-BsSkJMtX2A", "om3snBkOqEM", "RItyYglxDO4", "ogQZipnG8s8", "zLEfwQ2lRvk", "sioS_bh8mf0", "rXbxcKxbcz0", "rD4ZKx48LxU", "fopq59R0XtY", "x_81o4ZsAUA", "uv7KGcplrYo", "vZEn3UOPBq4", "CqZk_uYOd7Q", "bbly8SGp7xk", "EljT0qs_QeU", "DfMpqVj_JqU", "FszmKSuKbKw", "teufuwnmWao", "KllLAcXTifA", "8JV22KWwNHY", "LEw_dF5GAoA", "bVgS9X0I6Ns", "Io7LzJwcGWA", "lAdV2_avdis", "IKvNyBG6bBg", "o4qnyaLUoPM", "pWD7XpovbI8", "CxtjlqvOSsM", "A4wJ0uXbRfE", "jEYMoINGCmo", "WmXiRn6aIB8", "EnuCnXZOAUA", "fPt9MBqmle4", "3t8ijHQU-As", "V7FZlVSqT2A", "RcHRPBT7yJI", "Kq6aCPGNTz0", "yHO_9ccaEgw", "VwUX4oe9bco", "neIpza9QyH4", "FFZg7NdCQY4", "o0M-e7SFeDs", "bH-nZ-k6Exg", "Q5V7KiCmYCo", "9UOpHkg9g6M", "nIUoSUoPtZk", "YTVvBCGlfpo", "wD13-BiHuec", "bEhuN6pslvg", "SBTgS58vnA0", "rhw83ZJXpe0", "PEZnXC48iI0", "ORV7Os_jENs", "1h2nRZdOTzU", "MKiF_kXFgdU", "SveNOCqL1-E", "Doryy5hV5zw", "_Znodw8SCNc", "_TlFG5k4SsE", "F-shwjwEMzo", "yjs84WUTjCs", "C0tHeyVdYjo", "daVvaioq4FY", "nyVa_B7IHHk", "pvkNF92YgrA", "j9q0Hk0_sls", "shseO80xIGs", "_R5H-E4jYf0", "fmDFFMebdmI", "KMnR_m-p15o", "p9u2JK_oUiQ", "1jaiZG-jhMM", "wAtHoloc-Ug", "Loq3himI0GQ", "sH3p99moGCA", "5_7fra9Q9YY", "3XA12-XXizM", "Mo5qw-MyJNA", "lr2n-MdVohI", "1gk-kdk6qM4", "GuTKb684rfM", "WTihdw8arwc", "PtaW4g4pXrI", "ZB4BTJMvAOs", "at263mcQehM", "mmE3XpvOKTg", "vF8Q8bSqO60", "aHI95A1Bngo", "RyPJ3WaKolc", "6G9inHyHQD4", "eENvCiXZv-Y", "Nth4tLeQ9SQ", "GIngN0MkOHM", "eBhBFIT05JU", "zxU0I36w8NE", "YJgvrQXlRaw", "3Qq2Nd5V5zo", "uEA05VPUMOU", "yqqXwkn0q7k", "ZwdiQtnqLQE", "Ux5FrJq0SzI", "rNMHGognPdI", "re9bzKegv6I", "2dlgQIXO1Ik", "axmuUu2-tiM", "RGZRLwdEXcg", "VS2cHqiaVLw", "NN4WMx_BFQQ", "YMz6789AlgA", "8VLHErKsD0k", "kyLV7rjOSDw", "ddwZYxcl1uQ", "FHMa7S9kFuM", "uXobneHjejc", "8inyEl2YBrI", "xMgGpID0Uw0", "VRYJvI9KRpQ", "aH35PAajXZI", "TGczxtHBAtA", "3yvlETwPYFQ", "sUNlS5Olh5c", "qpE_dwIJ0Vk", "yiyc_SzDe4Y", "jzfD2sqvVCA", "_moTPUZ28LA", "2gGeSC2AjY4", "0ppfzG1oVj0", "lgYcUFhcNjI", "bDcHWrsSiq0", "FBVWQ6OyOS0", "Z6BH0lbJkXA", "WKDNxgQ7XaE", "KA0ylFc77c8", "wMKY5L04_Bk", "SP7mbgoLQr4", "ZIk0KMVI2iA", "FlnvW54lkbE", "A-lD2co_on4", "hXVOoO2NShQ", "jcHA19kk_kU", "rmKRGwDtUfc", "8jmVaMFCDUA", "d8ozk86SZVQ", "72xyd5WKKXs", "1KZz-Y7vqyw", "KJ4H9aXZh78", "tOsXfuBeRs8", "wkxf1S4mPiI", "UysYvHND7Wk", "7xxrour_hiQ", "yk8oyWGx7q4", "MvU-9H4UcC4", "R_wxdcOtpBM", "OEjAuu1AMFg", "f9WMcHCsHrQ", "boXzsosOejw", "kuOFuWkwDto", "oxp0B6-QZlM", "8Ee_Jxu4XsE", "ZNJmyPWvQEs", "EBGSfj0ofS0", "Z8Ls9BOffq8", "4Vlv865BmDY", "RoGulh630GY", "VfXek9JL6sk", "tEOlLTOp9mQ", "s-ndncI6Md0", "akzkp3pGHfI", "ZOQfCJUVCeI", "X4-cAhL7RW0", "0fBzX_ZkRAY", "4xS6HTKzqF0", "QWtAE4L06Qk", "lrnZ9wmFbCw", "TUasZ15uowg", "_O3nDqhObTE", "kgwfnbIjUV8", "_KHaCWW7kdk", "gi0kPvuW05A", "Ew256ScEBeQ", "2ep5MiIKHIk", "yMDS9s5YTiM", "7B_2GIzr37A", "37Z7oHjr_JY", "2uI84s2uMYY", "CEhWTgk_-bY", "pUoEjYDdMgw", "Av0K-6lLovI", "2CPs-NB6xfY", "7k8fVZ_PgK0", "4aUgCnx3-Xc", "tLHZRcpKywA", "nJI4IlMTjCg", "6TgqSz4PE3w", "Tfk4jnA917U", "pPMoG_6qcBo", "grXEm1mOcxg", "7cPz5xQW3R0", "daLl3N-74s4", "GxHuMtqSejA", "pEjxGK2NT18", "B2kTSkFlRAY", "m6Re2_6AGzg", "hWjjEDaUIBk", "D2aShuY5vz8", "I_uoSDzOJuA", "C45gR7z6JXc", "8NJgfVWQ63A", "EoFu1WRuUrY", "ulKKsXxvv5A", "N2p8UCx511Q", "42-fwNW6qGk", "xserXZlv1vE", "ha_baXT_kaw", "2c8flxxUGNM", "HgGlNRmKaC0", "hDZwUYt9e6Q", "WpHqYj812jg", "QRFuetWUGlk", "dQk-RMAJs3I", "d9z7Rq_MEDk", "Dv3mbPZ4tQI", "6yw5kHnPjBg", "iexC-nOYVLA", "tdSCTSGEHtg", "g-JV_ZAu2AY", "8ND6ZHO_D2k", "1Qh1clOnLqQ", "WDMLWTZ1jws", "rqFqmNtcZBU", "_6F_6MAFKTk", "U_8s5Mw242s", "Pm3AVMWqlrg", "Ezd2eBFDnbE", "fWJrVllv0tQ", "TAHHHLbk_EY", "GEshS0RXArA", "U3AqO--bHQM", "lCi9yHpfefc", "6ECKwRzyckE", "eO0PD9TgIT0", "WkVk_ejzZFo", "fxrZdx2x0WA", "6qOQ1kxiP-M", "5Q3x_bM64xU", "fnhaE9FBZn8", "DT-MlmZbhwU", "fneyWJQdBCg", "FQ70xqGAlbE", "VYbZKe1m3Rc", "UR91Z62fUTU", "JPj1pGgIgbo", "usAkK1wd4ns", "SGyUNVk1EKc", "pBb_RxFFXzI", "CDu67qNrC6k", "EvwfDZbLeo8", "ph5WAeAhbY4", "AL2L4YJUMEQ", "y8JuoNY7nz8", "1ij3jYtuWRQ", "oN-v8k7PEFU", "gfB3fbkddQ4", "TrJ8Et0de1g", "J58obxxB_vk", "62H0TcRE7dI", "ov_S-vqb9MI", "E1Yzx8dB75o", "ZhvPTAZkeHk", "KZYNe9RO8oM", "G-84t-O_Fmw", "ObGatkmNkCI", "makZfVU_vUE", "WvPOpO0HeOk", "YllwvpK3mhs", "h7g28rbfKN4", "X-g68QMfhS8", "121Ors4ZL4I", "EOjbw2Cw3aY", "uHXoq8t3pcY", "bHsY1UFAbtM", "tjfFkBRDrp8", "Yu6z7w-vXuA", "LLQVNN55jR4", "6sHuQWhIXik", "BTSlUR4oLFs", "h0ENbpJGgfE", "ujTHOlYxqQs", "3bRC0RaTTNU", "CCN7ZJppgKA", "PT92kNLk_4A", "Q2mI65qn0To", "7v2nxr7XBZg", "wiIFojgc6SU", "_0pj7vK_8Qk", "MQNQJOcBdWM", "rytCv29RRg4", "Fhbhv9z3wWY", "W6rPmlIHwNE", "4ofrULy6ni0", "oRkivQRX6ps", "S9PSh0UOlGg", "_4zWS4FThds", "20NLIVccPf0", "8C8OUstU4Yg", "HPeXq2hGbBo", "QtUaZ1wfL50", "X-cIN4ANzCI", "XV0wwen_sPg", "FH32gbqu7pA", "bNk5dx3jd5U", "q_m0K3oU5vo", "kwY-M8wSq4s", "XWZUzVwYpdM", "DeNFQIF1hu0", "H-BFfeSBTps", "eFGSfWIQKQc", "ersX2Gr8ZOo", "hnxkFGG828I", "cbZwRCYmX4o", "rr1uxCxu-Z4", "DymR7K2I_N8", "gkhuz8mDn-8", "EZ0HXdV14bE", "ntYdHfHkMWU", "H3ZgNefaQjI", "_3KISHxsn0w", "Tjk2f2kDdek", "Vj8yfsqr3aQ", "L_NjKjYYN50", "Y9yHVheXvrI", "FsTk2AJJShY", "5cPNEy41qaI", "ewVwAd8yAsk", "bcD2K1x1JWQ", "7hAOpwbScEo", "CLvAksknvCQ", "R38tR0w8_as", "GLf5VFi2xSQ", "fN_MgWzGsCI", "HfEKmeDtjfU", "qqQuqqcL_-U", "CqySZs2JGLA", "OEafWyf1Ics", "SZvmNKp_TJM", "9F86kGv6dJE", "FmjQCHx7xp4", "89YdwN7LDiI", "LyTELbwTSBo", "N2S1gBS8jpA", "rYzUQ8UGHkg", "jg2t1xxZcmk", "fa-8mW5PT5E", "xfWNHSsUDv8", "SGgZNmG3Dhk", "N9d74crmfGU", "EEDoMG7YFh8", "axRHCn1F62E", "BahIl6k86Ko", "kPBqULVuEf8", "g1KDy6Xbu5o", "cL0lSYt2WhQ", "1xdIYZEoLmA", "ova8-uqjal8", "Yb-ZaKL02v8", "4gRFJS24nnU", "KRv0OfYv4FA", "XskUN8MT2FA", "Bp9TTtkeBjM", "h3Dv_WX2NyQ", "Ub8n79chJts", "8Fi7PUlCBls", "mh1sD5ZPkPk", "NDvpEAGNJ0E", "jGUjUx3fmok", "wdTJq3wy5Gg", "WBqyk7pOZnA", "4FK64JbP93s", "y0ZQ3HrYs9U", "z7n9TKOrLmg", "bklVCv6fcLY", "x5setqiHDBI", "ote66jQHKoo", "CCSfMMEBNlw", "MPfi1odwTpc", "DtE5Q7zsr1A", "npTjnLPNthQ", "pSuUPHOaWlk", "osCFo-lVknw", "xhMd_QyNpD4", "FyZlzDWbv8c", "OhZKqj4fcao", "9R0gCw0H7Vo", "CLORDgtsxWo", "nAAc4vAa9Fc", "fdTKVJ09Jkc", "C46EY9acWmI", "T7GL4pTGHpk", "WgmpO2zsC_8", "IfuZkG-pQG0", "g5fZ1uAUhZ8", "cx572652YPM", "quJ-mBvVBmA", "YMW4FRdEq6o", "0Ianzy8FQD8", "5DCDDOTldww", "cmEdn_q9Tl8", "g9L81NMW7os", "jJLTuQFVjDA", "k_PhzPVe6R8", "BaBcIRHwTdM", "83VZRsvey30", "UWg8lRVPniw", "tAV3uqcvbdQ", "_Jcsr-S0Xcc", "YfSFqLxwFfY", "NT8EAdNDTBo", "r7PYS9LBhgk", "xYA_ek96z4c", "Olub7wYNoKU", "Se9Fxr9Wb1w", "AGLn0kSS7ac", "w67j9GVYjWw", "ca8oAXDFd5A", "LefqeWI8a5g", "IHk5crriWTk", "6cyrqdv7Oac", "Dqxpd4atqhM", "z5ycY7SSX1w", "gIIke81jH8w", "IO3Lv_GI010", "1gB_BCVSgNg", "6PfurCWjaf8", "3Qy83-6XJ_0", "JExf4otmBG8", "iHejzBhKV9I", "ohHZ9qEd3I8", "IHOCAy1Wh0A", "0Tah01zJ-kY", "eVenpXG-qEU", "b16ZmqQfdEs", "rQe0PKqcfYw", "aLx3f5ldinI", "Y8QBO5BRhNw", "ZujRDiWBoDg", "zdOEevW7ZUM", "hUQog7O1vIw", "ZY7APhMsgS4", "-bnW_NmLsTQ", "tohvBQOY3Ro", "F4Wc-wpdHvc", "bZ-9m8K4HSs", "u5CUnY7MpzU", "MUaj5iliAlU", "An_PvoLcA18", "RplC92mB0uk", "wDfjPKtmb2A", "D4vzBLrq4kg", "rcRQSxEIdoY", "hEGb_Kay738", "dW06W13-rNw", "Z6xt0l9zeJc", "FDUVuk50v6U", "t9i1ofttIuA", "FPl7a6mrRl4", "Cn3soqTuB54", "cyQpqxiZShs", "U57BGh8iqCk", "bAWC6T6DFaE", "krDIK3EdHX0", "xQlBXH3lta4", "o_H2XHWnHxg", "1Zp2gUO4mJc", "-Cr6RrsoTgQ", "C-WguduP17w", "PllWwq1GSBQ", "6Ea8JzhH2Ho", "Xj_wnNR0IiI", "l-3GDaBjUUU", "Hsr1g3G3bcg", "TpAUQltMWc4", "nC2OCXRThkM", "owGCWvprMHg", "Sj6PQKTP3Vg", "cr57Dwh7Fqw", "jHujrf5JaUQ", "yjFJ_hYUfms", "yJCgU-VCPEU", "73ws96wlDVI", "3B5JDV60FQE", "Arp4jZO3or0", "etuGtsXPeu4", "r_XdlLzKDJ0", "fmdzkWMY9ZI", "2mgLFxbnelQ", "d0Do4r5nGk4", "oj6VVGx_jQg", "9JcbQlhVUIU", "WDxKkOmbhpk", "VcntaF6aUs4", "Yoob_8vD6MU", "6DIzZqaAPTU", "T8ohDTRsh2U", "CU3XCeIknhs", "HPeFJQ25fb8", "ms8n9L3TNuQ", "J42ZBHff89A", "oKQ0C2Ibsyc", "wBwCiyg-CpM", "RZ0uCASpIdQ", "wx0qUBGbYrw", "S9e6kSvgLIE", "W6ntsSLQddo", "hC_VT3MeJmU", "5hhQ7zQMDew", "1KHnvPimEkw", "bVxwUSG58yY", "JlPkmD1yjYI", "XeAsCKaGXlA", "fv6pY8I8N1I", "rKv3QhJgaoI", "P4MY-Ohfq4M", "kSPpcMq-2BU", "CoDlEmSirko", "XAly145mKEM", "_5kbIrbwl7s", "7ak3yKhevO0", "nSGjfwfaf70", "UbqM1-TxjS8", "pZd99cngmKY", "25-teeDdmag", "aOHNcdjE7fw", "3mC2P8EpS4E", "PH8xcR9XwIU", "BKMG1IQKnRY", "X9aHzwOn3oc", "7Osekae3bx8", "zqZ80u7UvSc", "7qcH5N4GmOo", "NAOLl7_1fLg", "XEfrFbb3K84", "wcCSKdfK2KI", "Udklxo5VURc", "z_hdLGUcFHU", "lPEsQfGbD94", "_1-MW05X01k", "PO59Z7MeZ5A", "QtAUSW1mO00", "v0TjiITlkjo", "-HsWxG9rb3c", "Mya3oHQ6QNQ", "eQtq6RxWG5E", "7ByFshQubwk", "dNpmwfr0Pgc", "AtY0l8wgdzI", "4OhFzFZdxrw", "a5BtZERv4ZY", "d-O2pCGNgo8", "80FH5YaLqk4", "gFtK8FA9Bhw", "2jaxjuytTOk", "4rdNur7VrNs", "GlpwovoAsoA", "QO_mHoT5yWA", "wi74TtwQlao", "AoU5z9quxpg", "6dbizKlt-f0", "A1Hlns9vjgU", "7yWO5nDlKBI", "3ShE2o8E0jg", "ADXMTuKxTp0", "V5tluLc81Wk", "E0OydnOHdbM", "WUe1hli-BX4", "IA-Xlq4n2cs", "qnAD6vjudQk", "Q-TmFarDhxk", "6fqqMOPTMQ4", "bw8rT8lmxf8", "MopP4ok8cLg", "ZlDGJzIkgiM", "6WmpNoUA9ak", "0TAAxtdqL1c", "qF19-NKg-os", "z5Nv1C4CFg0", "osJNwVtMkWE", "1QnZMXfYcQw", "L2__krjrF1g", "lv7geAopOJk", "ZA0GBxbpNDk", "433Js4xY5Y4", "XfUjhag69pw", "l1ZsLwMN5Js", "VK_0Fzwg3go", "iXeSkJxRWu0", "QNsA5mB8OVY", "IGyK6WN09ZY", "fy9isTN8C3U", "sblXelbykEc", "-h0_bjQlxp8", "Xy7UzTXNtn0", "nyY1ZxlSCnQ", "BQH2PzqdtGc", "37Uhg-LOiIo", "RVg_iygmw34", "Fl-LbvqDEXI", "NltNqSZ7zb4", "PMToyJ6NijU", "3tvdahNO8XU", "pqHIyCHwlV8", "-SW3GxdpkSU", "BnixtDo_YsI", "AEdHtCwAGMs", "8hskbUqkI6o", "ieYKqJJy55E", "JxDRxNwgRgA", "WTL2KYwKb2E", "_eR-7EX0Uqk", "x919HaPj91o", "0XahW0RHF6c", "x70FkCgkFJ8", "vl1dMvkt5w4", "wgojMapExGk", "RFOah4_TK18", "_etS-Vtp80c", "kstW4--CVPk", "HlhIUlEhY7U", "KXEE3Lb7Stc", "ouLUPqGnbjs", "BptVil_0vj0", "lFy9G1q3BPA", "OxQbSvZRzl0", "hr9YoRrQED8", "WWTqnFKbbss", "yqTef7YfLIs", "ew4E73dE_aE", "2v9Y8DYxePM", "t3icIyCVLS4", "U2UXa57zr7I", "1VfDZPymH5o", "R5pcPk_O3lQ", "m6-P-KVxv0c", "dTLb60j3ymI", "KY3DAFRYKAY", "kjr5k_2VSJc", "nAzlZelS2GA", "9WmXjYGdZ2s", "rlo1vjl-8_M", "jVRuhhjXyQg", "M9J1dsxf7yM", "gv0GTtoS8CM", "3iu8qxjU0mg"];
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