const port = chrome.runtime.connect({ name: "xhs-panel" });
let selectedTaskId = "";

const $ = (id) => document.getElementById(id);

function send(message) {
  return chrome.runtime.sendMessage(message);
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function sendToActiveTab(message) {
  const tab = await activeTab();
  if (!tab || !tab.id) throw new Error("找不到当前标签页");
  return chrome.tabs.sendMessage(tab.id, message);
}

function settings() {
  return {
    targetCount: Math.max(1, Math.min(200, Number($("targetCount").value || 20))),
    commentMode: $("commentMode").value,
    imageMode: $("imageMode").value,
    speed: $("speed").value,
    maxRetry: 2
  };
}

function setPageStatus(kind, text) {
  $("pageStatus").className = `status ${kind || ""}`;
  $("pageText").textContent = text;
}

async function detectPage() {
  try {
    const res = await sendToActiveTab({ type: "content:detect" });
    const page = res && res.page;
    if (!page || !page.ok) {
      setPageStatus("bad", page ? page.reason : "当前页面不可采集");
      return;
    }
    setPageStatus("ok", `可采集：当前可见 ${page.visibleCards} 个笔记卡片`);
  } catch (error) {
    setPageStatus("bad", "请刷新小红书页面后重试，或确认插件有权限访问当前页面");
  }
}

async function refreshTasks() {
  const res = await send({ type: "tasks:list" });
  const tasks = res.tasks || [];
  const wrap = $("tasks");
  wrap.textContent = "";
  if (!tasks.length) {
    const empty = document.createElement("div");
    empty.className = "task-meta";
    empty.textContent = "暂无任务";
    wrap.append(empty);
    selectedTaskId = "";
    return;
  }
  if (!selectedTaskId || !tasks.some((t) => t.id === selectedTaskId)) selectedTaskId = tasks[0].id;
  for (const task of tasks.slice(0, 8)) {
    const el = document.createElement("div");
    el.className = `task ${task.id === selectedTaskId ? "selected" : ""}`;
    el.tabIndex = 0;
    const total = task.found || task.settings.targetCount || 1;
    const done = task.done || 0;
    const pct = Math.max(0, Math.min(100, Math.round((done / total) * 100)));
    el.innerHTML = `
      <div class="task-title"></div>
      <div class="task-meta"></div>
      <div class="progress"><div style="width:${pct}%"></div></div>
    `;
    el.querySelector(".task-title").textContent = task.sourceTitle || task.sourceUrl || task.id;
    el.querySelector(".task-meta").textContent =
      `${task.status} · ${done}/${total} 完成 · 失败 ${task.failed || 0} · ${task.message || ""}`;
    el.addEventListener("click", () => {
      selectedTaskId = task.id;
      refreshTasks();
    });
    wrap.append(el);
  }
}

async function start() {
  await detectPage();
  const res = await sendToActiveTab({ type: "content:start", settings: settings() });
  if (!res.ok) setPageStatus("bad", res.error || "启动失败");
  await refreshTasks();
}

async function control(type) {
  await sendToActiveTab({ type });
}

async function exportSelected(format) {
  if (!selectedTaskId) return;
  const res = await send({ type: "notes:list", taskId: selectedTaskId });
  if (!res.ok) {
    setPageStatus("bad", res.error || "导出失败");
    return;
  }
  const notes = (res.notes || []).map((n) => n.data);
  if (format === "xlsx") {
    await exportXlsx(notes);
    return;
  }
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const text = format === "csv" ? notesToCsv(notes) : JSON.stringify(notes, null, 2);
  const mime = format === "csv" ? "text/csv;charset=utf-8" : "application/json;charset=utf-8";
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `xhs-notes-${stamp}.${format}`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

function allImageUrls(notes) {
  const urls = [];
  const seen = new Set();
  const push = (url) => {
    if (!url || seen.has(url)) return;
    seen.add(url);
    urls.push(url);
  };
  for (const note of notes) {
    for (const url of (note.meta && note.meta.noteImgs) || []) push(url);
    for (const comment of note.comments || []) {
      for (const url of comment.imgs || []) push(url);
    }
  }
  return urls;
}

function noteImageUrls(notes) {
  const urls = [];
  const seen = new Set();
  for (const note of notes) {
    for (const url of (note.meta && note.meta.noteImgs) || []) {
      if (!url || seen.has(url)) continue;
      seen.add(url);
      urls.push(url);
    }
  }
  return urls;
}

async function fetchImageForExcel(url) {
  const res = await send({ type: "image:fetch", url });
  if (!res || !res.ok) throw new Error(res && res.error ? res.error : "图片下载失败");
  return res;
}

function imageDataToPng(base64, contentType) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth || img.width;
        canvas.height = img.naturalHeight || img.height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0);
        resolve({
          base64: canvas.toDataURL("image/png"),
          extension: "png"
        });
      } catch (error) {
        reject(error);
      }
    };
    img.onerror = () => reject(new Error("图片格式转换失败"));
    img.src = `data:${contentType || "image/jpeg"};base64,${base64}`;
  });
}

