function initWalkthrough(root) {
  const tabs = [...root.querySelectorAll("[data-step]")];
  const panels = [...root.querySelectorAll("[data-panel]")];
  const label = root.querySelector("[data-step-label]");
  const prev = root.querySelector("[data-prev]");
  const next = root.querySelector("[data-next]");
  let index = 0;

  // Redrawn on every step: a chart measures its host, and a hidden panel has no width.
  function drawDemos() {
    EssayCharts.demo(root.querySelector('[data-demo="jev"]'), [["Yes", 0.71], ["No", 0.29]], COLORS.jev);
    EssayCharts.demo(root.querySelector('[data-demo="gpt"]'), [["Yes", 0.38], ["No", 0.62]], COLORS.gpt);
    EssayCharts.demo(root.querySelector('[data-demo="human"]'), [["Yes", 0], ["No", 1]], COLORS.human);
  }

  function show(nextIndex, { focusTab = false } = {}) {
    index = Math.max(0, Math.min(panels.length - 1, nextIndex));
    tabs.forEach((tab, i) => {
      tab.setAttribute("aria-selected", String(i === index));
      tab.tabIndex = i === index ? 0 : -1;
    });
    panels.forEach((panel, i) => panel.classList.toggle("is-on", i === index));
    if (label) label.textContent = `${index + 1} / ${panels.length}`;
    // A button that disables itself while focused drops focus to <body>.
    const stranded = document.activeElement;
    if (prev) prev.disabled = index === 0;
    if (next) next.disabled = index === panels.length - 1;
    if (focusTab) tabs[index].focus();
    else if (prev && stranded === prev && prev.disabled) next?.focus();
    else if (next && stranded === next && next.disabled) prev?.focus();
    drawDemos();
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => show(Number(tab.dataset.step)));
    tab.addEventListener("keydown", (event) => {
      if (event.key === "ArrowRight") show(index + 1, { focusTab: true });
      if (event.key === "ArrowLeft") show(index - 1, { focusTab: true });
    });
  });
  prev?.addEventListener("click", () => show(index - 1));
  next?.addEventListener("click", () => show(index + 1));

  show(0);
}
