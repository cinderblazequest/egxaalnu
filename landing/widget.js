/* Встраиваемый виджет СПАС для школьных сайтов.
 *
 * Использование:
 *   <div id="spas-widget" data-api="https://api.spas.example/api"></div>
 *   <script src="https://your-username.github.io/spas-ai/widget.js" defer></script>
 *
 * Ожидаемый JSON от /api/scenarios:
 *   { "scenarios": [{ "id": ..., "title": ..., "icon": ..., "summary": ... }], "total": N }
 *
 * При ошибке загрузки — показывает кнопку "Открыть в Telegram" и тихо логирует.
 */

(function () {
  "use strict";

  const STYLE = `
    .spas-w { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; color: #f4f6f8; background: #15181d; border-radius: 16px; padding: 18px; max-width: 720px; }
    .spas-w h3 { margin: 0 0 12px; font-size: 18px; color: #ff3b30; }
    .spas-w .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; }
    .spas-w .item { background: #0b0d10; padding: 10px 12px; border-radius: 10px; display: flex; gap: 8px; align-items: flex-start; }
    .spas-w .item .ic { font-size: 18px; }
    .spas-w .item .tt { font-size: 14px; line-height: 1.3; }
    .spas-w .cta { display: inline-block; margin-top: 14px; padding: 10px 16px; background: #ff3b30; color: #fff; text-decoration: none; border-radius: 10px; font-size: 14px; }
    .spas-w .err { color: #b0b8c1; font-size: 13px; }
  `;

  function injectStyle() {
    if (document.getElementById("spas-w-style")) return;
    const s = document.createElement("style");
    s.id = "spas-w-style";
    s.textContent = STYLE;
    document.head.appendChild(s);
  }

  function fallback(host, botUrl) {
    host.innerHTML =
      '<div class="spas-w"><h3>СПАС — карманный AI-помощник первой помощи</h3>' +
      '<p class="err">Не удалось загрузить список сценариев. Открой бота напрямую — всё работает в Telegram.</p>' +
      `<a class="cta" href="${botUrl}" target="_blank" rel="noopener">🚀 Открыть в Telegram</a>` +
      "</div>";
  }

  function render(host, payload, botUrl) {
    const items = (payload && payload.scenarios) || [];
    const top = items.slice(0, 9);
    const rows = top
      .map(
        (s) =>
          `<div class="item"><span class="ic">${(s.icon || "•").replace(
            /</g,
            ""
          )}</span><div class="tt"><b>${(s.title || "")
            .replace(/</g, "")
            .replace(/>/g, "")}</b><br><span class="err">${(s.summary || "")
            .replace(/</g, "")
            .replace(/>/g, "")}</span></div></div>`
      )
      .join("");
    host.innerHTML =
      '<div class="spas-w"><h3>СПАС — 30 сценариев первой помощи</h3>' +
      `<div class="grid">${rows}</div>` +
      `<a class="cta" href="${botUrl}" target="_blank" rel="noopener">🚀 Открыть в Telegram</a>` +
      "</div>";
  }

  function init() {
    const host = document.getElementById("spas-widget");
    if (!host) return;
    injectStyle();
    const api = host.getAttribute("data-api") || "https://api.spas.example/api";
    const botUrl =
      host.getAttribute("data-bot") || "https://t.me/your_bot_username";
    fetch(api + "/scenarios", { cache: "default" })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((p) => render(host, p, botUrl))
      .catch(() => fallback(host, botUrl));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
