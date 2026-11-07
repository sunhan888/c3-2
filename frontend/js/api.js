/* DataMate API 클라이언트 (fetch 기반, 라이브러리 없음) */
(function () {
  const config = window.__APP_CONFIG__ || {};

  const normalise = (value) => String(value || "").trim().replace(/\/+$/, "");

  function resolveBaseUrl() {
    const fromQuery = new URLSearchParams(location.search).get("api");
    if (fromQuery) {
      localStorage.setItem("datamate.apiBase", normalise(fromQuery));
      return normalise(fromQuery);
    }
    const stored = localStorage.getItem("datamate.apiBase");
    if (stored) return normalise(stored);

    const configured = normalise(config.API_BASE_URL);
    if (configured) return configured;

    if (location.protocol === "file:") return "http://localhost:8000";
    const isLocalHost = ["localhost", "127.0.0.1"].includes(location.hostname);
    if (isLocalHost && location.port !== "8000") return "http://localhost:8000";
    return normalise(location.origin);
  }

  const baseUrl = resolveBaseUrl();

  function query(params) {
    if (!params) return "";
    const search = Object.entries(params)
      .filter(([, value]) => value !== undefined && value !== null && value !== "")
      .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
      .join("&");
    return search ? `?${search}` : "";
  }

  async function request(path, options = {}) {
    const { timeout = 90000, ...rest } = options;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(baseUrl + path, {
        ...rest,
        headers: {
          ...(rest.body ? { "Content-Type": "application/json" } : {}),
          ...(rest.headers || {}),
        },
        signal: controller.signal,
      });
      const text = await response.text();
      let data = null;
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (error) {
          data = { message: text.slice(0, 200) };
        }
      }
      if (!response.ok) {
        const detail = data && (data.detail || data);
        const message =
          (detail && (detail.message || detail.code)) ||
          (typeof detail === "string" ? detail : "") ||
          `요청이 실패했습니다 (${response.status})`;
        const error = new Error(message);
        error.status = response.status;
        error.payload = data;
        throw error;
      }
      return data;
    } catch (error) {
      if (error.name === "AbortError") {
        throw new Error("서버 응답이 너무 늦어요. 잠시 후 다시 시도해 주세요.");
      }
      if (error instanceof TypeError) {
        throw new Error(`API 서버(${baseUrl})에 연결할 수 없습니다. 서버 실행 상태를 확인해 주세요.`);
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  window.DataMateAPI = {
    baseUrl,
    request,
    health: () => request("/api/health", { timeout: 75000 }),
    summary: () => request("/api/data/summary"),
    statistics: () => request("/api/data/statistics"),
    listData: (params) => request(`/api/data${query(params)}`),
    createData: (payload) => request("/api/data", { method: "POST", body: JSON.stringify(payload) }),
    updateData: (id, payload) =>
      request(`/api/data/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(payload) }),
    deleteData: (id) => request(`/api/data/${encodeURIComponent(id)}`, { method: "DELETE" }),
    listConversations: () => request("/api/conversations?limit=50"),
    getConversation: (id) => request(`/api/conversations/${encodeURIComponent(id)}`),
    createConversation: (payload) =>
      request("/api/conversations", { method: "POST", body: JSON.stringify(payload) }),
    deleteConversation: (id) =>
      request(`/api/conversations/${encodeURIComponent(id)}`, { method: "DELETE" }),
    chat: (payload) => request("/api/chat", { method: "POST", body: JSON.stringify(payload), timeout: 150000 }),
    exportUrl: (format) => `${baseUrl}/api/data/export?format=${format === "json" ? "json" : "csv"}`,
    docsUrl: `${baseUrl}/docs`,
  };
})();
