/**
 * Vercel 빌드 단계에서 API 서버 주소를 주입한다.
 *   Build Command: node build-config.js
 *   Environment Variable: API_BASE_URL=https://<backend-host>
 *
 * 프레임워크/번들러 없이 동작하도록 js/config.js 파일을 그대로 다시 쓴다.
 */
const fs = require("fs");
const path = require("path");

const raw = process.env.API_BASE_URL || "";
const value = raw.trim().replace(/\/+$/, "");

const content = `// 빌드 시 자동 생성됨 (원본은 build-config.js)
window.__APP_CONFIG__ = {
  API_BASE_URL: ${JSON.stringify(value)},
};
`;

fs.writeFileSync(path.join(__dirname, "js", "config.js"), content, "utf8");
console.log(`[build-config] API_BASE_URL=${value || "(same-origin)"}`);
