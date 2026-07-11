(() => {
  const cardYMap = new Map();
  const BAD_TEXT = ["发布", "下载APP", "登录", "注册", "创作"];

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const jitter = (lo, hi) => lo + Math.random() * (hi - lo);

  function isXhsPage() {
    return location.hostname === "www.xiaohongshu.com";
  }

  function isSupportedPage() {
    return isXhsPage() && (
      location.pathname.includes("/search_result") ||
      location.pathname.includes("/explore") ||
      document.querySelectorAll(".note-item").length > 0
    );
  }

  function noteIdFromHref(href) {
    const m = /\/explore\/([a-z0-9]+)/i.exec(href || "");
    return m ? m[1] : "";
  }

  function findCardById(noteId) {
    const link = document.querySelector(`a[href*="/explore/${CSS.escape(noteId)}"]`);
    if (!link) return null;
    return link.closest(".note-item");
  }

  function collectCards() {
    const out = [];
    const scrollY = window.scrollY || 0;
    document.querySelectorAll(".note-item").forEach((item) => {
      const a = item.querySelector('a[href*="/explore/"]');
      const id = noteIdFromHref(a && a.href);
      if (!id) return;
      const rr = item.getBoundingClientRect();
      if (rr.width <= 0 || rr.height <= 0) return;
      const titleEl = item.querySelector(".title span") || item.querySelector(".title");
      const record = {
        id,
        href: a.href,
        title: (titleEl && titleEl.textContent || "").trim(),
        x: Math.round(rr.x + rr.width / 2),
        y: Math.round(rr.y + rr.height / 2),
        docY: Math.round(rr.y + scrollY)
      };
      cardYMap.set(id, record.docY);
      out.push(record);
    });
    const seen = new Set();
    return out.filter((item) => {
      if (seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    });
  }

  async function scanCards(target) {
    window.scrollTo(0, 0);
    await sleep(600);
    const seen = new Map();
    const merge = () => {
      const batch = window.xhsCrawlerLogic.waterfallSort(collectCards());
      for (const item of batch) {
        if (!seen.has(item.id)) seen.set(item.id, item);
      }
    };
    merge();
    for (let i = 0; i < 12 && seen.size < target; i += 1) {
      window.scrollBy(0, 1000);
      await sleep(800);
      merge();
    }
    return Array.from(seen.values()).slice(0, target);
  }

  function verifyClickTarget(card) {
    if (!card) return { ok: false, reason: "card_not_found" };
    const rr = card.getBoundingClientRect();
    const cx = Math.round(rr.x + rr.width / 2);
    const cy = Math.round(rr.y + rr.height / 2);
    const el = document.elementFromPoint(cx, cy);
    if (!el) return { ok: false, reason: "no_element" };
    const text = (el.textContent || "").slice(0, 60).trim();
    const bad = BAD_TEXT.find((t) => text.includes(t));
    const isCard = Boolean(el.closest(".note-item"));
    return {
      ok: !bad && isCard,
      reason: bad ? `bad_target:${bad}` : (isCard ? "" : "not_card"),
      text,
      tag: el.tagName,
      className: String(el.className || "").slice(0, 80)
    };
  }

  async function scrollToCard(noteId) {
    let card = findCardById(noteId);
    if (card) {
      const top = card.getBoundingClientRect().top + window.scrollY - window.innerHeight / 2;
      window.scrollTo(0, Math.max(0, top));
      await sleep(400);
      return findCardById(noteId);
    }
    const docY = cardYMap.get(noteId);
    if (docY != null) {
      window.scrollTo(0, Math.max(0, docY - 600));
      await sleep(900);
    }
    return findCardById(noteId);
  }

  function hoverClick(el) {
    const r = el.getBoundingClientRect();
    const opts = {
      bubbles: true,
      cancelable: true,
      clientX: Math.round(r.x + r.width / 2),
      clientY: Math.round(r.y + r.height / 2)
    };
    el.dispatchEvent(new MouseEvent("mousemove", opts));
    el.dispatchEvent(new MouseEvent("mousedown", opts));
    el.dispatchEvent(new MouseEvent("mouseup", opts));
    el.dispatchEvent(new MouseEvent("click", opts));
  }

  async function clickCard(noteId) {
    const card = await scrollToCard(noteId);
    const check = verifyClickTarget(card);
    if (!check.ok) return { ok: false, error: check.reason, detail: check };
    const cover = card.querySelector("a.cover") || card.querySelector('a[href*="/explore/"]') || card;
    cover.dispatchEvent(new MouseEvent("mousemove", { bubbles: true }));
    cover.click();
    await sleep(jitter(1800, 3200));
    return { ok: true };
  }

  function overlayVisible() {
    const mask = document.querySelector(".note-detail-mask");
    if (!mask) return false;
    return getComputedStyle(mask).display !== "none";
  }

  async function closeOverlay() {
    for (let i = 0; i < 5; i += 1) {
      if (!overlayVisible() && !document.querySelector(".preview-modal")) return;
      const close = document.querySelector(".close-circle") || document.querySelector('[class*="close"]');
      if (close) {
        hoverClick(close);
      } else {
        document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", keyCode: 27, bubbles: true }));
        document.dispatchEvent(new KeyboardEvent("keyup", { key: "Escape", code: "Escape", keyCode: 27, bubbles: true }));
      }
      await sleep(500);
    }
  }

  async function waitForComments(mode) {
    if (mode === "none") return;
    const maxRounds = mode === "top" ? 8 : 60;
    let last = 0;
    let stall = 0;
    for (let i = 0; i < maxRounds; i += 1) {
      const scroller = document.querySelector(".note-scroller");
      if (scroller) scroller.scrollTop = scroller.scrollHeight;
      await sleep(mode === "top" ? 600 : jitter(1000, 1800));
      const count = document.querySelectorAll(".comment-item").length;
      if (count === last) stall += 1;
      else {
        stall = 0;
        last = count;
      }
      if (stall >= (mode === "top" ? 2 : 5)) break;
    }

    const expandLimit = mode === "top" ? 5 : 80;
    for (let i = 0; i < expandLimit; i += 1) {
      const buttons = [
        ...document.querySelectorAll(".show-more"),
        ...document.querySelectorAll(".expand-btn")
      ].filter((el) => /展开|查看/.test((el.textContent || "").trim()));
      const btn = buttons.find((el) => {
        el.scrollIntoView({ block: "center" });
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      });
      if (!btn) break;
      hoverClick(btn);
      await sleep(mode === "top" ? 700 : jitter(1500, 2600));
    }
  }

  function extractMeta() {
    const title = (document.querySelector("#detail-title") || {}).textContent || document.title || "";
    const descEl = document.querySelector("#detail-desc,.desc");
    const desc = descEl ? (descEl.innerText || "").replace(/\s+/g, " ").trim() : "";
    const bar = document.querySelector(".engage-bar, [class*='engage']");
    const slides = [...document.querySelectorAll(".swiper-slide")];
    const noteImgs = [];
    const seen = new Set();
    for (const slide of slides) {
      const img = slide.querySelector("img");
      const src = img && img.src;
      if (!src || seen.has(src)) continue;
      seen.add(src);
      noteImgs.push(src);
    }
    const active = document.querySelector(".swiper-slide-active img");
    const startIdx = noteImgs.indexOf(active ? active.src : "");
    if (startIdx > 0) {
      const reordered = [];
      for (let i = 0; i < noteImgs.length; i += 1) reordered.push(noteImgs[(startIdx + i) % noteImgs.length]);
      return { title: title.trim(), desc, barText: bar ? bar.innerText.replace(/\s+/g, " ").trim() : "", hasVideo: Boolean(document.querySelector("video")), noteImgs: reordered };
    }
    return { title: title.trim(), desc, barText: bar ? bar.innerText.replace(/\s+/g, " ").trim() : "", hasVideo: Boolean(document.querySelector("video")), noteImgs };
  }

  function extractComments(mode) {
    if (mode === "none") return [];
    const comments = [];
    document.querySelectorAll(".comment-item").forEach((it) => {
      let p = it.parentElement;
      let lvl = 1;
      while (p) {
        if (p.classList && p.classList.contains("reply-container")) {
          lvl = 2;
          break;
        }
        p = p.parentElement;
      }
      const contentEl = it.querySelector(".note-text")
        || it.querySelector(".ai-comment-text-container")
        || it.querySelector(".text-content")
        || it.querySelector(".desc");
      const locEl = it.querySelector(".location");
      const ip = locEl ? (locEl.textContent || "").replace(/\s+/g, " ").trim() : "";
      const dateEl = it.querySelector(".date");
      const dateRaw = dateEl ? (dateEl.textContent || "").replace(/\s+/g, " ").trim() : "";
      const countText = (selector) => {
        const el = it.querySelector(selector);
        const text = el ? (el.textContent || "").replace(/\s+/g, "").trim() : "";
        return /^\d+$/.test(text) ? text : "0";
      };
      const imgs = [];
      it.querySelectorAll("img").forEach((img) => {
        const src = img.src || "";
        const cls = String(img.className || "");
        if (src && !src.includes("avatar") && !cls.includes("emoji")) imgs.push(src);
      });
      const nick = ((it.querySelector(".name") || {}).textContent || "").replace(/\s+/g, " ").trim();
      const content = contentEl ? (contentEl.innerText || "").replace(/\s+/g, " ").trim() : "";
      if (!nick && !content) return;
      comments.push({
        lvl,
        nick,
        content,
        date: ip ? dateRaw.replace(ip, "").trim() : dateRaw,
        ip,
        likes: countText(".interactions .like .count") || countText(".like .count"),
        replies: countText(".interactions .reply .count") || countText(".reply .count"),
        imgs
      });
    });
    return window.xhsCrawlerLogic.computeThreads(comments);
  }

  async function extractNote(noteId, commentMode) {
    await waitForComments(commentMode);
    const meta = extractMeta();
    if (!meta.title) return { ok: false, error: "empty_title" };
    const comments = extractComments(commentMode);
    return {
      ok: true,
      note: {
        note_id: noteId,
        url: `https://www.xiaohongshu.com/explore/${noteId}`,
        meta,
        comments,
        total_comments: comments.length,
        extracted_at: new Date().toISOString()
      }
    };
  }

  window.xhsCrawlerPage = {
    isSupportedPage,
    collectCards,
    scanCards,
    clickCard,
    closeOverlay,
    extractNote,
    sleep,
    jitter
  };
})();
