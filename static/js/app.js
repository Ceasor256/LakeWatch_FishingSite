document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("menuToggle");
  const sidebar = document.getElementById("sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", () => {
      const open = sidebar.classList.toggle("sidebar-open");
      toggle.setAttribute("aria-expanded", String(open));
    });
    // Close the mobile menu when tapping outside it.
    document.addEventListener("click", (event) => {
      if (sidebar.classList.contains("sidebar-open") && !sidebar.contains(event.target) && event.target !== toggle) {
        sidebar.classList.remove("sidebar-open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  const canvas = document.getElementById("activityChart");
  const dataNode = document.querySelector(".chart-data");
  if (canvas && dataNode) {
    const labels = (dataNode.dataset.labels || "").split(",").filter(Boolean);
    const values = (dataNode.dataset.values || "").split(",").map(v => Number(v) || 0);
    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(rect.width, 280) * ratio;
      canvas.height = 220 * ratio;
      const ctx = canvas.getContext("2d");
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      const w = Math.max(rect.width, 280), h = 220;
      const pad = {left: 30, right: 12, top: 18, bottom: 32};
      const chartW = w - pad.left - pad.right, chartH = h - pad.top - pad.bottom;
      const max = Math.max(4, ...values);
      ctx.clearRect(0, 0, w, h);
      ctx.font = "11px system-ui"; ctx.textAlign = "left"; ctx.fillStyle = "#8995a6"; ctx.strokeStyle = "#edf0f4"; ctx.lineWidth = 1;
      for (let i = 0; i <= 4; i++) {
        const y = pad.top + chartH * i / 4;
        ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(w-pad.right, y); ctx.stroke();
        ctx.fillText(String(Math.round(max * (4-i) / 4)), 3, y + 4);
      }
      const slot = chartW / Math.max(labels.length, 1);
      values.forEach((v, i) => {
        const barW = Math.min(28, slot * .52);
        const bh = chartH * v / max;
        const x = pad.left + slot * i + (slot - barW) / 2;
        const y = pad.top + chartH - bh;
        ctx.fillStyle = "#0e8c83";
        const r = Math.min(5, barW/2, bh/2);
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x, y, barW, Math.max(2, bh), r); else ctx.rect(x, y, barW, Math.max(2, bh));
        ctx.fill();
        if (v > 0) { ctx.fillStyle = "#405564"; ctx.textAlign = "center"; ctx.fillText(String(v), x + barW / 2, y - 5); }
        ctx.fillStyle = "#8995a6"; ctx.textAlign = "center";
        ctx.fillText(labels[i] || "", x + barW/2, h - 10);
      });
    };
    draw();
    window.addEventListener("resize", draw);
  }
});
