function initWalkthrough(root) {
  const tabs = [...root.querySelectorAll("[data-step]")];
  const panels = [...root.querySelectorAll("[data-panel]")];
  const label = root.querySelector("[data-step-label]");
  const prev = root.querySelector("[data-prev]");
  const next = root.querySelector("[data-next]");
  let index = 0;

  function show(nextIndex) {
    index = Math.max(0, Math.min(panels.length - 1, nextIndex));
    tabs.forEach((tab, i) => tab.setAttribute("aria-selected", String(i === index)));
    panels.forEach((panel, i) => panel.classList.toggle("is-on", i === index));
    if (label) label.textContent = `${index + 1} / ${panels.length}`;
    if (prev) prev.disabled = index === 0;
    if (next) next.disabled = index === panels.length - 1;
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => show(Number(tab.dataset.step)));
  });
  prev?.addEventListener("click", () => show(index - 1));
  next?.addEventListener("click", () => show(index + 1));
  root.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight") show(index + 1);
    if (event.key === "ArrowLeft") show(index - 1);
  });

  EssayCharts.demo(root.querySelector('[data-demo="jev"]'), [
    ["Yes", 0.71],
    ["No", 0.29],
  ], "#c63b22");
  EssayCharts.demo(root.querySelector('[data-demo="gpt"]'), [
    ["Yes", 0.38],
    ["No", 0.62],
  ], "#2a5d6e");
  EssayCharts.demo(root.querySelector('[data-demo="human"]'), [
    ["Yes", 0],
    ["No", 1],
  ], "#2f5d3a");

  show(0);
}
