(() => {
  const page = window.xhsCrawlerPage;
  let currentRun = null;

  function send(message) {
    return chrome.runtime.sendMessage(message);
  }

  function taskId() {
    return `task_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  }

  function speedDelay(speed) {
    if (speed === "conservative") return page.jitter(5000, 9000);
    return page.jitter(2500, 5500);
  }

  async function updateTask(task, patch) {
    Object.assign(task, patch, { updatedAt: Date.now() });
    await send({ type: "task:update", task });
  }

  async function detectPage() {
    if (!page.isSupportedPage()) {
      return {
        ok: false,
        reason: "请先打开小红书搜索结果页、话题页或包含笔记卡片的页面。"
      };
    }
    const cards = page.collectCards();
    return {
      ok: true,
      url: location.href,
      title: document.title,
      visibleCards: cards.length,
      overlayOpen: Boolean(document.querySelector(".note-detail-mask"))
    };
  }

  async function start(settings) {
    if (currentRun && currentRun.status === "running") {
      return { ok: false, error: "已有采集任务正在运行" };
    }
    if (!page.isSupportedPage()) {
      return { ok: false, error: "当前页面不是可采集的小红书页面" };
    }

    const controller = { status: "running", stop: false, pause: false };
    currentRun = controller;

    const task = {
      id: taskId(),
      sourceUrl: location.href,
      sourceTitle: document.title,
      settings,
      status: "running",
      found: 0,
      done: 0,
      failed: 0,
      skipped: 0,
      currentNoteId: "",
      message: "正在扫描当前页面"
    };
    await send({ type: "task:create", task });

    try {
      const cards = await page.scanCards(settings.targetCount);
      task.found = cards.length;
      await updateTask(task, {
        found: cards.length,
        message: cards.length ? `已发现 ${cards.length} 篇，开始采集` : "没有发现可采集笔记",
        status: cards.length ? "running" : "done"
      });
      if (!cards.length) return { ok: true, taskId: task.id };

      for (const card of cards) {
        if (controller.stop) break;
        while (controller.pause && !controller.stop) {
          await updateTask(task, { status: "paused", message: "已暂停" });
          await page.sleep(600);
        }
        if (controller.stop) break;

        task.currentNoteId = card.id;
        await updateTask(task, { status: "running", currentNoteId: card.id, message: `正在打开 ${card.title || card.id}` });

        let success = false;
        let lastError = "";
        const attempts = Math.max(1, Number(settings.maxRetry || 2) + 1);
        for (let attempt = 1; attempt <= attempts && !success && !controller.stop; attempt += 1) {
          await page.closeOverlay();
          const clicked = await page.clickCard(card.id);
          if (!clicked.ok) {
            lastError = clicked.error || "click_failed";
            await page.sleep(700);
            continue;
          }

          const extracted = await page.extractNote(card.id, settings.commentMode);
          if (!extracted.ok) {
            lastError = extracted.error || "extract_failed";
            await page.sleep(700);
            continue;
          }

          await send({ type: "note:put", taskId: task.id, note: extracted.note });
          success = true;
          task.done += 1;
          await updateTask(task, {
            done: task.done,
            currentNoteId: card.id,
            message: `完成 ${task.done}/${task.found}: ${extracted.note.meta.title}`
          });
        }

        if (!success && !controller.stop) {
          task.failed += 1;
          await send({
            type: "note:put",
            taskId: task.id,
            note: {
              note_id: card.id,
              url: card.href,
              meta: { title: card.title || "", desc: "", barText: "", hasVideo: false, noteImgs: [] },
              comments: [],
              total_comments: 0,
              error: lastError || "unknown",
              extracted_at: new Date().toISOString()
            }
          });
          await updateTask(task, { failed: task.failed, message: `失败 ${card.id}: ${lastError || "unknown"}` });
        }

        await page.closeOverlay();
        if (controller.stop) break;
        await page.sleep(speedDelay(settings.speed));
        if (settings.speed === "conservative" && Math.random() < 0.15) {
          await page.sleep(page.jitter(5000, 10000));
        }
      }

      const stopped = controller.stop;
      controller.status = stopped ? "stopped" : "done";
      await updateTask(task, {
        status: stopped ? "paused" : "done",
        currentNoteId: "",
        message: stopped ? "已停止，可导出已采集数据" : "采集完成"
      });
      return { ok: true, taskId: task.id };
    } catch (error) {
      await updateTask(task, {
        status: "blocked",
        message: String(error && error.message ? error.message : error)
      });
      return { ok: false, error: task.message, taskId: task.id };
    } finally {
      if (currentRun === controller) currentRun = null;
    }
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    (async () => {
      if (message.type === "content:detect") {
        sendResponse({ ok: true, page: await detectPage() });
        return;
      }
      if (message.type === "content:start") {
        start(message.settings).catch((error) => {
          console.error("[xhs-crawler] start failed", error);
        });
        sendResponse({ ok: true });
        return;
      }
      if (message.type === "content:pause") {
        if (currentRun) currentRun.pause = true;
        sendResponse({ ok: true });
        return;
      }
      if (message.type === "content:resume") {
        if (currentRun) currentRun.pause = false;
        sendResponse({ ok: true });
        return;
      }
      if (message.type === "content:stop") {
        if (currentRun) currentRun.stop = true;
        sendResponse({ ok: true });
        return;
      }
    })().catch((error) => {
      sendResponse({ ok: false, error: String(error && error.message ? error.message : error) });
    });
    return true;
  });
})();
