/* ===== DOM REFERENCES ===== */
const form = document.getElementById("job-form");
const submitButton = document.getElementById("submit-button");
const formMessage = document.getElementById("form-message");
const submitGuard = document.getElementById("submit-guard");
const jobTitle = document.getElementById("job-title");
const jobBadge = document.getElementById("job-badge");
const jobProgress = document.getElementById("job-progress");
const jobEnhanced = document.getElementById("job-enhanced");
const jobError = document.getElementById("job-error");
const jobErrorMeta = document.getElementById("job-error-meta");
const warningsList = document.getElementById("warnings-list");
const resultContainer = document.getElementById("result-container");
const previewVideo = document.getElementById("preview-video");
const downloadLink = document.getElementById("download-link");
const healthBadge = document.getElementById("health-badge");
const externalSummary = document.getElementById("external-summary");
const runtimeNote = document.getElementById("runtime-note");
const healthList = document.getElementById("health-list");
const modelSelect = document.getElementById("video-model-select");
const modelHint = document.getElementById("model-hint");

let pollHandle = null;
let isProcessing = false;
let externalReady = false;

/* ===== REFERENCE IMAGE STATE ===== */
const referenceFiles = {
  embalagem: null,
  logo: null,
  cores: null,
};

const REF_TYPES = ["embalagem", "logo", "cores"];

/* ===== MODEL HINTS ===== */
const MODEL_HINTS = {
  seedance_1_5_pro: "Kling 2.1 Padrão: qualidade equilibrada. Unico modelo disponivel na sua conta.",
  kling_3_0: "Kling 2.1 Realista: mesmo modelo base com tier diferente. Unico disponivel.",
  veo_3_1: "Kling 2.1 Profissional: mesmo modelo base com tier diferente. Unico disponivel.",
};

if (modelSelect) {
  modelSelect.addEventListener("change", () => {
    if (modelHint) {
      modelHint.textContent = MODEL_HINTS[modelSelect.value] || "";
    }
  });
}

/* ===== REFERENCE IMAGE UPLOAD ===== */
function initReferenceUploads() {
  REF_TYPES.forEach((type) => {
    const dropZone = document.getElementById(`drop-${type}`);
    const fileInput = document.getElementById(`file-${type}`);
    const preview = document.getElementById(`preview-${type}`);
    const removeBtn = document.getElementById(`remove-${type}`);

    if (!dropZone || !fileInput || !preview) return;

    // Click to upload
    dropZone.addEventListener("click", (e) => {
      if (e.target === removeBtn || e.target.closest(".ref-remove")) return;
      fileInput.click();
    });

    // File input change
    fileInput.addEventListener("change", () => {
      if (fileInput.files && fileInput.files[0]) {
        handleRefFile(type, fileInput.files[0]);
      }
    });

    // Drag events
    dropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropZone.classList.add("drag-over");
    });

    dropZone.addEventListener("dragleave", () => {
      dropZone.classList.remove("drag-over");
    });

    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("drag-over");
      const file = e.dataTransfer.files[0];
      if (file && file.type.startsWith("image/")) {
        handleRefFile(type, file);
      }
    });

    // Remove button
    if (removeBtn) {
      removeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        clearRefImage(type);
      });
    }
  });
}

function handleRefFile(type, file) {
  referenceFiles[type] = file;

  const dropZone = document.getElementById(`drop-${type}`);
  const preview = document.getElementById(`preview-${type}`);
  const removeBtn = document.getElementById(`remove-${type}`);
  const placeholder = dropZone.querySelector(".ref-placeholder");

  const url = URL.createObjectURL(file);
  preview.src = url;
  preview.classList.remove("hidden");
  if (removeBtn) removeBtn.classList.remove("hidden");
  if (placeholder) placeholder.classList.add("hidden");
  dropZone.classList.add("has-image");
}

function clearRefImage(type) {
  referenceFiles[type] = null;

  const dropZone = document.getElementById(`drop-${type}`);
  const preview = document.getElementById(`preview-${type}`);
  const removeBtn = document.getElementById(`remove-${type}`);
  const fileInput = document.getElementById(`file-${type}`);
  const placeholder = dropZone.querySelector(".ref-placeholder");

  if (preview.src) URL.revokeObjectURL(preview.src);
  preview.src = "";
  preview.classList.add("hidden");
  if (removeBtn) removeBtn.classList.add("hidden");
  if (placeholder) placeholder.classList.remove("hidden");
  dropZone.classList.remove("has-image");
  if (fileInput) fileInput.value = "";
}

