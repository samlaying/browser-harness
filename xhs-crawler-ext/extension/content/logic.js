(() => {
  function waterfallSort(items) {
    if (!items.length) return [];
    const ordered = [...items].sort((a, b) => (a.y === b.y ? a.x - b.x : a.y - b.y));
    const rows = [];
    let row = [];
    let lastY = null;
    for (const item of ordered) {
      if (row.length && lastY !== null && Math.abs(item.y - lastY) > 100) {
        rows.push(row);
        row = [];
      }
      row.push(item);
      lastY = item.y;
    }
    if (row.length) rows.push(row);
    for (const r of rows) r.sort((a, b) => a.x - b.x);
    return rows.flat();
  }

  function computeThreads(comments) {
    const out = comments.map((c) => ({ ...c }));
    let threadId = 0;
    let currentThread = 0;
    for (const comment of out) {
      if (comment.lvl === 1) {
        threadId += 1;
        currentThread = threadId;
        comment.thread_id = threadId;
        comment.reply_to = "";
      } else {
        comment.thread_id = currentThread;
        comment.reply_to = "";
      }
    }
    for (let i = 0; i < out.length; i += 1) {
      if (out[i].lvl !== 2) continue;
      for (let j = i - 1; j >= 0; j -= 1) {
        if (out[j].nick !== out[i].nick) {
          out[i].reply_to = out[j].nick || "";
          break;
        }
      }
    }
    return out;
  }

  window.xhsCrawlerLogic = { waterfallSort, computeThreads };
})();
