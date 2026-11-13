"use strict";

for (const select of document.querySelectorAll("select[data-submit-on-change]")) {
  select.addEventListener("change", () => select.form.requestSubmit());
}

for (const form of document.querySelectorAll("form[data-pending]")) {
  const button = form.querySelector('button[type="submit"]');
  const feedback = form.querySelector(".submit-feedback");
  const label = button.textContent;
  form.addEventListener("submit", (event) => {
    if (button.disabled) {
      event.preventDefault();
      return;
    }
    button.disabled = true;
    button.textContent = form.dataset.pending;
    if (feedback) feedback.textContent = "请稍候。";
  });
  window.addEventListener("pageshow", () => {
    button.disabled = false;
    button.textContent = label;
    if (feedback) feedback.textContent = "";
  });
}

const panel = document.querySelector("[data-progress-url]");
if (panel) {
  const stage = document.getElementById("stage-title");
  const meter = document.getElementById("topic-meter");
  const counts = document.getElementById("topic-counts");
  const count = document.getElementById("topic-count");
  const failed = document.getElementById("topic-failed");
  const elapsed = document.getElementById("topic-elapsed");
  const preview = document.getElementById("topic-preview");
  const connection = document.getElementById("topic-connection");
  const stages = {
    discovering: "正在读取专题目录",
    downloading: "正在下载文章",
    exporting: `正在生成 ${panel.dataset.format}`,
  };

  async function poll() {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(panel.dataset.progressUrl, { signal: controller.signal });
      if (response.status === 404) {
        window.location.replace(panel.dataset.jobUrl);
        return;
      }
      if (!response.ok) throw new Error("Progress unavailable");
      const status = await response.json();
      if (status.finished) {
        window.location.replace(panel.dataset.jobUrl);
        return;
      }
      connection.hidden = true;
      const label = stages[status.stage];
      if (label && stage.textContent !== label) stage.textContent = label;
      meter.hidden = counts.hidden = !status.total;
      meter.max = status.total || 1;
      meter.value = status.processed;
      count.textContent = `${status.processed} / ${status.total}`;
      failed.textContent = status.failed;
      elapsed.textContent = `${status.elapsed} 秒`;
      preview.hidden = status.discovered_total <= status.total;
      if (!preview.hidden) {
        preview.textContent = `专题共 ${status.discovered_total} 篇，本次只处理前 ${status.total} 篇。`;
      }
    } catch {
      connection.hidden = false;
    } finally {
      window.clearTimeout(timeout);
    }
    window.setTimeout(poll, 1500);
  }

  window.setTimeout(poll, 1500);
}