/* ===== SERVICE LABELS ===== */
const serviceLabels = {
  ffmpeg: "FFmpeg",
  openai: "OpenAI",
  higgsfield_auth: "Higgsfield",
  elevenlabs: "ElevenLabs",
};

/* ===== UI STATE ===== */
function updateSubmitState() {
  submitButton.disabled = isProcessing || !externalReady;
}

function resetResult() {
  resultContainer.classList.add("hidden");
  previewVideo.removeAttribute("src");
  previewVideo.load();
  downloadLink.setAttribute("href", "#");
}

function setWarnings(warnings) {
  warningsList.innerHTML = "";
  if (!warnings || warnings.length === 0) {
    return;
  }

  warnings.forEach((warning) => {
    const item = document.createElement("li");
    item.textContent = warning;
    warningsList.appendChild(item);
  });
}

/* ===== HEALTH CHECK ===== */
function renderHealthServices(services) {
  healthList.innerHTML = "";

  Object.entries(services).forEach(([key, service]) => {
    const item = document.createElement("li");
    item.className = "health-item";

    const top = document.createElement("div");
    top.className = "health-top";

    const name = document.createElement("span");
    name.className = "health-name";
    name.textContent = serviceLabels[key] || key;

    const badge = document.createElement("span");
    badge.className = `status-pill ${service.status}`;
    badge.textContent = service.status;

    top.appendChild(name);
    top.appendChild(badge);

    const message = document.createElement("p");
    message.className = "health-message";
    message.textContent = service.message;

    item.appendChild(top);
    item.appendChild(message);

    const detailParts = [];
    if (service.auth_confirmed !== null && service.auth_confirmed !== undefined) {
      detailParts.push(`auth_confirmed=${service.auth_confirmed}`);
    }
    if (service.submit_confirmed !== null && service.submit_confirmed !== undefined) {
      detailParts.push(`submit_confirmed=${service.submit_confirmed}`);
    }
    if (service.render_confirmed !== null && service.render_confirmed !== undefined) {
      detailParts.push(`render_confirmed=${service.render_confirmed}`);
    }
    if (service.reason) {
      detailParts.push(`reason=${service.reason}`);
    }

    if (detailParts.length > 0) {
      const detail = document.createElement("p");
      detail.className = "health-detail";
      detail.textContent = detailParts.join(" | ");
      item.appendChild(detail);
    }

    healthList.appendChild(item);
  });
}

function renderExternalHealth(payload) {
  externalReady = payload.ready_for_submit === true;
  healthBadge.textContent = externalReady ? "ready" : "attention";
  externalSummary.textContent = externalReady
    ? "OpenAI, Higgsfield e FFmpeg estao prontos para receber um job real."
    : "Existe pelo menos uma integracao indisponivel. Revise os itens abaixo antes de enviar.";

  const runtimeParts = [];
  runtimeParts.push(
    payload.startup_mode === "runner"
      ? "Servidor iniciado pelo runner oficial."
      : "Para teste real, inicie via python -m scripts.web_server start."
  );
  if (payload.external_connectivity_checked) {
    runtimeParts.push("A conectividade externa desta instancia ja foi verificada.");
  } else {
    runtimeParts.push("Esta instancia ainda nao tinha validacao externa registrada.");
  }
  runtimeNote.textContent = runtimeParts.join(" ");

  renderHealthServices(payload.services || {});

  if (!externalReady) {
    submitGuard.textContent =
      "O envio esta bloqueado porque OpenAI, Higgsfield ou FFmpeg nao estao prontos neste momento.";
  } else {
    submitGuard.textContent =
      "Conectividade externa validada. O envio usara OpenAI para planejar e Higgsfield para gerar.";
  }

  updateSubmitState();
}

async function fetchExternalHealth() {
  try {
    const response = await fetch("/api/health/external");
    if (!response.ok) {
      throw new Error("Nao foi possivel validar as integracoes externas.");
    }
    const data = await response.json();
    renderExternalHealth(data);
  } catch (error) {
    externalReady = false;
    healthBadge.textContent = "error";
    externalSummary.textContent =
      "Falha ao consultar o health externo. Inicie o servidor pelo runner oficial e tente novamente.";
    runtimeNote.textContent = "Comando oficial: python -m scripts.web_server start";
    healthList.innerHTML = "";
    submitGuard.textContent =
      "O envio foi bloqueado porque nao foi possivel confirmar conectividade com OpenAI/Higgsfield.";
    updateSubmitState();
  }
}

