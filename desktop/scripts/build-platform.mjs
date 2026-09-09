#!/usr/bin/env node
/**
 * 按当前平台自动选择对应的 Tauri 平台配置，执行 `tauri build`。
 *
 * 平台 → 配置文件映射：
 *   win32  → src-tauri/configs/windows/tauri.windows.conf.json
 *   linux  → src-tauri/configs/linux/tauri.linux.conf.json
 *   darwin → src-tauri/configs/macos/tauri.macos.conf.json
 *
 * 平台配置文件会与 src-tauri/tauri.conf.json 深合并（CLI --config 行为），
 * 因此平台文件里只放本平台差异项。
 */
import { spawnSync } from "node:child_process";
import { platform } from "node:process";

const MAP = {
  win32: "windows",
  linux: "linux",
  darwin: "macos",
};

const p = MAP[platform];
if (!p) {
  console.error(`[build-platform] 不支持的平台: ${platform}`);
  process.exit(1);
}

const config = `src-tauri/configs/${p}/tauri.${p}.conf.json`;
console.log(`[build-platform] 检测到平台 ${platform} → 使用配置 ${config}`);

const r = spawnSync("npx", ["tauri", "build", "--config", config], {
  stdio: "inherit",
  shell: process.platform === "win32",
});
process.exit(r.status ?? 1);