async function excelImagePayload(image) {
  if (["jpeg", "png", "gif"].includes(image.extension)) {
    return {
      base64: `data:${image.contentType || "image/jpeg"};base64,${image.base64}`,
      extension: image.extension
    };
  }
  return imageDataToPng(image.base64, image.contentType);
}

function applyCellStyle(cell, fillColor, bold) {
  cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: `FF${fillColor}` } };
  cell.alignment = { vertical: "top", wrapText: true };
  cell.border = { bottom: { style: "thin", color: { argb: "FFCCCCCC" } } };
  if (bold) cell.font = { bold: true };
}

async function exportXlsx(notes) {
  if (!window.ExcelJS) {
    setPageStatus("bad", "ExcelJS 未加载，无法导出 XLSX");
    return;
  }
  setPageStatus("", "正在生成 XLSX，图片较多时会慢一些");

  const workbook = new ExcelJS.Workbook();
  workbook.creator = "小红书本地采集助手";
  workbook.created = new Date();
  const sheet = workbook.addWorksheet("小红书数据", {
    views: [{ state: "frozen", ySplit: 1 }]
  });

  sheet.columns = [
    { header: "序号", key: "seq", width: 8 },
    { header: "层级", key: "level", width: 8 },
    { header: "昵称/标题", key: "name", width: 22 },
    { header: "内容", key: "content", width: 80 },
    { header: "回复", key: "replyTo", width: 14 },
    { header: "时间", key: "date", width: 16 },
    { header: "IP", key: "ip", width: 10 },
    { header: "赞", key: "likes", width: 8 },
    { header: "图片", key: "images", width: 20 }
  ];

  const header = sheet.getRow(1);
  header.font = { bold: true, color: { argb: "FFFFFFFF" } };
  header.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF24292F" } };

  const colors = [
    "D6EAF8", "D5F5E3", "FCF3CF", "FADBD8", "E8DAEF",
    "D4E6F1", "ABEBC6", "F9E79F", "F5B7B1", "D2B4DE"
  ];
  let rowNo = 2;
  let commentSeq = 0;
  const imageCache = new Map();
  const embedTotal = noteImageUrls(notes).length;

  for (let noteIndex = 0; noteIndex < notes.length; noteIndex += 1) {
    const note = notes[noteIndex];
    const meta = note.meta || {};
    const fill = colors[noteIndex % colors.length];
    const postRowNo = rowNo;
    const postRow = sheet.getRow(rowNo);
    postRow.values = [
      noteIndex + 1,
      "帖子",
      meta.title || "",
      meta.desc || "",
      meta.barText || "",
      "",
      "",
      "",
      `图片×${(meta.noteImgs || []).length}`
    ];
    postRow.height = 30;
    for (let col = 1; col <= 9; col += 1) applyCellStyle(postRow.getCell(col), fill, true);

    const noteImgs = meta.noteImgs || [];
    for (let imgIndex = 0; imgIndex < noteImgs.length; imgIndex += 1) {
      const imageRowNo = postRowNo + imgIndex;
      if (imgIndex > 0) {
        const extraRow = sheet.getRow(imageRowNo);
        extraRow.height = 90;
        for (let col = 1; col <= 9; col += 1) applyCellStyle(extraRow.getCell(col), fill, false);
      }
      try {
        let image = imageCache.get(noteImgs[imgIndex]);
        if (!image) {
          image = await fetchImageForExcel(noteImgs[imgIndex]);
          imageCache.set(noteImgs[imgIndex], image);
        }
        const payload = await excelImagePayload(image);
        const imageId = workbook.addImage({
          base64: payload.base64,
          extension: payload.extension
        });
        sheet.getRow(imageRowNo).height = 92;
        sheet.addImage(imageId, {
          tl: { col: 8, row: imageRowNo - 1 },
          ext: { width: 120, height: 120 }
        });
      } catch (error) {
        sheet.getCell(imageRowNo, 9).value = `图片失败: ${String(error.message || error)}`;
      }
      setPageStatus("", `正在嵌入图片 ${imageCache.size}/${embedTotal}`);
    }

    rowNo = Math.max(rowNo + 1, postRowNo + noteImgs.length);

    const comments = note.comments || [];
    if (!comments.length) {
      const row = sheet.getRow(rowNo);
      row.values = ["", "无评论", "", "", "", "", "", "", ""];
      for (let col = 1; col <= 9; col += 1) applyCellStyle(row.getCell(col), fill, false);
      rowNo += 1;
    } else {
      for (const comment of comments) {
        commentSeq += 1;
        const row = sheet.getRow(rowNo);
        row.values = [
          commentSeq,
          comment.lvl === 2 ? "回复" : "评论",
          comment.nick || "",
          comment.content || "",
          comment.reply_to || "",
          comment.date || "",
          comment.ip || "",
          comment.likes || "0",
          (comment.imgs || []).join("\n")
        ];
        row.height = 24;
        for (let col = 1; col <= 9; col += 1) applyCellStyle(row.getCell(col), fill, false);
        if (comment.lvl === 2) row.font = { color: { argb: "FF555555" } };
        rowNo += 1;
      }
    }
    rowNo += 1;
  }

  const buffer = await workbook.xlsx.writeBuffer();
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  downloadBlob(
    new Blob([buffer], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }),
    `xhs-notes-${stamp}.xlsx`
  );
  setPageStatus("ok", `XLSX 已生成：${notes.length} 篇笔记`);
}

