/* DataMate 프론트엔드 로직 (바닐라 JS) */
(function () {
  const api = window.DataMateAPI;
  const state = {
    summary: null,
    statistics: null,
    conversations: [],
    currentConversationId: null,
    dataItems: [],
    editingId: null,
    sending: false,
    health: null,
  };

  const el = {};
  const cache = (id) => document.getElementById(id);

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    [
      "status-chip", "status-text", "docs-link", "theme-toggle", "sidebar-toggle", "sidebar",
      "coldstart-banner", "new-chat", "conv-count", "conv-list", "refresh-all", "api-base",
      "sum-period", "sum-period-sub", "sum-count", "sum-count-sub", "sum-avg", "sum-avg-sub",
      "sum-trend", "sum-trend-sub", "chat-title", "chat-context", "chat-model", "chat-log",
      "quick-row", "composer", "chat-input", "send-btn", "data-form", "data-date", "data-value",
      "data-memo", "data-submit", "data-search", "data-count", "data-body", "volatility-badge",
      "trend-chart", "weekday-bars", "insight-stats", "monthly-table", "toast",
    ].forEach((id) => {
      const node = cache(id);
      el[id] = node;
      el[id.replace(/-([a-z])/g, (_, ch) => ch.toUpperCase())] = node;
    });

    el.apiBase.textContent = api.baseUrl.replace(/^https?:\/\//, "");
    el.docsLink.href = api.docsUrl;
    el.docsLink.title = `${api.docsUrl} (Swagger UI)`;
    el["data-date"].value = new Date().toISOString().slice(0, 10);

    initTheme();
    bindEvents();
    renderQuickChips();
    bootstrap();
  }

  /* ------------------------------------------------------------- bootstrap */
  async function bootstrap() {
    const slowTimer = setTimeout(() => {
      el.coldstartBanner.hidden = false;
    }, 4000);

    const healthPromise = api
      .health()
      .then((health) => {
        state.health = health;
        const storageLabel = health.storage_backend === "firestore" ? "Firestore" : "local";
        el["chat-model"].textContent = health.llm_configured
          ? `${health.model} · ${storageLabel}`
          : "데모 모드 · 규칙 기반";
        el["chat-model"].title = health.llm_configured
          ? "OPENAI_API_KEY가 설정되어 GPT가 응답합니다."
          : "OPENAI_API_KEY가 없어 규칙 기반 데모 응답을 사용합니다.";
        setStatus(
          "is-ok",
          `연결됨 · ${health.storage_backend === "firestore" ? "Firestore" : "로컬"} · ${health.data_points}건`
        );
        el.statusChip.title = `모델 ${health.model} · 도구 ${health.tools_enabled ? "ON" : "OFF"} · 대화 ${health.conversations}건`;
        return health;
      })
      .catch((error) => {
        setStatus("is-error", "서버 연결 실패");
        el.statusChip.title = error.message;
        return null;
      })
      .finally(() => {
        clearTimeout(slowTimer);
        el.coldstartBanner.hidden = true;
      });

    const results = await Promise.allSettled([
      healthPromise,
      loadSummary(),
      loadConversations(),
      loadData(),
    ]);
    const failed = results.filter((item) => item.status === "rejected");
    if (failed.length) {
      toast(failed[0].reason.message || "일부 데이터를 불러오지 못했어요.", true);
    }
    renderWelcome();
    loadStatistics().catch(() => {});
  }

  async function updateHealthChip() {
    try {
      const health = await api.health();
      state.health = health;
      const storage = health.storage_backend === "firestore" ? "Firestore" : "로컬";
      setStatus("is-ok", `연결됨 · ${storage} · ${health.data_points}건`);
    } catch (error) {
      /* 상태 칩 갱신 실패는 무시 */
    }
  }

  function setStatus(kind, text) {
    el.statusChip.classList.remove("is-ok", "is-error");
    if (kind) el.statusChip.classList.add(kind);
    el.statusText.textContent = text;
  }

  /* ----------------------------------------------------------------- theme */
  function initTheme() {
    const saved = localStorage.getItem("datamate.theme");
    const theme = saved || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.dataset.theme = theme;
  }

  function toggleTheme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("datamate.theme", next);
    renderChart();
  }

  /* --------------------------------------------------------------- formatting */
  const won = (value) => `${Math.round(Number(value) || 0).toLocaleString("ko-KR")}원`;

  function compactWon(value) {
    const number = Number(value) || 0;
    if (Math.abs(number) >= 100000000) return `${(number / 100000000).toFixed(1)}억원`;
    if (Math.abs(number) >= 10000) return `${Math.round(number / 10000).toLocaleString("ko-KR")}만원`;
    return won(number);
  }

  function shortDate(iso) {
    if (!iso) return "";
    return String(iso).slice(0, 10).replace(/-/g, ".");
  }

  function timeLabel(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    const now = new Date();
    if (date.toDateString() === now.toDateString()) {
      return date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
    }
    return `${date.getMonth() + 1}/${date.getDate()}`;
  }

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }

  function inlineFormat(text) {
    return text
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  function renderMarkdown(raw) {
    const lines = escapeHtml(raw || "").split("\n");
    const out = [];
    let list = null;
    let table = [];

    const flushList = () => {
      if (list) {
        out.push(`<ul>${list.join("")}</ul>`);
        list = null;
      }
    };
    const flushTable = () => {
      if (!table.length) return;
      const rows = table.map((line) =>
        line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim())
      );
      const isSeparator = (row) => row.length > 0 && row.every((cell) => /^:?-{2,}:?$/.test(cell));
      let header = null;
      let body = rows;
      if (rows.length >= 2 && isSeparator(rows[1])) {
        header = rows[0];
        body = rows.slice(2);
      }
      const html = ["<table>"];
      if (header) {
        html.push(`<thead><tr>${header.map((cell) => `<th>${inlineFormat(cell)}</th>`).join("")}</tr></thead>`);
      }
      html.push(
        `<tbody>${body
          .map((row) => `<tr>${row.map((cell) => `<td>${inlineFormat(cell)}</td>`).join("")}</tr>`)
          .join("")}</tbody>`
      );
      html.push("</table>");
      out.push(html.join(""));
      table = [];
    };

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
        flushList();
        table.push(trimmed);
        continue;
      }
      flushTable();
      if (!trimmed) {
        flushList();
        continue;
      }
      if (/^[-*•]\s+/.test(trimmed)) {
        list = list || [];
        list.push(`<li>${inlineFormat(trimmed.replace(/^[-*•]\s+/, ""))}</li>`);
        continue;
      }
      flushList();
      if (/^#{1,4}\s+/.test(trimmed)) {
        out.push(`<p><strong>${inlineFormat(trimmed.replace(/^#{1,4}\s+/, ""))}</strong></p>`);
        continue;
      }
      out.push(`<p>${inlineFormat(line)}</p>`);
    }
    flushTable();
    flushList();
    return out.join("");
  }

  function toast(message, isError = false) {
    el.toast.textContent = message;
    el.toast.classList.toggle("is-error", isError);
    el.toast.hidden = false;
    requestAnimationFrame(() => el.toast.classList.add("is-visible"));
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => {
      el.toast.classList.remove("is-visible");
      setTimeout(() => {
        el.toast.hidden = true;
      }, 220);
    }, 3200);
  }

  /* ------------------------------------------------------------------ events */
  function bindEvents() {
    el["theme-toggle"].addEventListener("click", toggleTheme);
    el["sidebar-toggle"].addEventListener("click", () => el.sidebar.classList.toggle("is-open"));
    el["new-chat"].addEventListener("click", startNewChat);
    el["refresh-all"].addEventListener("click", refreshAll);
    el.composer.addEventListener("submit", (event) => {
      event.preventDefault();
      sendMessage(el["chat-input"].value);
    });
    el["chat-input"].addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage(el["chat-input"].value);
      }
    });
    el["chat-input"].addEventListener("input", autoGrow);

    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => switchTab(tab.dataset.tab));
    });

    el["data-form"].addEventListener("submit", addData);
    el["data-search"].addEventListener(
      "input",
      debounce(() => loadData(), 320)
    );
    document.querySelectorAll("[data-export]").forEach((button) => {
      button.addEventListener("click", () => exportData(button.dataset.export));
    });

    window.addEventListener("resize", debounce(() => renderChart(), 200));
    if ("ResizeObserver" in window) {
      const observer = new ResizeObserver(() => renderChart());
      observer.observe(el.trendChart.parentElement);
    }
  }

  function autoGrow() {
    const input = el["chat-input"];
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
  }

  function debounce(fn, delay) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  }

  function switchTab(name) {
    document.querySelectorAll(".tab").forEach((tab) => {
      const active = tab.dataset.tab === name;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    document.querySelectorAll(".panel").forEach((panel) => {
      const active = panel.id === `panel-${name}`;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });
    if (name === "insight") {
      renderChart();
      if (!state.statistics) loadStatistics().catch((error) => toast(error.message, true));
    }
  }

  function refreshAll() {
    loadSummary();
    loadConversations();
    loadData();
    loadStatistics();
    api
      .health()
      .then((health) => {
        state.health = health;
        setStatus("is-ok", `연결됨 · ${health.storage_backend === "firestore" ? "Firestore" : "로컬"} · ${health.data_points}건`);
      })
      .catch((error) => setStatus("is-error", error.message));
    toast("최신 상태로 새로고침했어요.");
  }

  /* ----------------------------------------------------------------- summary */
  async function loadSummary() {
    const summary = await api.summary();
    state.summary = summary;
    renderSummary(summary);
    return summary;
  }

  function renderSummary(summary) {
    if (!summary || summary.empty) {
      el.sumPeriod.textContent = "데이터 없음";
      el.sumPeriodSub.textContent = "데이터를 먼저 추가해 주세요";
      el.sumCount.textContent = "0건";
      el.sumAvg.textContent = "—";
      el.sumTrend.textContent = "—";
      el["chat-context"].textContent = "저장된 데이터가 없습니다. '데이터 관리' 탭에서 추가해 주세요.";
      return;
    }

    el.sumPeriod.textContent = `${shortDate(summary.period.start)} ~ ${shortDate(summary.period.end)}`;
    el.sumPeriodSub.textContent = `${summary.period.days}일 구간`;

    el.sumCount.textContent = `${summary.count.toLocaleString("ko-KR")}건`;
    el.sumCountSub.textContent = "일별 레코드";

    el.sumAvg.textContent = won(summary.metrics.average);
    el.sumAvgSub.textContent = `최고 ${compactWon(summary.metrics.max)} · 최저 ${compactWon(summary.metrics.min)}`;

    const trend = summary.trend;
    const sign = trend.change_pct >= 0 ? "+" : "";
    el.sumTrend.textContent = `${trend.direction} ${sign}${trend.change_pct}%`;
    el.sumTrend.className = trend.direction === "하락" ? "down" : trend.direction === "상승" ? "up" : "";
    el.sumTrendSub.textContent = `직전 ${trend.window_days}일 대비`;

    el["chat-context"].textContent =
      `컨텍스트: ${summary.count}개 레코드 · ${summary.period.label} · ${trend.label}`;
  }

  /* ----------------------------------------------------------- conversations */
  async function loadConversations() {
    const data = await api.listConversations();
    state.conversations = data.items || [];
    el.convCount.textContent = String(data.total ?? state.conversations.length);
    renderConversationList();
  }

  function renderConversationList() {
    if (!state.conversations.length) {
      el.convList.innerHTML = '<li class="conv-empty">아직 저장된 대화가 없어요.<br />첫 질문을 보내 보세요.</li>';
      return;
    }
    el.convList.innerHTML = state.conversations
      .map((conversation) => {
        const active = conversation.id === state.currentConversationId ? " is-active" : "";
        return `
          <li class="conv-item${active}" data-id="${conversation.id}" tabindex="0">
            <span class="conv-title">${escapeHtml(conversation.title)}</span>
            <span class="conv-meta">${conversation.message_count}개 메시지 · ${timeLabel(conversation.updated_at)}</span>
            <button class="conv-delete" data-delete="${conversation.id}" title="대화 삭제" aria-label="대화 삭제">✕</button>
          </li>`;
      })
      .join("");

    el.convList.querySelectorAll(".conv-item").forEach((item) => {
      item.addEventListener("click", (event) => {
        if (event.target.closest("[data-delete]")) return;
        openConversation(item.dataset.id);
      });
      item.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openConversation(item.dataset.id);
        }
      });
    });
    el.convList.querySelectorAll("[data-delete]").forEach((button) => {
      button.addEventListener("click", async (event) => {
        event.stopPropagation();
        await removeConversation(button.dataset.delete);
      });
    });
  }

  async function openConversation(id) {
    try {
      const conversation = await api.getConversation(id);
      state.currentConversationId = id;
      el["chat-title"].textContent = conversation.title;
      el["chat-log"].innerHTML = "";
      conversation.messages.forEach((message) => {
        appendMessage(message.role === "user" ? "user" : "assistant", message.content, {
          time: message.created_at,
          quiet: true,
        });
      });
      if (!conversation.messages.length) renderWelcome();
      renderConversationList();
      el.sidebar.classList.remove("is-open");
      switchTab("chat");
      scrollChatToBottom();
      toast(`'${conversation.title}' 대화를 불러왔어요.`);
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function removeConversation(id) {
    if (!window.confirm("이 대화를 삭제할까요? 삭제 후에는 되돌릴 수 없습니다.")) return;
    try {
      await api.deleteConversation(id);
      if (state.currentConversationId === id) startNewChat();
      await loadConversations();
      toast("대화를 삭제했어요.");
    } catch (error) {
      toast(error.message, true);
    }
  }

  function startNewChat() {
    state.currentConversationId = null;
    el["chat-title"].textContent = "새 대화";
    el["chat-log"].innerHTML = "";
    renderWelcome();
    renderConversationList();
    el["chat-input"].focus();
    el.sidebar.classList.remove("is-open");
    switchTab("chat");
  }

  function renderWelcome() {
    if (el["chat-log"].children.length) return;
    const summary = state.summary;
    let context = "아직 데이터가 없어요. '데이터 관리' 탭에서 날짜와 값을 추가해 주세요.";
    if (summary && !summary.empty) {
      context =
        `현재 컨텍스트: **${summary.period.label}** · **${summary.count}건** · ${summary.trend.label}`;
    }
    appendMessage(
      "assistant",
      `안녕하세요, DataMate예요. 스터디카페 매출 데이터를 요약해 근거 있는 답변을 드립니다.\n\n${context}\n\n궁금한 점을 물어보시거나, 아래 추천 질문을 눌러 보세요.`,
      { isWelcome: true }
    );
  }

  /* -------------------------------------------------------------------- chat */
  function renderQuickChips() {
    const questions = [
      "이번 달 매출 어때?",
      "가장 매출이 좋았던 날은?",
      "주말과 주중 매출 차이는?",
      "최근 30일 추세를 요약해줘",
    ];
    el.quickRow.innerHTML = questions
      .map((question) => `<button class="chip" type="button">${escapeHtml(question)}</button>`)
      .join("");
    el.quickRow.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => sendMessage(chip.textContent));
    });
  }

  function appendMessage(role, content, options = {}) {
    const wrapper = document.createElement("div");
    wrapper.className = `msg ${role === "user" ? "user" : "assistant"}`;

    const avatar = document.createElement("span");
    avatar.className = "avatar";
    avatar.textContent = role === "user" ? "나" : "DM";

    const body = document.createElement("div");
    body.className = "bubble";
    if (role === "user") {
      body.innerHTML = escapeHtml(content).replace(/\n/g, "<br />");
    } else {
      body.innerHTML = renderMarkdown(content);
    }

    if (options.tools && options.tools.length) {
      const meta = document.createElement("div");
      meta.className = "msg-meta";
      options.tools.forEach((tool) => {
        const chip = document.createElement("span");
        chip.className = "tool-chip";
        chip.textContent = `${tool.name}${tool.ok ? "" : " 실패"}`;
        chip.title = tool.summary || "";
        meta.appendChild(chip);
      });
      if (options.latency) {
        const latency = document.createElement("span");
        latency.className = "msg-time";
        latency.textContent = `${(options.latency / 1000).toFixed(1)}초`;
        meta.appendChild(latency);
      }
      body.appendChild(meta);
    }

    if (options.time && !options.isWelcome) {
      const time = document.createElement("span");
      time.className = "msg-time";
      time.textContent = timeLabel(options.time);
      body.appendChild(time);
    }

    wrapper.append(avatar, body);
    el["chat-log"].appendChild(wrapper);
    scrollChatToBottom();
    return wrapper;
  }

  function appendTyping() {
    const wrapper = document.createElement("div");
    wrapper.className = "msg assistant";
    wrapper.innerHTML = `
      <span class="avatar">DM</span>
      <div class="bubble">
        <span class="typing" aria-label="답변 생성 중"><i></i><i></i><i></i></span>
        <span class="muted small">데이터 요약을 컨텍스트로 넣고 답변을 만드는 중…</span>
      </div>`;
    el["chat-log"].appendChild(wrapper);
    scrollChatToBottom();
    return wrapper;
  }

  function scrollChatToBottom() {
    el["chat-log"].scrollTop = el["chat-log"].scrollHeight;
  }

  async function sendMessage(rawText) {
    const message = String(rawText || "").trim();
    if (!message || state.sending) return;

    state.sending = true;
    el.sendBtn.disabled = true;
    el["chat-input"].value = "";
    autoGrow();
    appendMessage("user", message);
    const typing = appendTyping();

    try {
      const response = await api.chat({
        message,
        conversation_id: state.currentConversationId,
      });
      typing.remove();
      appendMessage("assistant", response.reply, {
        tools: response.used_tools,
        latency: response.latency_ms,
      });
      state.currentConversationId = response.conversation_id;
      if (response.summary) {
        state.summary = response.summary;
        renderSummary(response.summary);
      }
      el["chat-context"].textContent = `컨텍스트: ${response.context_note}`;
      await loadConversations();
      const current = state.conversations.find((item) => item.id === response.conversation_id);
      if (current) el["chat-title"].textContent = current.title;
      loadStatistics().catch(() => {});
      renderConversationList();
    } catch (error) {
      typing.remove();
      appendMessage("assistant", `답변을 가져오지 못했어요.\n\n**${error.message}**`);
      toast(error.message, true);
    } finally {
      state.sending = false;
      el.sendBtn.disabled = false;
      el["chat-input"].focus();
    }
  }

  /* -------------------------------------------------------------------- data */
  async function loadData() {
    const query = el.dataSearch.value.trim();
    const response = await api.listData({ limit: 60, q: query });
    state.dataItems = response.items || [];
    renderDataTable(response);
    return response;
  }

  function renderDataTable(response) {
    const items = state.dataItems;
    if (!items.length) {
      el["data-body"].innerHTML =
        '<tr><td colspan="4" class="muted" style="text-align:center; padding:28px;">조건에 맞는 데이터가 없습니다.</td></tr>';
      el.dataCount.textContent = "0건";
      return;
    }

    el.dataCount.textContent = `${response.total.toLocaleString("ko-KR")}건 중 ${items.length}건 표시 · 최신순`;

    el["data-body"].innerHTML = items
      .map((item) => {
        if (state.editingId === item.id) {
          return `
            <tr data-id="${item.id}" class="is-editing">
              <td><div class="row-edit"><input type="date" data-field="date" value="${item.date}" /></div></td>
              <td class="num"><div class="row-edit"><input type="number" data-field="value" step="1" min="1" value="${Math.round(item.value)}" /></div></td>
              <td><div class="row-edit"><input type="text" data-field="memo" maxlength="200" value="${escapeHtml(item.memo || "")}" /></div></td>
              <td>
                <div class="row-actions">
                  <button class="mini-btn" data-save="${item.id}">저장</button>
                  <button class="mini-btn" data-cancel="${item.id}">취소</button>
                </div>
              </td>
            </tr>`;
        }
        return `
          <tr data-id="${item.id}">
            <td>${item.date}</td>
            <td class="num"><strong>${won(item.value)}</strong></td>
            <td class="memo-cell">${escapeHtml(item.memo || "—")}</td>
            <td>
              <div class="row-actions">
                <button class="mini-btn" data-edit="${item.id}">수정</button>
                <button class="mini-btn danger" data-remove="${item.id}">삭제</button>
              </div>
            </td>
          </tr>`;
      })
      .join("");

    el["data-body"].querySelectorAll("[data-edit]").forEach((button) => {
      button.addEventListener("click", () => {
        state.editingId = button.dataset.edit;
        renderDataTable(response);
      });
    });
    el["data-body"].querySelectorAll("[data-cancel]").forEach((button) => {
      button.addEventListener("click", () => {
        state.editingId = null;
        renderDataTable(response);
      });
    });
    el["data-body"].querySelectorAll("[data-save]").forEach((button) => {
      button.addEventListener("click", () => saveEdit(button.dataset.save));
    });
    el["data-body"].querySelectorAll("[data-remove]").forEach((button) => {
      button.addEventListener("click", () => removeData(button.dataset.remove));
    });
  }

  async function addData(event) {
    event.preventDefault();
    const date = el["data-date"].value;
    const value = Number(el["data-value"].value);
    const memo = el["data-memo"].value.trim();

    if (!date || !Number.isFinite(value) || value <= 0) {
      toast("날짜와 0보다 큰 값을 입력해 주세요.", true);
      return;
    }

    el["data-submit"].disabled = true;
    try {
      await api.createData({ date, value, memo });
      toast(`${date} 데이터를 추가했어요.`);
      el["data-value"].value = "";
      el["data-memo"].value = "";
      await Promise.all([loadData(), loadSummary(), loadStatistics(), updateHealthChip()]);
      renderWelcomeIfEmptyChat();
    } catch (error) {
      if (error.status === 409) {
        toast(`${date} 데이터가 이미 있어요. 목록에서 '수정'을 사용해 주세요.`, true);
        el.dataSearch.value = date;
        await loadData();
      } else {
        toast(error.message, true);
      }
    } finally {
      el["data-submit"].disabled = false;
    }
  }

  async function saveEdit(id) {
    const row = el["data-body"].querySelector(`tr[data-id="${id}"]`);
    if (!row) return;
    const payload = {
      date: row.querySelector('[data-field="date"]').value,
      value: Number(row.querySelector('[data-field="value"]').value),
      memo: row.querySelector('[data-field="memo"]').value.trim(),
    };
    if (!payload.date || !Number.isFinite(payload.value) || payload.value <= 0) {
      toast("날짜와 값을 확인해 주세요.", true);
      return;
    }
    try {
      await api.updateData(id, payload);
      state.editingId = null;
      toast("데이터를 수정했어요.");
      await Promise.all([loadData(), loadSummary(), loadStatistics(), updateHealthChip()]);
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function removeData(id) {
    const item = state.dataItems.find((row) => row.id === id);
    if (!window.confirm(`${item ? item.date : "선택한"} 데이터를 삭제할까요?`)) return;
    try {
      await api.deleteData(id);
      toast("데이터를 삭제했어요.");
      await Promise.all([loadData(), loadSummary(), loadStatistics(), updateHealthChip()]);
    } catch (error) {
      toast(error.message, true);
    }
  }

  function exportData(format) {
    const anchor = document.createElement("a");
    anchor.href = api.exportUrl(format);
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    toast(`${format.toUpperCase()} 다운로드를 시작했어요.`);
  }

  function renderWelcomeIfEmptyChat() {
    if (!el["chat-log"].children.length) renderWelcome();
  }

  /* --------------------------------------------------------------- statistics */
  async function loadStatistics() {
    const statistics = await api.statistics();
    state.statistics = statistics;
    renderChart();
    renderWeekdayBars(statistics);
    renderInsightStats(statistics);
    renderMonthlyTable(statistics);
    return statistics;
  }

  function renderChart() {
    if (!window.DataMateChart || !state.statistics) return;
    if (el.trendChart.offsetParent === null) return;
    window.DataMateChart.render(el.trendChart, state.statistics.moving_average || []);
  }

  function renderWeekdayBars(statistics) {
    const rows = statistics.weekday || [];
    if (!rows.length) {
      el.weekdayBars.innerHTML = "<p class='muted small'>데이터가 없습니다.</p>";
      return;
    }
    const max = Math.max(...rows.map((row) => row.average));
    el.weekdayBars.innerHTML = rows
      .map((row) => {
        const width = max ? Math.max(4, (row.average / max) * 100) : 0;
        const peak = row.average === max ? " is-peak" : "";
        return `
          <div class="bar-row${peak}">
            <span class="muted">${row.weekday}</span>
            <span class="bar-track"><span class="bar-fill" style="width:${width}%"></span></span>
            <span class="bar-value">${compactWon(row.average)}</span>
          </div>`;
      })
      .join("");
  }

  function renderInsightStats(statistics) {
    const weekend = statistics.weekend_vs_weekday || {};
    const volatility = statistics.volatility || {};
    const growth = statistics.growth || {};
    const topMonth = (statistics.top_months || [])[0];

    el["volatility-badge"].textContent = `변동성 CV ${volatility.coefficient_of_variation ?? 0}%`;
    el.insightStats.innerHTML = `
      <li><span class="muted">주중 평균</span><span>${won(weekend.weekday_average || 0)}</span></li>
      <li><span class="muted">주말 평균</span><span>${won(weekend.weekend_average || 0)}</span></li>
      <li><span class="muted">주말 프리미엄</span><span>${Number(weekend.gap_pct || 0) >= 0 ? "+" : ""}${weekend.gap_pct ?? 0}%</span></li>
      <li><span class="muted">최근 7일 성장률</span><span>${Number(growth.change_pct || 0) >= 0 ? "+" : ""}${growth.change_pct ?? 0}%</span></li>
      <li><span class="muted">표준편차</span><span>${won(volatility.std_dev || 0)}</span></li>
      <li><span class="muted">최고 월</span><span>${topMonth ? `${topMonth.month} · ${compactWon(topMonth.average)}` : "—"}</span></li>`;
  }

  function renderMonthlyTable(statistics) {
    const rows = (statistics.monthly || []).slice(-6).reverse();
    const body = el.monthlyTable.querySelector("tbody");
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="4" class="muted">데이터가 없습니다.</td></tr>';
      return;
    }
    body.innerHTML = rows
      .map((row) => {
        const change = row.change_pct;
        const changeText = change === null || change === undefined ? "—" : `${change >= 0 ? "+" : ""}${change}%`;
        const cls = change === null || change === undefined ? "muted" : change >= 0 ? "up" : "down";
        return `<tr><td>${row.month}</td><td class="num">${won(row.average)}</td><td class="num">${compactWon(row.total)}</td><td class="num ${cls}">${changeText}</td></tr>`;
      })
      .join("");
  }
})();
