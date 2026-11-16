// Citation Binder Frontend Logic - Production Foundation

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("verify-form");
  const claimInput = document.getElementById("claim-input");
  const urlInput = document.getElementById("url-input");
  const charCount = document.getElementById("char-count");
  const submitBtn = document.getElementById("submit-btn");

  const claimError = document.getElementById("claim-error");
  const urlError = document.getElementById("url-error");

  const progressCard = document.getElementById("progress-card");
  const elapsedTimer = document.getElementById("elapsed-timer");
  const resultCard = document.getElementById("result-card");
  
  const errorCard = document.getElementById("error-card");
  const errorIcon = document.getElementById("error-icon");
  const errorTitle = document.getElementById("error-title");
  const errorMessage = document.getElementById("error-message");
  const errorSetupGuide = document.getElementById("error-setup-guide");

  const verdictBadge = document.getElementById("verdict-badge");
  const verdictSublabel = document.getElementById("verdict-sublabel");
  const documentTitle = document.getElementById("document-title");
  const retrievalTime = document.getElementById("retrieval-time");
  const totalTime = document.getElementById("total-time");
  const explanationText = document.getElementById("explanation-text");
  const quoteCountBadge = document.getElementById("quote-count-badge");
  const quotesContainer = document.getElementById("quotes-container");
  const sourceLink = document.getElementById("source-link");
  const finalLink = document.getElementById("final-link");
  const redirectPill = document.getElementById("redirect-pill");
  const retrievalTimestamp = document.getElementById("retrieval-timestamp");
  const passagesCount = document.getElementById("passages-count");
  const evalProvider = document.getElementById("eval-provider");

  // Step telemetry elements
  const stepElements = [
    document.getElementById("step-ssrf"),
    document.getElementById("step-fetch"),
    document.getElementById("step-parse"),
    document.getElementById("step-assess"),
  ];

  let timerInterval = null;
  let startTime = 0;

  // Real-time character count
  claimInput.addEventListener("input", () => {
    charCount.textContent = `${claimInput.value.length} / 1000`;
    if (claimInput.value.trim().length >= 5) {
      claimError.classList.add("hidden");
    }
  });

  urlInput.addEventListener("input", () => {
    if (isValidHttpUrl(urlInput.value.trim())) {
      urlError.classList.add("hidden");
    }
  });

  // Client-side URL validator
  function isValidHttpUrl(string) {
    try {
      const u = new URL(string);
      return u.protocol === "http:" || u.protocol === "https:";
    } catch (_) {
      return false;
    }
  }

  // Quick Presets
  const presets = {
    supports: {
      claim: "The James Webb Space Telescope was launched into space on December 25, 2021.",
      url: "https://en.wikipedia.org/wiki/James_Webb_Space_Telescope"
    },
    not_supports: {
      claim: "Apollo 11 landed on the Moon in 1999.",
      url: "https://en.wikipedia.org/wiki/Apollo_11"
    },
    partially_supports: {
      claim: "Python was created by Guido van Rossum and released in 2015.",
      url: "https://en.wikipedia.org/wiki/Python_(programming_language)"
    },
    ssrf_blocked: {
      claim: "Testing AWS cloud metadata endpoint access.",
      url: "http://169.254.169.254/latest/meta-data/"
    }
  };

  document.querySelectorAll(".preset-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const pKey = btn.getAttribute("data-preset");
      const data = presets[pKey];
      if (data) {
        claimInput.value = data.claim;
        urlInput.value = data.url;
        charCount.textContent = `${data.claim.length} / 1000`;
        claimError.classList.add("hidden");
        urlError.classList.add("hidden");
        form.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });

  function startProgress() {
    progressCard.classList.remove("hidden");
    resultCard.classList.add("hidden");
    errorCard.classList.add("hidden");
    errorSetupGuide.classList.add("hidden");
    submitBtn.disabled = true;

    startTime = Date.now();
    elapsedTimer.textContent = "0.0s elapsed";

    stepElements.forEach((el, idx) => {
      el.className = "p-2.5 rounded-xl border border-slate-200 bg-slate-50 transition flex items-center gap-2";
      const icon = el.querySelector(".step-num");
      icon.className = "step-num w-5 h-5 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center font-mono text-[10px] font-bold";
      icon.textContent = String(idx + 1);
    });

    function setStepActive(idx) {
      if (idx < stepElements.length) {
        const el = stepElements[idx];
        el.className = "p-2.5 rounded-xl border border-brand-400 bg-brand-50 transition flex items-center gap-2";
        const icon = el.querySelector(".step-num");
        icon.className = "step-num w-5 h-5 rounded-full bg-brand-600 text-white flex items-center justify-center font-mono text-[10px] font-bold animate-pulse";
      }
    }

    setStepActive(0);
    setTimeout(() => setStepActive(1), 300);
    setTimeout(() => setStepActive(2), 700);
    setTimeout(() => setStepActive(3), 1100);

    timerInterval = setInterval(() => {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      elapsedTimer.textContent = `${elapsed}s elapsed`;
    }, 100);
  }

  function stopProgress() {
    clearInterval(timerInterval);
    progressCard.classList.add("hidden");
    submitBtn.disabled = false;
  }

  // Non-color reliant Verdict rendering with prominent textual symbols and accessibility labels
  function renderVerdict(verdict) {
    const v = String(verdict).toLowerCase().trim();
    verdictBadge.className = "inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl border-2 font-black text-sm tracking-wide uppercase shadow-xs";

    if (v === "supports") {
      verdictBadge.classList.add("bg-emerald-50", "text-emerald-900", "border-emerald-500");
      verdictBadge.innerHTML = `
        <span class="font-mono text-base font-black text-emerald-700" aria-hidden="true">[✓]</span>
        <span>Supports</span>
      `;
      verdictSublabel.textContent = "Direct Factual Entailment (Corroborated)";
      verdictSublabel.className = "text-xs font-semibold px-2.5 py-1 rounded-lg bg-emerald-100/70 text-emerald-900 border border-emerald-300";

    } else if (v === "partially supports") {
      verdictBadge.classList.add("bg-amber-50", "text-amber-950", "border-amber-500");
      verdictBadge.innerHTML = `
        <span class="font-mono text-base font-black text-amber-700" aria-hidden="true">[~]</span>
        <span>Partially Supports</span>
      `;
      verdictSublabel.textContent = "Partial Corroboration (Unverified Details or Qualifications)";
      verdictSublabel.className = "text-xs font-semibold px-2.5 py-1 rounded-lg bg-amber-100/70 text-amber-900 border border-amber-300";

    } else if (v === "does not support") {
      verdictBadge.classList.add("bg-rose-50", "text-rose-950", "border-rose-500");
      verdictBadge.innerHTML = `
        <span class="font-mono text-base font-black text-rose-700" aria-hidden="true">[✕]</span>
        <span>Does Not Support</span>
      `;
      verdictSublabel.textContent = "Direct Factual Contradiction (Refuted by Source)";
      verdictSublabel.className = "text-xs font-semibold px-2.5 py-1 rounded-lg bg-rose-100/70 text-rose-900 border border-rose-300";

    } else {
      // Default: unable to verify
      verdictBadge.classList.add("bg-slate-100", "text-slate-900", "border-slate-500");
      verdictBadge.innerHTML = `
        <span class="font-mono text-base font-black text-slate-700" aria-hidden="true">[?]</span>
        <span>Unable To Verify</span>
      `;
      verdictSublabel.textContent = "Inconclusive (Missing or Insufficient Evidence in Source)";
      verdictSublabel.className = "text-xs font-semibold px-2.5 py-1 rounded-lg bg-slate-200/80 text-slate-800 border border-slate-300";
    }
  }

  function renderEvidenceQuotes(quotes, verified) {
    quotesContainer.innerHTML = "";
    quoteCountBadge.textContent = String(quotes.length);

    if (!quotes || quotes.length === 0) {
      quotesContainer.innerHTML = `
        <div class="p-4 rounded-xl border border-dashed border-slate-300 text-slate-500 text-xs italic bg-slate-50 text-center">
          No verbatim passages directly substantiating or refuting this claim were extracted from the source text.
        </div>
      `;
      return;
    }

    quotes.forEach((q, idx) => {
      const qDiv = document.createElement("div");
      qDiv.className = "p-3 rounded-xl border border-slate-200 bg-white shadow-2xs space-y-1.5 transition hover:border-slate-300";

      const pos = (verified && verified[idx] && verified[idx].character_start !== null && verified[idx].character_start !== undefined)
        ? `<span class="text-[10px] font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded">Char offset: ${verified[idx].character_start}-${verified[idx].character_end}</span>`
        : "";

      qDiv.innerHTML = `
        <div class="flex flex-wrap items-center justify-between gap-1 text-xs">
          <span class="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-300">
            <span class="font-mono font-black" aria-hidden="true">[✓]</span>
            Verbatim Source Match
          </span>
          ${pos}
        </div>
        <blockquote class="text-xs text-slate-800 leading-relaxed pl-2.5 border-l-2 border-brand-500 italic break-words">
          "${escapeHtml(q)}"
        </blockquote>
      `;
      quotesContainer.appendChild(qDiv);
    });
  }

  function showError(category, title, msg, isSetup = false) {
    errorCard.classList.remove("hidden");
    errorSetupGuide.classList.toggle("hidden", !isSetup);

    if (category === "ssrf") {
      errorCard.className = "rounded-2xl border-2 border-purple-400 bg-purple-50 p-5 shadow-sm space-y-2 text-purple-950";
      errorIcon.textContent = "[!]";
      errorIcon.className = "text-purple-700 font-mono font-black text-lg";
      errorTitle.textContent = title || "Security Rejection (SSRF Guard)";
    } else if (category === "unsupported") {
      errorCard.className = "rounded-2xl border-2 border-amber-400 bg-amber-50 p-5 shadow-sm space-y-2 text-amber-950";
      errorIcon.textContent = "[~]";
      errorIcon.className = "text-amber-700 font-mono font-black text-lg";
      errorTitle.textContent = title || "Unsupported Source Format";
    } else if (category === "setup") {
      errorCard.className = "rounded-2xl border-2 border-blue-400 bg-blue-50 p-5 shadow-sm space-y-2 text-blue-950";
      errorIcon.textContent = "[i]";
      errorIcon.className = "text-blue-700 font-mono font-black text-lg";
      errorTitle.textContent = title || "Server Model Setup Required";
    } else {
      errorCard.className = "rounded-2xl border-2 border-rose-400 bg-rose-50 p-5 shadow-sm space-y-2 text-rose-950";
      errorIcon.textContent = "[✕]";
      errorIcon.className = "text-rose-700 font-mono font-black text-lg";
      errorTitle.textContent = title || "Verification Request Failed";
    }

    errorMessage.textContent = msg;
    errorCard.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function escapeHtml(text) {
    if (!text) return "";
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Form submission handler
  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const claim = claimInput.value.trim();
    const url = urlInput.value.trim();

    let hasValidationError = false;
    if (claim.length < 5) {
      claimError.classList.remove("hidden");
      hasValidationError = true;
    }
    if (!isValidHttpUrl(url)) {
      urlError.classList.remove("hidden");
      hasValidationError = true;
    }
    if (hasValidationError) return;

    startProgress();

    try {
      const response = await fetch("/api/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ claim, url }),
      });

      const data = await response.json();

      if (!response.ok) {
        // Handle categorized HTTP errors
        if (response.status === 400 && String(data.detail).includes("SSRF")) {
          showError("ssrf", "Access Blocked by SSRF Protection", data.detail);
        } else if (response.status === 415) {
          showError("unsupported", "Unsupported Source Format", data.detail);
        } else {
          showError("generic", "Verification Failed", data.detail || `Server returned error status ${response.status}`);
        }
        stopProgress();
        return;
      }

      // Check if explanation indicates server model setup requirement
      if (data.verdict === "unable to verify" && String(data.explanation).includes("Setup Required")) {
        showError("setup", "Model Credentials Setup Required", data.explanation, true);
        stopProgress();
        return;
      }

      // Populate Result Dossier
      renderVerdict(data.verdict);
      documentTitle.textContent = data.page_title || "Retrieved Source Document";
      retrievalTime.textContent = `${data.retrieval_time_ms} ms`;
      totalTime.textContent = `${data.total_processing_time_ms} ms`;
      explanationText.textContent = data.explanation;

      renderEvidenceQuotes(data.evidence_passages || data.quoted_evidence || [], data.verified_quotes || []);

      // Safe Provenance URLs (protocol whitelist defense against javascript: / data: URI injection)
      function setSafeLink(element, rawUrl) {
        element.textContent = rawUrl || "--";
        if (rawUrl && (rawUrl.startsWith("http://") || rawUrl.startsWith("https://"))) {
          element.href = rawUrl;
        } else {
          element.href = "#";
        }
      }
      setSafeLink(sourceLink, data.source_link);
      setSafeLink(finalLink, data.final_url);

      if (data.redirect_count > 0 || data.source_link !== data.final_url) {
        redirectPill.classList.remove("hidden");
        redirectPill.textContent = `${data.redirect_count} redirect${data.redirect_count > 1 ? "s" : ""}`;
      } else {
        redirectPill.classList.add("hidden");
      }

      retrievalTimestamp.textContent = new Date(data.retrieval_timestamp).toLocaleString();
      passagesCount.textContent = `${data.passages_analyzed || 0} passages`;
      evalProvider.textContent = `${data.provider || "engine"} (${data.model || "v1"})`;

      stopProgress();
      resultCard.classList.remove("hidden");
      resultCard.scrollIntoView({ behavior: "smooth", block: "start" });

    } catch (err) {
      stopProgress();
      showError("generic", "Network Connection Error", err.message || "Failed to contact the Citation Binder verification server.");
    }
  });
});
