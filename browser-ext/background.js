// knowledge-engine 浏览器扩展 service worker
// 右键菜单 → POST 选中文本到本地后端 /api/ingest

const DEFAULT_ENDPOINT = "http://127.0.0.1:8000";

async function endpoint() {
  const { ke_endpoint } = await chrome.storage.local.get("ke_endpoint");
  return ke_endpoint || DEFAULT_ENDPOINT;
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "ke-ingest-selection",
    title: "采集到 knowledge-engine",
    contexts: ["selection"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== "ke-ingest-selection") return;
  const text = (info.selectionText || "").trim();
  if (!text) return;
  const base = await endpoint();
  const url = base.replace(/\/$/, "") + "/api/ingest";
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, kind: "clipboard" }),
    });
    if (!res.ok) {
      const err = await res.text().catch(() => "");
      notify(`采集失败（${res.status}）${err.slice(0, 80)}`);
      return;
    }
    const r = await res.json();
    notify(`采集成功：新增 ${r.added ?? 0} 节点${r.deduped ? "（命中去重）" : ""}`);
  } catch (e) {
    notify(`采集失败：无法连接 ${base}（${e.message}）`);
  }
});

function notify(message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icon.png",
    title: "knowledge-engine",
    message,
  });
}
