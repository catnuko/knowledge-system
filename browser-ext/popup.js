const DEFAULT_ENDPOINT = "http://127.0.0.1:8000";
const input = document.getElementById("endpoint");
const status = document.getElementById("status");

(async function init() {
  const { ke_endpoint } = await chrome.storage.local.get("ke_endpoint");
  input.value = ke_endpoint || DEFAULT_ENDPOINT;
})();

document.getElementById("save").addEventListener("click", async () => {
  let v = input.value.trim().replace(/\/$/, "");
  if (!v) v = DEFAULT_ENDPOINT;
  await chrome.storage.local.set({ ke_endpoint: v });
  status.textContent = "已保存：" + v;
  setTimeout(() => (status.textContent = ""), 2000);
});
