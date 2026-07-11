importScripts("db.js");

const livePorts = new Set();

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
});

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "xhs-panel") return;
  livePorts.add(port);
  port.onDisconnect.addListener(() => livePorts.delete(port));
});

function broadcast(message) {
  for (const port of livePorts) {
    try {
      port.postMessage(message);
    } catch (_) {
      livePorts.delete(port);
    }
  }
}

function normalizeTask(task) {
  const now = Date.now();
  return {
    id: task.id,
    tabId: task.tabId,
    sourceUrl: task.sourceUrl,
    sourceTitle: task.sourceTitle || "",
    settings: task.settings,
    status: task.status || "running",
    createdAt: task.createdAt || now,
    updatedAt: now,
    found: task.found || 0,
    done: task.done || 0,
    failed: task.failed || 0,
    skipped: task.skipped || 0,
    currentNoteId: task.currentNoteId || "",
    message: task.message || ""
  };
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

function extensionFromContentType(contentType, url) {
  const type = (contentType || "").toLowerCase();
  if (type.includes("png")) return "png";
  if (type.includes("webp")) return "webp";
  if (type.includes("gif")) return "gif";
  if (type.includes("jpeg") || type.includes("jpg")) return "jpeg";
  const clean = (url || "").split("?")[0].toLowerCase();
  if (clean.endsWith(".png")) return "png";
  if (clean.endsWith(".webp")) return "webp";
  if (clean.endsWith(".gif")) return "gif";
  return "jpeg";
}

function safeFilenamePart(value) {
  return String(value || "")
    .replace(/[\\/:*?"<>|]+/g, "_")
    .replace(/\s+/g, "_")
    .slice(0, 80) || "image";
}

async function fetchImage(url) {
  const resp = await fetch(url, {
    credentials: "include",
    headers: {
      "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
    }
  });
  if (!resp.ok) throw new Error(`图片请求失败 ${resp.status}`);
  const contentType = resp.headers.get("content-type") || "";
  const buffer = await resp.arrayBuffer();
  return {
    ok: true,
    url,
    contentType,
    extension: extensionFromContentType(contentType, url),
    base64: arrayBufferToBase64(buffer)
  };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    if (message.type === "task:create") {
      await putTask(normalizeTask(message.task));
      broadcast({ type: "task:updated", task: await getTask(message.task.id) });
      sendResponse({ ok: true });
      return;
    }

    if (message.type === "task:update") {
      const existing = await getTask(message.task.id);
      const task = normalizeTask({ ...(existing || {}), ...message.task });
      await putTask(task);
      broadcast({ type: "task:updated", task });
      sendResponse({ ok: true, task });
      return;
    }

    if (message.type === "note:put") {
      await putNote({
        id: `${message.taskId}:${message.note.note_id}`,
        taskId: message.taskId,
        noteId: message.note.note_id,
        data: message.note,
        createdAt: Date.now()
      });
      sendResponse({ ok: true });
      return;
    }

    if (message.type === "tasks:list") {
      const tasks = await listTasks();
      tasks.sort((a, b) => b.createdAt - a.createdAt);
      sendResponse({ ok: true, tasks });
      return;
    }

    if (message.type === "notes:list") {
      sendResponse({ ok: true, notes: await listNotes(message.taskId) });
      return;
    }

    if (message.type === "task:delete") {
      await deleteTask(message.taskId);
      broadcast({ type: "tasks:changed" });
      sendResponse({ ok: true });
      return;
    }

    if (message.type === "tasks:clear") {
      await clearAll();
      broadcast({ type: "tasks:changed" });
      sendResponse({ ok: true });
      return;
    }

    if (message.type === "image:fetch") {
      sendResponse(await fetchImage(message.url));
      return;
    }

    if (message.type === "images:download") {
      const urls = message.urls || [];
      const folder = safeFilenamePart(message.folder || "xhs_images");
      let started = 0;
      let failed = 0;
      for (let i = 0; i < urls.length; i += 1) {
        try {
          const image = await fetchImage(urls[i]);
          const ext = image.extension === "jpeg" ? "jpg" : image.extension;
          await chrome.downloads.download({
            url: `data:${image.contentType || "image/jpeg"};base64,${image.base64}`,
            filename: `${folder}/${String(i + 1).padStart(3, "0")}.${ext}`,
            saveAs: false
          });
          started += 1;
        } catch (_) {
          failed += 1;
        }
      }
      sendResponse({ ok: true, started, failed });
      return;
    }

    sendResponse({ ok: false, error: "unknown message" });
  })().catch((error) => {
    sendResponse({ ok: false, error: String(error && error.message ? error.message : error) });
  });
  return true;
});
