const API_BASE = "http://localhost:8000";
const API_KEY = localStorage.getItem("agent_orch_api_key") || "dev-key";
let activeTaskId = null;
let activeJobId = null;
let jobPollTimer = null;
let providersLivePollTimer = null;
let providersLiveJobs = {};
const STAGES = ["planning", "executing", "committing", "pr"];

const el = (id) => document.getElementById(id);

function pretty(data) {
  return JSON.stringify(data, null, 2);
}

function authHeaders(extra = {}) {
  return { "x-api-key": API_KEY, ...extra };
}

function setStatusMessage(message) {
  el("statusMessage").textContent = message;
}

function setJobStatus(message) {
  el("jobStatus").textContent = message;
}

function setTimeline(state, mode = "active") {
  const stageIndex = STAGES.indexOf(state);
  const nodes = document.querySelectorAll(".stage");
  nodes.forEach((node) => {
    const key = node.dataset.stage;
    const idx = STAGES.indexOf(key);
    node.classList.remove("pending", "active", "done", "error");
    if (idx < stageIndex) {
      node.classList.add("done");
    } else if (idx === stageIndex) {
      node.classList.add(mode === "error" ? "error" : "active");
    } else {
      node.classList.add("pending");
    }
  });
}

async function connectProject() {
  const payload = {
    project_type: el("projectType").value,
    local_path: el("localPath").value || null,
    ssh_user: el("sshUser").value || null,
    ssh_host: el("sshHost").value || null,
    ssh_project_path: el("sshPath").value || null,
  };

  const res = await fetch(`${API_BASE}/api/projects/connect`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  el("connectOutput").textContent = pretty(data);
  if (data.connected) {
    setStatusMessage("Project connected. Next: create a task with your goal.");
  } else {
    setStatusMessage("Connection needs fixes. Check the preflight results above.");
  }
}

async function createTask() {
  const payload = {
    project_label: el("projectLabel").value || "Untitled Project",
    user_goal: el("goal").value,
  };

  const res = await fetch(`${API_BASE}/api/tasks`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  activeTaskId = data.task_id;
  el("advanceBtn").disabled = false;
  el("executeLocalBtn").disabled = false;
  el("commitBtn").disabled = false;
  el("preparePrBtn").disabled = false;
  el("createPrBtn").disabled = false;
  el("runAllBtn").disabled = false;
  el("runAsyncBtn").disabled = false;
  el("fixBtn").disabled = false;
  el("dispatchBtn").disabled = false;
  el("dispatchManyBtn").disabled = false;
  el("runProvidersLiveBtn").disabled = false;
  el("sshExecBtn").disabled = false;
  el("eventsBtn").disabled = false;
  setTimeline("planning", "active");
  setStatusMessage("Task created. Review plan, then run Execute Local or Run All.");
  el("taskOutput").textContent = pretty(data);
}

async function advanceTask() {
  if (!activeTaskId) return;
  const res = await fetch(`${API_BASE}/api/tasks/${activeTaskId}/advance`, {
    method: "POST",
    headers: authHeaders(),
  });
  const data = await res.json();
  el("taskOutput").textContent = pretty(data);
}

async function executeLocal() {
  if (!activeTaskId) return;
  setTimeline("executing", "active");
  setStatusMessage("Executing task locally and running tests...");
  const res = await fetch(`${API_BASE}/api/tasks/${activeTaskId}/execute-local`, {
    method: "POST",
    headers: authHeaders(),
  });
  const data = await res.json();
  if (data.tests_status === "failing") {
    setTimeline("executing", "error");
    setStatusMessage("Tests failed. Click Fix It For Me to create a recovery task.");
  } else {
    setTimeline("executing", "done");
    setStatusMessage("Execution completed. Next: commit changes.");
  }
  el("taskOutput").textContent = pretty(data);
}

async function commitTask() {
  if (!activeTaskId) return;
  setTimeline("committing", "active");
  setStatusMessage("Creating a commit for your task changes...");
  const res = await fetch(`${API_BASE}/api/tasks/${activeTaskId}/commit`, {
    method: "POST",
    headers: authHeaders(),
  });
  const data = await res.json();
  if (data.commit_hash) {
    setTimeline("committing", "done");
    setStatusMessage("Commit created. Next: create your GitHub PR.");
  } else {
    setTimeline("committing", "error");
    setStatusMessage("No commit was created. Check if there are any new changes.");
  }
  el("taskOutput").textContent = pretty(data);
}

async function preparePr() {
  if (!activeTaskId) return;
  setStatusMessage("PR draft prepared. Review title and description.");
  const res = await fetch(`${API_BASE}/api/tasks/${activeTaskId}/prepare-pr`, {
    headers: authHeaders(),
  });
  const data = await res.json();
  el("taskOutput").textContent = pretty(data);
}

async function createPr() {
  if (!activeTaskId) return;
  setTimeline("pr", "active");
  setStatusMessage("Creating GitHub PR...");
  const payload = { base_branch: el("baseBranch").value || "main" };
  const res = await fetch(`${API_BASE}/api/tasks/${activeTaskId}/create-pr`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (data.pull_request_url) {
    setTimeline("pr", "done");
    setStatusMessage("PR created successfully. You can now review and merge.");
  } else {
    setTimeline("pr", "error");
    setStatusMessage("PR creation failed. Check GitHub auth and remote setup.");
  }
  el("taskOutput").textContent = pretty(data);
}

async function runAll() {
  if (!activeTaskId) return;
  setTimeline("executing", "active");
  setStatusMessage("Running full pipeline: execute, commit, and create PR...");
  const payload = { base_branch: el("baseBranch").value || "main" };
  const res = await fetch(`${API_BASE}/api/tasks/${activeTaskId}/run-all`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (data.status === "completed") {
    setTimeline("pr", "done");
    setStatusMessage("All done. PR is open and ready for your review.");
  } else if (data.status === "needs_review") {
    setTimeline("executing", "error");
    setStatusMessage("Stopped after execution because tests failed. Click Fix It For Me.");
  } else {
    setTimeline("committing", "error");
    setStatusMessage("Stopped before PR creation. Check task output for details.");
  }
  el("taskOutput").textContent = pretty(data);
}

async function enqueueAsyncRun() {
  if (!activeTaskId) return;
  setTimeline("executing", "active");
  setStatusMessage("Queued background run. You can keep using the app.");
  const payload = { job_type: "run_all", params: { base_branch: el("baseBranch").value || "main" } };
  const res = await fetch(`${API_BASE}/api/tasks/${activeTaskId}/jobs`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  activeJobId = data.job_id;
  setJobStatus(`Job ${activeJobId} queued...`);
  startJobPolling();
  el("taskOutput").textContent = pretty(data);
}

async function checkProviders() {
  const res = await fetch(`${API_BASE}/api/providers`, { headers: authHeaders() });
  const data = await res.json();
  el("taskOutput").textContent = pretty(data);
  setStatusMessage("Provider readiness loaded.");
}

async function dispatchProviderTask() {
  if (!activeTaskId) return;
  const selected = getSelectedProviders();
  const provider = selected[0] || "codex";
  const payload = {
    provider,
    mode: el("providerMode").value,
  };
  const res = await fetch(`${API_BASE}/api/tasks/${activeTaskId}/dispatch`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  setStatusMessage(`Task dispatched via ${payload.provider} (${payload.mode}).`);
  el("taskOutput").textContent = pretty(data);
}

function getSelectedProviders() {
  const select = el("providerSelect");
  return Array.from(select.selectedOptions).map((opt) => opt.value);
}

async function dispatchSelectedProviders() {
  if (!activeTaskId) return;
  const providers = getSelectedProviders();
  if (!providers.length) {
    setStatusMessage("Select at least one provider first.");
    return;
  }
  const payload = {
    providers,
    mode: el("providerMode").value,
  };
  const res = await fetch(`${API_BASE}/api/tasks/${activeTaskId}/dispatch-many`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  setStatusMessage(
    `Dispatched to ${providers.length} provider(s) in ${payload.mode} mode.`
  );
  el("taskOutput").textContent = pretty(data);
}

function terminalElForProvider(provider) {
  return el(`term-${provider}`);
}

function clearProviderTerminals(providers) {
  providers.forEach((p) => {
    const node = terminalElForProvider(p);
    if (node) node.textContent = "";
  });
}

function stopProvidersLivePolling() {
  if (providersLivePollTimer) {
    clearInterval(providersLivePollTimer);
    providersLivePollTimer = null;
  }
  providersLiveJobs = {};
}

function startProvidersLivePolling(jobIdsByProvider) {
  stopProvidersLivePolling();
  providersLiveJobs = jobIdsByProvider;

  providersLivePollTimer = setInterval(async () => {
    const providers = Object.keys(providersLiveJobs);
    let allDone = true;

    for (const provider of providers) {
      const jobId = providersLiveJobs[provider];
      if (!jobId) continue;
      try {
        const res = await fetch(`${API_BASE}/api/jobs/${jobId}`, {
          headers: authHeaders(),
        });
        const job = await res.json();

        const node = terminalElForProvider(provider);
        if (node) {
          if (job.status === "failed") {
            node.textContent = `JOB FAILED (status=${job.status})\\n\\n${job.error || ""}`;
          } else {
            const transcript =
              (job.result && (job.result.transcript || job.result)) || "";
            node.textContent = typeof transcript === "string" ? transcript : JSON.stringify(transcript, null, 2);
          }
        }

        if (job.status !== "succeeded" && job.status !== "failed") {
          allDone = false;
        }
      } catch (error) {
        allDone = false;
        const node = terminalElForProvider(provider);
        if (node) node.textContent = `Error polling job ${jobId}: ${error.message}`;
      }
    }

    if (allDone) {
      stopProvidersLivePolling();
      setStatusMessage("Providers live run finished. Terminals updated.");
      el("runProvidersLiveBtn").disabled = false;
    }
  }, 1200);
}

async function runProvidersLive() {
  if (!activeTaskId) return;
  const providers = getSelectedProviders();
  if (!providers.length) {
    setStatusMessage("Select at least one provider first.");
    return;
  }

  const mode = el("providerMode").value;
  clearProviderTerminals(providers);
  el("runProvidersLiveBtn").disabled = true;

  setStatusMessage(`Queued live runs for ${providers.length} provider(s)...`);
  const jobIdsByProvider = {};

  for (const provider of providers) {
    const payload = {
      job_type: "dispatch_live_pipeline",
      params: { provider, mode, phases: ["implement", "tests_fix"] },
    };
    const res = await fetch(`${API_BASE}/api/tasks/${activeTaskId}/jobs`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    jobIdsByProvider[provider] = data.job_id;
  }

  startProvidersLivePolling(jobIdsByProvider);
}

async function executeSshCommand() {
  if (!activeTaskId) return;
  const payload = {
    command: el("sshCommand").value || "pwd",
    timeout_seconds: 60,
  };
  const res = await fetch(`${API_BASE}/api/tasks/${activeTaskId}/execute-ssh`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (data.success) {
    setStatusMessage("SSH command executed successfully.");
  } else {
    setStatusMessage("SSH command failed. Review output.");
  }
  el("taskOutput").textContent = pretty(data);
}

async function loadTaskEvents() {
  if (!activeTaskId) return;
  const res = await fetch(`${API_BASE}/api/tasks/${activeTaskId}/events`, {
    headers: authHeaders(),
  });
  const data = await res.json();
  setStatusMessage("Loaded task event history.");
  el("taskOutput").textContent = pretty(data);
}

function stopJobPolling() {
  if (jobPollTimer) {
    clearInterval(jobPollTimer);
    jobPollTimer = null;
  }
}

function startJobPolling() {
  stopJobPolling();
  jobPollTimer = setInterval(async () => {
    if (!activeJobId) return;
    try {
      const res = await fetch(`${API_BASE}/api/jobs/${activeJobId}`, { headers: authHeaders() });
      const job = await res.json();
      setJobStatus(`Job ${activeJobId}: ${job.status}`);
      if (job.status === "succeeded") {
        stopJobPolling();
        setTimeline("pr", "done");
        setStatusMessage("Async run completed successfully.");
        el("taskOutput").textContent = pretty(job);
      } else if (job.status === "failed") {
        stopJobPolling();
        setTimeline("executing", "error");
        setStatusMessage("Async run failed. Check output and retry.");
        el("taskOutput").textContent = pretty(job);
      }
    } catch (error) {
      stopJobPolling();
      setJobStatus(`Job polling error: ${error.message}`);
    }
  }, 1200);
}

async function fixItForMe() {
  if (!activeTaskId) return;
  setStatusMessage("Creating an automatic recovery task from failure logs...");
  const res = await fetch(`${API_BASE}/api/tasks/${activeTaskId}/fix-it`, {
    method: "POST",
    headers: authHeaders(),
  });
  const data = await res.json();
  activeTaskId = data.task_id;
  setTimeline("planning", "active");
  setStatusMessage("Recovery task created. Run Execute Local or Run All.");
  el("taskOutput").textContent = pretty(data);
}

el("connectBtn").addEventListener("click", () => {
  connectProject().catch((error) => {
    el("connectOutput").textContent = `Error: ${error.message}`;
  });
});

el("startTaskBtn").addEventListener("click", () => {
  createTask().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});

el("advanceBtn").addEventListener("click", () => {
  advanceTask().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});

el("executeLocalBtn").addEventListener("click", () => {
  executeLocal().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});

el("commitBtn").addEventListener("click", () => {
  commitTask().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});

el("preparePrBtn").addEventListener("click", () => {
  preparePr().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});

el("createPrBtn").addEventListener("click", () => {
  createPr().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});

el("runAllBtn").addEventListener("click", () => {
  runAll().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});

el("runAsyncBtn").addEventListener("click", () => {
  enqueueAsyncRun().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});

el("fixBtn").addEventListener("click", () => {
  fixItForMe().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});

el("providersBtn").addEventListener("click", () => {
  checkProviders().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});

el("dispatchBtn").addEventListener("click", () => {
  dispatchProviderTask().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});

el("dispatchManyBtn").addEventListener("click", () => {
  dispatchSelectedProviders().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});

el("runProvidersLiveBtn").addEventListener("click", () => {
  runProvidersLive().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});

el("sshExecBtn").addEventListener("click", () => {
  executeSshCommand().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});

el("eventsBtn").addEventListener("click", () => {
  loadTaskEvents().catch((error) => {
    el("taskOutput").textContent = `Error: ${error.message}`;
  });
});