/* ===== JOB STATUS ===== */
function renderStatus(data) {
  jobTitle.textContent = data.title || "Job em processamento";
  jobBadge.textContent = data.status;
  jobProgress.textContent = data.progress_message || "";
  jobEnhanced.textContent = data.enhanced_brief
    ? `Briefing melhorado: ${data.enhanced_brief}`
    : "";
  jobError.textContent = data.user_message || data.error_message || "";
  setWarnings(data.warnings || []);

  const detailParts = [];
  if (data.failed_stage) {
    detailParts.push(`etapa=${data.failed_stage}`);
  }
  if (data.failed_service) {
    detailParts.push(`servico=${data.failed_service}`);
  }
  if (data.failure_code) {
    detailParts.push(`codigo=${data.failure_code}`);
  }
  if (data.retryable !== null && data.retryable !== undefined) {
    detailParts.push(`retryable=${data.retryable}`);
  }
  if (data.auth_confirmed !== null && data.auth_confirmed !== undefined) {
    detailParts.push(`auth_confirmed=${data.auth_confirmed}`);
  }
  if (data.submit_confirmed !== null && data.submit_confirmed !== undefined) {
    detailParts.push(`submit_confirmed=${data.submit_confirmed}`);
  }
  if (data.render_confirmed !== null && data.render_confirmed !== undefined) {
    detailParts.push(`render_confirmed=${data.render_confirmed}`);
  }
  if (data.failure_reason) {
    detailParts.push(`reason=${data.failure_reason}`);
  }
  jobErrorMeta.textContent = detailParts.join(" | ");

  if (data.status === "completed" && data.preview_url && data.download_url) {
    previewVideo.src = data.preview_url;
    downloadLink.href = data.download_url;
    resultContainer.classList.remove("hidden");
    if (pollHandle) {
      clearInterval(pollHandle);
      pollHandle = null;
    }
    isProcessing = false;
    updateSubmitState();
    formMessage.textContent = "Video final pronto.";
  }

  if (data.status === "failed") {
    if (pollHandle) {
      clearInterval(pollHandle);
      pollHandle = null;
    }
    isProcessing = false;
    updateSubmitState();
    formMessage.textContent = data.user_message || "A geracao falhou.";
    fetchExternalHealth().catch(() => {});
  }
}

async function fetchStatus(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`);
  if (!response.ok) {
    throw new Error("Nao foi possivel consultar o status do job.");
  }
  const data = await response.json();
  renderStatus(data);
}

function startSSE(jobId) {
  if (pollHandle) {
    clearInterval(pollHandle);
    pollHandle = null;
  }

  const streamUrl = `/api/jobs/${jobId}/stream`;
  const eventSource = new EventSource(streamUrl);

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      renderStatus(data);

      // EventSource will close on terminal states via the server
      if (data.status === "completed" || data.status === "failed") {
        eventSource.close();
      }
    } catch (error) {
      console.error("SSE parse error:", error);
    }
  };

  eventSource.onerror = (error) => {
    console.error("SSE connection error:", error);
    eventSource.close();
    // Fallback: use polling as backup
    startPolling(jobId);
  };
}

/* ===== FORM SUBMIT ===== */
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!externalReady) {
    submitGuard.textContent =
      "O envio continua bloqueado ate a OpenAI, a Higgsfield e o FFmpeg estarem prontos.";
    return;
  }

  isProcessing = true;
  updateSubmitState();
  formMessage.textContent = "Enviando job...";
  jobError.textContent = "";
  jobErrorMeta.textContent = "";
  jobEnhanced.textContent = "";
  setWarnings([]);
  resetResult();

  const formData = new FormData(form);

  // Append reference images
  if (referenceFiles.embalagem) {
    formData.append("ref_embalagem", referenceFiles.embalagem);
  }
  if (referenceFiles.logo) {
    formData.append("ref_logo", referenceFiles.logo);
  }
  if (referenceFiles.cores) {
    formData.append("ref_cores", referenceFiles.cores);
  }

  // Logo overlay preference
  const logoCheck = document.getElementById("logo-overlay-check");
  formData.append("apply_logo_overlay", logoCheck && logoCheck.checked ? "true" : "false");

  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      body: formData,
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Nao foi possivel criar o job.");
    }

    formMessage.textContent = `Job ${payload.job_id} criado.`;
    startSSE(payload.job_id);
  } catch (error) {
    isProcessing = false;
    updateSubmitState();
    formMessage.textContent = "";
    jobError.textContent = error.message;
  }
});

/* ===== INIT ===== */
initReferenceUploads();
updateSubmitState();
fetchExternalHealth().catch(() => {});
window.setInterval(() => {
  if (!isProcessing) {
    fetchExternalHealth().catch(() => {});
  }
}, 30000);
