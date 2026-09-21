function observeSections() {
  const links = [...document.querySelectorAll(".rail a[data-section]")];
  const sections = links
    .map((link) => document.getElementById(link.dataset.section))
    .filter(Boolean);

  const io = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      links.forEach((link) => {
        link.classList.toggle("is-on", link.dataset.section === visible.target.id);
      });
    },
    { rootMargin: "-30% 0px -50% 0px", threshold: [0.1, 0.4, 0.7] },
  );
  sections.forEach((section) => io.observe(section));
}

function resizeCharts(draw) {
  let timer = 0;
  window.addEventListener("resize", () => {
    clearTimeout(timer);
    timer = setTimeout(draw, 150);
  });
}

async function main() {
  observeSections();
  const walk = document.querySelector("[data-walkthrough]");
  if (walk) initWalkthrough(walk);

  let figures;
  try {
    const response = await fetch("data/figures.json");
    if (!response.ok) throw new Error(response.statusText);
    figures = await response.json();
  } catch (error) {
    document.querySelectorAll(".chart").forEach((node) => {
      node.textContent = "Figures failed to load. Serve this folder over HTTP so data/figures.json can be fetched.";
    });
    console.error(error);
    return;
  }

  const draw = () => {
    EssayCharts.floors(document.getElementById("chart-floors"), figures);
    EssayCharts.panel(document.getElementById("chart-panel"), figures);
    EssayCharts.comparison(document.getElementById("chart-comparison"), figures);
    EssayCharts.noul(document.getElementById("chart-noul"), figures);
    EssayCharts.grounding(document.getElementById("chart-grounding"), figures);
    EssayCharts.segments(document.getElementById("chart-segments"), figures);
    EssayCharts.economics(document.getElementById("chart-economics"), figures);
    EssayCharts.price(document.getElementById("chart-price"), figures);
  };
  draw();
  resizeCharts(draw);
}

document.addEventListener("DOMContentLoaded", main);
