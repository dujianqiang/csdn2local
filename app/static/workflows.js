"use strict";

for (const select of document.querySelectorAll("select[data-submit-on-change]")) {
  select.addEventListener("change", () => select.form.requestSubmit());
}

for (const formats of document.querySelectorAll("[data-format-options]")) {
  const pdf = formats.querySelector('input[value="pdf"]');
  const hint = formats.querySelector("#pdf-runtime-help");
  const updateHint = () => { hint.hidden = !pdf.checked; };
  formats.addEventListener("change", updateHint);
  window.addEventListener("pageshow", updateHint);
  updateHint();
}

const articleLimit = document.getElementById("article-limit");
if (articleLimit) {
  const presets = [...document.querySelectorAll("[data-article-limit]")];
  const syncPresets = () => {
    for (const button of presets) {
      button.setAttribute("aria-pressed", String(articleLimit.valueAsNumber === Number(button.dataset.articleLimit)));
    }
  };
  for (const button of presets) {
    button.addEventListener("click", () => {
      articleLimit.value = button.dataset.articleLimit;
      syncPresets();
    });
  }
  articleLimit.addEventListener("input", syncPresets);
  window.addEventListener("pageshow", syncPresets);
  document.querySelector(".limit-presets").hidden = false;
  syncPresets();
}

const failedFilter = document.querySelector("[data-failed-filter]");
if (failedFilter) {
  const completed = document.querySelectorAll('[data-article-status="success"]');
  const applyFilter = () => {
    for (const article of completed) article.hidden = failedFilter.checked;
  };
  failedFilter.addEventListener("change", applyFilter);
  window.addEventListener("pageshow", applyFilter);
  failedFilter.closest("label").hidden = false;
  applyFilter();
}

for (const form of document.querySelectorAll("form[data-pending]")) {
  const buttons = Array.from(form.elements).filter((element) => element.matches('button[type="submit"]'));
  const feedback = form.querySelector(".submit-feedback");
  let pendingButton;
  let label;
  form.addEventListener("submit", (event) => {
    if (form.getAttribute("aria-busy") === "true") {
      event.preventDefault();
      return;
    }
    form.setAttribute("aria-busy", "true");
    pendingButton = event.submitter;
    if (pendingButton) {
      label = pendingButton.textContent;
      for (const button of buttons) button.setAttribute("aria-disabled", "true");
      pendingButton.textContent = form.dataset.pending;
    }
    if (feedback) feedback.textContent = "请稍候。";
  });
  window.addEventListener("pageshow", () => {
    form.removeAttribute("aria-busy");
    for (const button of buttons) button.removeAttribute("aria-disabled");
    if (pendingButton) pendingButton.textContent = label;
    pendingButton = null;
    if (feedback) feedback.textContent = "";
  });
}

const retrySelected = document.querySelector("[data-retry-selected]");
if (retrySelected) {
  const choices = Array.from(retrySelected.form.elements).filter((element) => element.name === "positions");
  const syncRetrySelection = () => {
    const count = choices.filter((input) => input.checked).length;
    retrySelected.disabled = count === 0;
    retrySelected.textContent = count ? `批量重试（${count}）` : "批量重试";
  };
  for (const choice of choices) choice.addEventListener("change", syncRetrySelection);
  window.addEventListener("pageshow", syncRetrySelection);
  syncRetrySelection();
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
  const steps = panel.querySelectorAll("[data-stage-step]");
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
      if (label && stage.textContent !== label) {
        stage.textContent = label;
        for (const step of steps) {
          if (step.dataset.stageStep === status.stage) step.setAttribute("aria-current", "step");
          else step.removeAttribute("aria-current");
        }
      }
      counts.hidden = !status.total;
      if (status.stage === "downloading" && status.total) {
        meter.max = status.total;
        meter.value = status.processed;
      } else {
        meter.removeAttribute("value");
      }
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
