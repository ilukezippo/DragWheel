// DragWheel for Browser: right-click a video, song, link or page to play it in a DragWheel Float, or a picture
// to save it in another format. The work is done by the DragWheel app on this PC (native messaging).
const HOST = "com.ilukezippo.dragwheel";
const api = typeof browser !== "undefined" ? browser : chrome;

const FORMATS = [
  ["png", "PNG"], ["jpg", "JPG"], ["webp", "WebP"], ["avif", "AVIF"], ["gif", "GIF"], ["bmp", "BMP"],
  ["tiff", "TIFF"], ["ico", "ICO (icon)"], ["pdf", "PDF"], ["heic", "HEIC"], ["original", "As it is (original format)"],
];
const MEDIA_EXT = /\.(mp4|m4v|webm|mkv|mov|avi|mp3|m4a|aac|ogg|opus|flac|wav|m3u8)(\?|#|$)/i;

function buildMenus() {
  api.contextMenus.removeAll(() => {
    // one entry for videos, songs and links: a preview video inside a link (YouTube's home page) is both,
    // and two entries for the same thing only confused
    api.contextMenus.create({ id: "float-media", title: "Play in DragWheel Float", contexts: ["video", "audio", "link"] });
    api.contextMenus.create({ id: "float-page", title: "Play this page in DragWheel Float", contexts: ["page", "frame"] });
    api.contextMenus.create({ id: "img", title: "Save image as… (DragWheel)", contexts: ["image"] });
    for (const [id, label] of FORMATS) {
      api.contextMenus.create({ id: "img:" + id, parentId: "img", title: label, contexts: ["image"] });
    }
    api.contextMenus.create({ id: "img-sep", parentId: "img", type: "separator", contexts: ["image"] });
    api.contextMenus.create({ id: "img:wheel", parentId: "img", title: "Choose on the DragWheel wheel…", contexts: ["image"] });
  });
}
api.runtime.onInstalled.addListener(buildMenus);
api.runtime.onStartup && api.runtime.onStartup.addListener(buildMenus);

function send(msg) {
  return new Promise((resolve) => {
    try {
      api.runtime.sendNativeMessage(HOST, msg, (reply) => {
        const err = api.runtime.lastError;
        resolve(err ? { ok: false, missing: true, error: err.message } : (reply || { ok: false, error: "No answer" }));
      });
    } catch (e) {
      resolve({ ok: false, missing: true, error: String(e) });
    }
  });
}

async function report(tab, reply) {
  if (reply.ok) return;
  if (reply.missing) {           // DragWheel isn't installed (or is older than 1.2.3): show how to get it
    api.tabs.create({ url: "https://ilukezippo.github.io/DragWheel/#browser" });
    return;
  }
  if (tab && tab.id >= 0) {
    try {
      await api.scripting.executeScript({ target: { tabId: tab.id }, func: (m) => alert("DragWheel: " + m), args: [reply.error] });
    } catch (e) { /* pages like the Web Store can't show it */ }
  }
}

// pause the video or song on the page, so it carries on in the Float instead
async function pausePage(tab, frameId) {
  try {
    await api.scripting.executeScript({
      target: { tabId: tab.id, frameIds: [frameId || 0] },
      func: () => document.querySelectorAll("video, audio").forEach((m) => { try { m.pause(); } catch (e) {} }),
    });
  } catch (e) { /* not allowed on this page */ }
}

async function playInFloat(url, tab, frameId) {
  const reply = await send({ type: "float", url, title: tab ? tab.title : "" });
  if (reply.ok && tab) pausePage(tab, frameId);
  report(tab, reply);
}

function mediaUrl(info, tab) {
  // a real file address plays directly; a stream made by the page (blob:) can't leave it, so DragWheel
  // opens the page itself instead (YouTube and ~1,800 other sites)
  const src = info.srcUrl || "";
  if (/^https?:/i.test(src) && MEDIA_EXT.test(src)) return src;
  // a preview playing inside a link (YouTube's home page, search results…): the link is the video
  if (info.linkUrl && /^https?:/i.test(info.linkUrl)) return info.linkUrl;
  return info.frameUrl && info.frameUrl !== info.pageUrl && /^https?:/i.test(info.frameUrl) ? info.frameUrl
    : (info.pageUrl || (tab && tab.url));
}

function toBase64(buf) {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

function nameFrom(url, title) {
  try {
    const u = new URL(url);
    const last = decodeURIComponent(u.pathname.split("/").filter(Boolean).pop() || "");
    if (last && !/^(image|img|photo|download)$/i.test(last)) return last.replace(/\.[a-z0-9]{2,5}$/i, "");
  } catch (e) {}
  return (title || "image").slice(0, 60);
}

async function grabImage(info, tab) {
  const url = info.srcUrl;
  // 1) straight from here (works for most pictures, with the site's cookies)
  if (/^(https?|data):/i.test(url)) {
    try {
      const r = await fetch(url, { credentials: "include" });
      if (r.ok) {
        const b = await r.arrayBuffer();
        return { data: toBase64(b), mime: r.headers.get("content-type") || "" };
      }
    } catch (e) { /* try from the page */ }
  }
  // 2) from inside the page (blob: pictures, or ones only the page may load)
  const [res] = await api.scripting.executeScript({
    target: { tabId: tab.id, frameIds: [info.frameId || 0] },
    args: [url],
    func: async (u) => {
      try {
        const r = await fetch(u);
        const blob = await r.blob();
        const data = await new Promise((ok) => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.readAsDataURL(blob); });
        return { data: String(data).split(",")[1], mime: blob.type };
      } catch (e) {          // last try: draw the picture that's already on the page
        const img = [...document.images].find((i) => i.currentSrc === u || i.src === u);
        if (!img) return null;
        const c = document.createElement("canvas");
        c.width = img.naturalWidth; c.height = img.naturalHeight;
        c.getContext("2d").drawImage(img, 0, 0);
        try { return { data: c.toDataURL("image/png").split(",")[1], mime: "image/png" }; } catch (e2) { return null; }
      }
    },
  });
  return res && res.result;
}

async function saveImage(info, tab, format) {
  let pic = null;
  try { pic = await grabImage(info, tab); } catch (e) { pic = null; }
  if (!pic || !pic.data) {
    report(tab, { ok: false, error: "This picture can't be saved (the site protects it)." });
    return;
  }
  const reply = await send({ type: "image", data: pic.data, mime: pic.mime, url: info.srcUrl,
                             name: nameFrom(info.srcUrl, tab && tab.title), format });
  report(tab, reply);
}

api.contextMenus.onClicked.addListener((info, tab) => {
  const id = String(info.menuItemId);
  if (id === "float-media" || id === "float-link") playInFloat(mediaUrl(info, tab), tab, info.frameId);
  else if (id === "float-page") playInFloat(info.frameUrl || info.pageUrl || tab.url, tab, info.frameId);
  else if (id.startsWith("img:")) saveImage(info, tab, id.slice(4));
});

// the popup asks for these
api.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "ping") { send({ type: "ping" }).then(sendResponse); return true; }
  if (msg && msg.type === "float-tab") {
    api.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const t = tabs[0];
      if (t && /^https?:/i.test(t.url)) playInFloat(t.url, t, 0).then(() => sendResponse({ ok: true }));
      else sendResponse({ ok: false, error: "This page can't be played." });
    });
    return true;
  }
  return false;
});
