const STEPS = [
  ["scrape", "Scrape source"],
  ["summarize", "Summarize"],
  ["seo_research", "SEO research"],
  ["brief", "Build brief"],
  ["writer", "Write draft"],
  ["critic", "Critique"],
  ["repurposer", "Repurpose social"],
  ["image", "Find image"],
  ["assembler", "Assemble package"],
];

const form = document.getElementById("generate-form");
const submitBtn = document.getElementById("submit-btn");
const statusPanel = document.getElementById("status-panel");
const statusTitle = document.getElementById("status-title");
const runIdEl = document.getElementById("run-id");
const liveSteps = document.getElementById("live-steps");
const statusNote = document.getElementById("status-note");
const errorBanner = document.getElementById("error-banner");
const results = document.getElementById("results");

function buildLiveSteps() {
  liveSteps.innerHTML = STEPS.map(
    ([id, label]) =>
      `<li data-step="${id}"><span class="dot" aria-hidden="true"></span>${label}</li>`
  ).join("");
}

function setStepStates(progress) {
  const doneMap = progress?.steps || {};
  const current = progress?.current_step;
  for (const li of liveSteps.querySelectorAll("li")) {
    const id = li.dataset.step;
    li.classList.remove("done", "active");
    if (doneMap[id]) li.classList.add("done");
    if (current === id) li.classList.add("active");
  }
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((btn) => {
    const on = btn.dataset.tab === name;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    const on = panel.dataset.panel === name;
    panel.classList.toggle("active", on);
    panel.hidden = !on;
  });
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

async function pollStatus(runId) {
  const res = await fetch(`/status/${runId}`);
  if (!res.ok) throw new Error(`Status check failed (${res.status})`);
  return res.json();
}

function renderResults(payload) {
  const pkg = payload.result;
  if (!pkg) {
    errorBanner.hidden = false;
    errorBanner.textContent = "Run finished without a package.";
    return;
  }

  results.hidden = false;
  document.getElementById("article-title").textContent = pkg.article.title;
  document.getElementById("article-meta").textContent =
    `${pkg.article.word_count} words · meta: ${pkg.article.meta_description}`;
  document.getElementById("cost-chip").textContent =
    `$${pkg.cost.total_usd.toFixed(4)} · ${pkg.cost.total_tokens.toLocaleString()} tokens`;

  document.getElementById("article-body").textContent = pkg.article.body_markdown;

  const twitter = document.getElementById("twitter-body");
  twitter.innerHTML = pkg.social.twitter_thread
    .map((t) => `<div class="tweet">${escapeHtml(t)}</div>`)
    .join("");

  document.getElementById("linkedin-body").textContent = pkg.social.linkedin_post;
  document.getElementById("email-body").textContent = pkg.social.email_newsletter_snippet;

  const critique = pkg.seo_critique;
  const issues =
    critique.issues?.length
      ? `<ul>${critique.issues.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>`
      : "<p>No blocking issues.</p>";
  document.getElementById("critique-body").innerHTML = `
    <div class="score">${(critique.score * 100).toFixed(0)}% · ${critique.passed ? "Passed" : "Below threshold"}</div>
    <p>Keyword: ${critique.keyword_coverage_ok ? "ok" : "needs work"} ·
       Headings: ${critique.heading_coverage_ok ? "ok" : "needs work"} ·
       Length: ${critique.length_ok ? "ok" : "needs work"}</p>
    ${issues}
  `;

  const imageWrap = document.getElementById("result-image");
  const img = document.getElementById("result-img");
  if (pkg.image?.url) {
    imageWrap.hidden = false;
    img.alt = pkg.image.alt_text || "";
    img.src = pkg.image.url;
    // Prefer a locally exported file when available (extension varies).
    fetch(`/runs/${pkg.run_id}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((saved) => {
        const local = saved?.files?.find((f) => f.startsWith("image."));
        if (local) img.src = `/outputs/${pkg.run_id}/${local}`;
      })
      .catch(() => {});
    document.getElementById("image-credit").innerHTML =
      `Photo by <a href="${pkg.image.photographer_url}" target="_blank" rel="noopener">${escapeHtml(pkg.image.photographer)}</a> on Pexels`;
  } else {
    imageWrap.hidden = true;
  }

  switchTab("article");
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBanner.hidden = true;
  results.hidden = true;

  const source_url = document.getElementById("source_url").value.trim() || null;
  const raw_text = document.getElementById("raw_text").value.trim() || null;
  const target_keyword = document.getElementById("target_keyword").value.trim();
  const brand_voice = document.getElementById("brand_voice").value.trim();

  if (!source_url && !raw_text) {
    errorBanner.hidden = false;
    errorBanner.textContent = "Provide a source URL or paste raw text.";
    statusPanel.hidden = false;
    return;
  }

  buildLiveSteps();
  statusPanel.hidden = false;
  statusTitle.textContent = "Running";
  statusNote.textContent = "Kickoff sent — waiting for the first agent…";
  submitBtn.disabled = true;

  try {
    const res = await fetch("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_url, raw_text, target_keyword, brand_voice }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Generate failed (${res.status})`);
    }
    const { run_id } = await res.json();
    runIdEl.textContent = run_id;

    while (true) {
      const data = await pollStatus(run_id);
      if (data.progress) setStepStates(data.progress);

      if (data.status === "running") {
        const step = data.progress?.current_step;
        statusNote.textContent = step
          ? `Current hop: ${step.replaceAll("_", " ")}`
          : "Agents are working…";
        await new Promise((r) => setTimeout(r, 1200));
        continue;
      }

      if (data.status === "failed") {
        statusTitle.textContent = "Failed";
        statusNote.textContent = "";
        errorBanner.hidden = false;
        errorBanner.textContent = data.error || "Pipeline failed.";
        break;
      }

      statusTitle.textContent = "Done";
      statusNote.textContent = data.output_folder
        ? `Saved to ${data.output_folder}`
        : "Package ready.";
      renderResults(data);
      break;
    }
  } catch (err) {
    statusTitle.textContent = "Failed";
    errorBanner.hidden = false;
    errorBanner.textContent = err.message || String(err);
  } finally {
    submitBtn.disabled = false;
  }
});

buildLiveSteps();
