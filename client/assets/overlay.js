(() => {
  "use strict";

  const content = document.getElementById("content");
  const format = document.getElementById("format");
  const notice = document.getElementById("notice");
  const pageLabel = document.getElementById("page");
  const footerLabel = document.querySelector(".footer > span:first-child");
  const ROTATE_MS = 6500;
  const TEXT_PAGE_CHARS = 560;
  let materialKey = "";
  let pages = [];
  let pageIndex = 0;
  let rotationTimer = null;

  function setFooter(approved) {
    if (!footerLabel) return;
    const english = document.documentElement.lang === "en";
    footerLabel.textContent = approved
      ? english
        ? "Approved editorial intervention"
        : "Intervención editorial aprobada"
      : english
        ? "Local public output"
        : "Salida pública local";
  }

  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  };

  function stopRotation() {
    if (rotationTimer !== null) clearInterval(rotationTimer);
    rotationTimer = null;
  }

  function clear() {
    stopRotation();
    content.replaceChildren();
    format.textContent = "";
    notice.textContent = "";
    pageLabel.textContent = "";
    materialKey = "";
    pages = [];
    pageIndex = 0;
  }

  function splitText(value, maxChars = TEXT_PAGE_CHARS) {
    const text = String(value || "");
    if (!text.trim()) return [];
    const chunks = [];
    let remaining = text;
    while (remaining.length > maxChars) {
      let splitAt = remaining.lastIndexOf(" ", maxChars);
      const newlineAt = remaining.lastIndexOf("\n", maxChars);
      splitAt = Math.max(splitAt, newlineAt);
      if (splitAt < Math.floor(maxChars * 0.55)) splitAt = maxChars;
      chunks.push(remaining.slice(0, splitAt).trim());
      remaining = remaining.slice(splitAt).trimStart();
    }
    if (remaining.trim()) chunks.push(remaining.trim());
    return chunks;
  }

  function listItems(block) {
    return Array.isArray(block.items)
      ? block.items.map((item) =>
          typeof item === "string"
            ? item
            : String(item?.text || item?.label || ""),
        )
      : [];
  }

  function makePages(material) {
    const result = [];
    if (material.body) {
      for (const text of splitText(material.body))
        result.push({ type: "text", text });
    }
    for (const block of Array.isArray(material.blocks) ? material.blocks : []) {
      const type = String(block?.type || "text");
      const text = String(block?.text || "");
      const items = listItems(block);
      if (type === "comparison") {
        const comparisons = [];
        if (text.trim()) comparisons.push({ left: text, right: "" });
        for (let index = 0; index < items.length; index += 2) {
          comparisons.push({
            left: items[index] || "",
            right: items[index + 1] || "",
          });
        }
        for (const pair of comparisons) {
          const left = splitText(pair.left, 230);
          const right = splitText(pair.right, 230);
          const pageCount = Math.max(left.length, right.length, 1);
          for (let index = 0; index < pageCount; index += 1) {
            result.push({
              type,
              items: [left[index] || "", right[index] || ""],
              labels: ["A", "B"],
            });
          }
        }
      } else if (type === "steps") {
        const expanded = items.flatMap((item) => splitText(item, 230));
        const headers = splitText(text, 560);
        const pageCount = Math.max(
          Math.ceil(expanded.length / 3),
          headers.length,
          1,
        );
        for (let index = 0; index < pageCount; index += 1) {
          result.push({
            type,
            text: headers[index] || "",
            items: expanded.slice(index * 3, index * 3 + 3),
          });
        }
      } else {
        const contentText = text || items.join("\n");
        for (const part of splitText(contentText))
          result.push({ type, text: part });
      }
    }
    return result;
  }

  function drawPage() {
    content.querySelectorAll(".blocks").forEach((element) => element.remove());
    const page = pages[pageIndex];
    if (!page) {
      pageLabel.textContent = "";
      return;
    }
    const area = node("div", "blocks");
    if (page.type === "comparison") {
      const pair = node("div", "comparison");
      page.items.forEach((text, index) => {
        const card = node("div", "comparison-card");
        card.append(node("h2", "", page.labels[index]), node("p", "", text));
        pair.append(card);
      });
      area.append(pair);
    } else if (page.type === "steps") {
      const card = node("div", "block steps");
      if (page.text) card.append(node("p", "steps-heading", page.text));
      const list = node("ol");
      page.items.forEach((item) => list.append(node("li", "", item)));
      card.append(list);
      area.append(card);
    } else if (page.type === "callout") {
      area.append(node("div", "block callout", page.text));
    } else {
      area.append(node("div", "block text", page.text));
    }
    content.append(area);
    pageLabel.textContent = `${pageIndex + 1} / ${pages.length}`;
  }

  function renderEmpty(message) {
    clear();
    setFooter(false);
    const empty = node("div", "empty");
    empty.append(
      node(
        "strong",
        "",
        document.documentElement.lang === "en" ? "Waiting" : "En espera",
      ),
      node(
        "span",
        "",
        message ||
          (document.documentElement.lang === "en"
            ? "Approved public content will appear here."
            : "La pieza pública aparecerá aquí cuando esté disponible."),
      ),
    );
    content.append(empty);
  }

  function materialSignature(material) {
    return JSON.stringify({
      id: material.id,
      version: material.version,
      title: material.title,
      format: material.format,
      body: material.body,
      blocks: material.blocks,
    });
  }

  function render(material) {
    if (!material) {
      renderEmpty();
      return;
    }
    const key = materialSignature(material);
    if (key === materialKey) return;
    clear();
    materialKey = key;
    format.textContent = String(material.format || "").replaceAll("_", " ");
    const title = node(
      "h1",
      String(material.title || "").length > 90 ? "long-title" : "",
      material.title || "",
    );
    content.append(title);
    pages = makePages(material);
    pageIndex = 0;
    notice.textContent = "";
    setFooter(true);
    drawPage();
    if (pages.length > 1) {
      rotationTimer = setInterval(() => {
        pageIndex = (pageIndex + 1) % pages.length;
        drawPage();
      }, ROTATE_MS);
    }
  }

  async function poll() {
    try {
      const code = location.pathname.split("/").filter(Boolean).at(-1);
      if (!code) throw new Error("missing public code");
      const response = await fetch(`/api/public/${encodeURIComponent(code)}`, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      render(data.material || null);
    } catch {
      renderEmpty(
        document.documentElement.lang === "en"
          ? "Connection unavailable."
          : "No se pudo conectar.",
      );
    }
  }

  poll();
  setInterval(poll, 2000);
})();