async function downloadSelectedImages() {
  if (!selectedTaskId) return;
  const res = await send({ type: "notes:list", taskId: selectedTaskId });
  if (!res.ok) {
    setPageStatus("bad", res.error || "读取任务失败");
    return;
  }
  const notes = (res.notes || []).map((n) => n.data);
  const urls = allImageUrls(notes);
  if (!urls.length) {
    setPageStatus("", "当前任务没有可下载图片");
    return;
  }
  const dl = await send({ type: "images:download", urls, folder: `xhs-images-${selectedTaskId}` });
  if (!dl.ok) {
    setPageStatus("bad", dl.error || "下载图片失败");
    return;
  }
  setPageStatus("ok", `已开始下载 ${dl.started} 张图片${dl.failed ? `，失败 ${dl.failed} 张` : ""}`);
}

function csvEscape(value) {
  const s = value == null ? "" : String(value);
  return /[",\n\r]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}

function notesToCsv(notes) {
  const rows = [[
    "note_id", "title", "desc", "bar_text", "image_count",
    "comment_level", "nick", "comment", "reply_to", "date", "ip", "likes"
  ]];
  for (const note of notes) {
    const meta = note.meta || {};
    const comments = note.comments || [];
    if (!comments.length) {
      rows.push([
        note.note_id, meta.title, meta.desc, meta.barText, (meta.noteImgs || []).length,
        "", "", "", "", "", "", ""
      ]);
      continue;
    }
    for (const c of comments) {
      rows.push([
        note.note_id,
        meta.title,
        meta.desc,
        meta.barText,
        (meta.noteImgs || []).length,
        c.lvl === 2 ? "reply" : "comment",
        c.nick,
        c.content,
        c.reply_to,
        c.date,
        c.ip,
        c.likes
      ]);
    }
  }
  return rows.map((row) => row.map(csvEscape).join(",")).join("\n");
}

$("detectBtn").addEventListener("click", detectPage);
$("startBtn").addEventListener("click", start);
$("pauseBtn").addEventListener("click", () => control("content:pause"));
$("resumeBtn").addEventListener("click", () => control("content:resume"));
$("stopBtn").addEventListener("click", () => control("content:stop"));
$("exportJsonBtn").addEventListener("click", () => exportSelected("json"));
$("exportCsvBtn").addEventListener("click", () => exportSelected("csv"));
$("exportXlsxBtn").addEventListener("click", () => exportSelected("xlsx"));
$("downloadImagesBtn").addEventListener("click", downloadSelectedImages);
$("deleteBtn").addEventListener("click", async () => {
  if (!selectedTaskId) return;
  await send({ type: "task:delete", taskId: selectedTaskId });
  selectedTaskId = "";
  await refreshTasks();
});
$("clearBtn").addEventListener("click", async () => {
  await send({ type: "tasks:clear" });
  selectedTaskId = "";
  await refreshTasks();
});

port.onMessage.addListener((message) => {
  if (message.type === "task:updated" || message.type === "tasks:changed") refreshTasks();
});

detectPage();
refreshTasks();
