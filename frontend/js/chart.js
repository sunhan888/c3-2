/* 의존성 없는 Canvas 라인 차트 (일별 값 + 7일 이동평균) */
(function () {
  function cssVar(name, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  }

  function formatCompact(value) {
    if (value >= 100000000) return `${(value / 100000000).toFixed(1)}억`;
    if (value >= 10000) return `${Math.round(value / 10000)}만`;
    return String(Math.round(value));
  }

  function formatDay(iso) {
    const text = String(iso).slice(5);
    return text.replace("-", "/");
  }

  function render(canvas, points) {
    if (!canvas) return;
    const data = Array.isArray(points) ? points : [];
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(rect.width || canvas.parentElement.clientWidth || 640, 0);
    // bitmap 크기(width/height 속성)가 아니라 CSS 픽셀 크기를 기준으로 계산해야
    // 재렌더링 때마다 캔버스가 devicePixelRatio만큼 커지는 문제를 막을 수 있다.
    const height = canvas.clientHeight || 300;
    const dpr = window.devicePixelRatio || 1;
    if (width < 40) return;

    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const accent = cssVar("--accent", "#4f46e5");
    const border = cssVar("--border", "#e5e7f0");
    const muted = cssVar("--muted", "#6b7280");
    const surface = cssVar("--surface", "#ffffff");

    if (!data.length) {
      ctx.fillStyle = muted;
      ctx.font = `13px ${cssVar("--mono", "monospace")}`;
      ctx.fillText("표시할 데이터가 없습니다.", 20, height / 2);
      return;
    }

    const padding = { top: 18, right: 16, bottom: 30, left: 54 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;

    const values = data.flatMap((item) => [item.value, item.ma7]).filter((v) => Number.isFinite(v));
    const rawMin = Math.min(...values);
    const rawMax = Math.max(...values);
    const span = Math.max(rawMax - rawMin, 1);
    const min = rawMin - span * 0.12;
    const max = rawMax + span * 0.12;

    const x = (index) => padding.left + (data.length === 1 ? plotWidth / 2 : (plotWidth * index) / (data.length - 1));
    const y = (value) => padding.top + plotHeight - ((value - min) / (max - min)) * plotHeight;

    // 그리드 + y축 라벨
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    ctx.font = `11px ${cssVar("--mono", "monospace")}`;
    ctx.fillStyle = muted;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    const gridCount = 4;
    for (let index = 0; index <= gridCount; index += 1) {
      const value = min + ((max - min) * index) / gridCount;
      const py = y(value);
      ctx.beginPath();
      ctx.moveTo(padding.left, py);
      ctx.lineTo(width - padding.right, py);
      ctx.stroke();
      ctx.fillText(formatCompact(value), padding.left - 10, py);
    }

    // x축 라벨
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const step = Math.max(1, Math.ceil(data.length / 6));
    for (let index = 0; index < data.length; index += step) {
      ctx.fillText(formatDay(data[index].date), x(index), height - padding.bottom + 10);
    }

    // 일별 영역
    const gradient = ctx.createLinearGradient(0, padding.top, 0, height - padding.bottom);
    gradient.addColorStop(0, hexToRgba(accent, 0.28));
    gradient.addColorStop(1, hexToRgba(accent, 0.02));
    ctx.beginPath();
    data.forEach((item, index) => {
      const px = x(index);
      const py = y(item.value);
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.lineTo(x(data.length - 1), height - padding.bottom);
    ctx.lineTo(x(0), height - padding.bottom);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // 일별 라인
    ctx.beginPath();
    data.forEach((item, index) => {
      const px = x(index);
      const py = y(item.value);
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.strokeStyle = accent;
    ctx.lineWidth = 1.6;
    ctx.globalAlpha = 0.85;
    ctx.stroke();
    ctx.globalAlpha = 1;

    // 7일 이동평균
    ctx.beginPath();
    data.forEach((item, index) => {
      const px = x(index);
      const py = y(item.ma7 ?? item.value);
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.strokeStyle = "#f59e0b";
    ctx.lineWidth = 2.6;
    ctx.lineJoin = "round";
    ctx.stroke();

    // 마지막 지점 강조
    const last = data[data.length - 1];
    ctx.beginPath();
    ctx.arc(x(data.length - 1), y(last.value), 4, 0, Math.PI * 2);
    ctx.fillStyle = accent;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x(data.length - 1), y(last.value), 7, 0, Math.PI * 2);
    ctx.strokeStyle = hexToRgba(accent, 0.3);
    ctx.lineWidth = 3;
    ctx.stroke();

    // 마지막 값 라벨
    const label = `${Math.round(last.value).toLocaleString("ko-KR")}원`;
    ctx.font = `600 11px ${cssVar("--mono", "monospace")}`;
    const textWidth = ctx.measureText(label).width;
    const labelX = Math.min(x(data.length - 1) - textWidth - 6, width - padding.right - textWidth - 6);
    const labelY = Math.max(y(last.value) - 22, padding.top + 2);
    ctx.fillStyle = surface;
    roundRect(ctx, labelX - 6, labelY - 4, textWidth + 12, 20, 6);
    ctx.fill();
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = accent;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(label, labelX, labelY + 6);
  }

  function roundRect(ctx, x, y, width, height, radius) {
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.arcTo(x + width, y, x + width, y + height, radius);
    ctx.arcTo(x + width, y + height, x, y + height, radius);
    ctx.arcTo(x, y + height, x, y, radius);
    ctx.arcTo(x, y, x + width, y, radius);
    ctx.closePath();
  }

  function hexToRgba(hex, alpha) {
    const value = hex.replace("#", "").trim();
    if (value.length !== 6) return `rgba(79, 70, 229, ${alpha})`;
    const r = parseInt(value.slice(0, 2), 16);
    const g = parseInt(value.slice(2, 4), 16);
    const b = parseInt(value.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  window.DataMateChart = { render };
})();
