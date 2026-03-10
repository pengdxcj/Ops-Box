const API_BASE = "/api/v1";

const extensionSchema = {
  CLOUD_SERVER: {
    payloadKey: "cloud_server",
    fields: [
      { key: "instance_id", label: "\u5b9e\u4f8b ID", required: true, placeholder: "i-ecs-prod-012" },
      { key: "vpc_id", label: "VPC ID", required: true, placeholder: "vpc-001" },
      { key: "cpu", label: "CPU", required: true, type: "number", placeholder: "4" },
      { key: "memory_gb", label: "\u5185\u5b58(GB)", required: true, type: "number", placeholder: "8" },
      { key: "os", label: "OS", required: true, placeholder: "Ubuntu 22.04" },
      { key: "private_ip", label: "\u5185\u7f51 IP", required: true, placeholder: "10.0.1.12" },
      { key: "public_ip", label: "\u516c\u7f51 IP", required: true, placeholder: "1.2.3.4" },
      {
        key: "expire_time",
        label: "\u5230\u671f\u65f6\u95f4(ISO8601)",
        placeholder: "2026-12-31T12:00:00",
      },
    ],
  },
  DB: {
    payloadKey: "database",
    fields: [
      { key: "db_type", label: "\u6570\u636e\u5e93\u7c7b\u578b", required: true, placeholder: "MySQL" },
      { key: "version", label: "\u7248\u672c", required: true, placeholder: "8.0" },
      { key: "endpoint", label: "\u5730\u5740", required: true, placeholder: "db-prod.internal" },
      { key: "port", label: "\u7aef\u53e3", required: true, type: "number", placeholder: "3306" },
      { key: "role", label: "\u89d2\u8272", value: "primary", placeholder: "primary" },
      { key: "storage_gb", label: "\u5b58\u50a8(GB)", type: "number", value: 20, placeholder: "20" },
      { key: "backup_policy", label: "\u5907\u4efd\u7b56\u7565", value: "daily", placeholder: "daily" },
    ],
  },
  MIDDLEWARE: {
    payloadKey: "middleware",
    fields: [
      { key: "mw_type", label: "\u4e2d\u95f4\u4ef6\u7c7b\u578b", required: true, placeholder: "Redis" },
      {
        key: "cluster_name",
        label: "\u96c6\u7fa4\u540d\u79f0",
        required: true,
        placeholder: "redis-prod-main",
      },
      { key: "version", label: "\u7248\u672c", required: true, placeholder: "7.2" },
      { key: "node_count", label: "\u8282\u70b9\u6570", type: "number", value: 1, placeholder: "3" },
      { key: "ha_mode", label: "\u9ad8\u53ef\u7528\u6a21\u5f0f", value: "single", placeholder: "master-replica" },
    ],
  },
  SECURITY_PRODUCT: {
    payloadKey: "security_product",
    fields: [
      { key: "product_type", label: "\u5b89\u5168\u4ea7\u54c1\u7c7b\u578b", required: true, placeholder: "WAF" },
      { key: "vendor", label: "\u5382\u5546", required: true, placeholder: "AcmeSec" },
      { key: "version", label: "\u7248\u672c", required: true, placeholder: "3.6" },
      { key: "deploy_mode", label: "\u90e8\u7f72\u6a21\u5f0f", required: true, placeholder: "cloud_managed" },
      {
        key: "coverage_scope",
        label: "\u8986\u76d6\u8303\u56f4",
        required: true,
        placeholder: "edge + api-gateway",
      },
      {
        key: "license_expire",
        label: "\u8bb8\u53ef\u8bc1\u5230\u671f(ISO8601)",
        placeholder: "2026-10-01T00:00:00",
      },
    ],
  },
};

const state = {
  assets: [],
};

function showToast(message, isError = false) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.style.borderColor = isError ? "rgba(176,66,44,0.45)" : "rgba(15,45,47,0.12)";
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 2600);
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok || payload.code !== 0) {
    const msg = payload.detail || payload.message || `\u8bf7\u6c42\u5931\u8d25: ${res.status}`;
    throw new Error(msg);
  }
  return payload.data;
}

function parseTags(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [tagKey, ...rest] = line.split("=");
      return { tag_key: tagKey.trim(), tag_value: rest.join("=").trim() };
    })
    .filter((tag) => tag.tag_key && tag.tag_value);
}

function toNumberIfNeeded(value, type) {
  if (type !== "number") {
    return value;
  }
  return Number(value);
}

function buildExtensionPayload(assetType) {
  const conf = extensionSchema[assetType];
  const extension = {};
  for (const field of conf.fields) {
    const input = document.querySelector(`[data-field="${field.key}"]`);
    if (!input) {
      continue;
    }
    const raw = input.value.trim();
    if (!raw && field.required) {
      throw new Error(`${field.label} \u4e3a\u5fc5\u586b\u9879`);
    }
    if (!raw) {
      continue;
    }
    extension[field.key] = toNumberIfNeeded(raw, field.type);
  }
  return { payloadKey: conf.payloadKey, data: extension };
}

function renderExtensionFields(assetType) {
  const container = document.getElementById("extensionFields");
  const conf = extensionSchema[assetType];
  container.innerHTML = conf.fields
    .map(
      (field) => `
      <label>
        ${field.label}
        <input
          data-field="${field.key}"
          type="${field.type === "number" ? "number" : "text"}"
          ${field.required ? "required" : ""}
          value="${field.value ?? ""}"
          placeholder="${field.placeholder ?? ""}"
        />
      </label>
    `
    )
    .join("");
}

function renderMetrics(assets) {
  const inUse = assets.filter((asset) => asset.status === "IN_USE").length;
  const prod = assets.filter((asset) => asset.env === "prod").length;
  const sec = assets.filter((asset) => asset.asset_type === "SECURITY_PRODUCT").length;

  const metrics = [
    { label: "\u8d44\u4ea7\u603b\u6570", value: assets.length },
    { label: "\u4f7f\u7528\u4e2d", value: inUse },
    { label: "\u751f\u4ea7\u73af\u5883", value: prod },
    { label: "\u5b89\u5168\u4ea7\u54c1", value: sec },
  ];

  document.getElementById("metrics").innerHTML = metrics
    .map(
      (metric) => `
      <article class="metric">
        <div class="metric-label">${metric.label}</div>
        <div class="metric-value">${metric.value}</div>
      </article>
    `
    )
    .join("");
}

function renderAssetTable(assets) {
  const tbody = document.getElementById("assetTableBody");
  if (!assets.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="muted">\u672a\u67e5\u8be2\u5230\u8d44\u4ea7\u3002</td></tr>`;
    return;
  }

  tbody.innerHTML = assets
    .map(
      (item) => `
      <tr>
        <td>${item.id}</td>
        <td>${item.asset_code}</td>
        <td>${item.name}</td>
        <td>${item.asset_type}</td>
        <td>${item.env}</td>
        <td>${item.status}</td>
        <td>${item.owner}</td>
        <td>
          <button class="btn btn-danger btn-small" data-action="delete" data-id="${item.id}" data-code="${item.asset_code}">
            \u5220\u9664
          </button>
        </td>
      </tr>
    `
    )
    .join("");
}

function currentFilters() {
  return {
    asset_type: document.getElementById("filterType").value.trim(),
    env: document.getElementById("filterEnv").value.trim(),
    status: document.getElementById("filterStatus").value.trim(),
    owner: document.getElementById("filterOwner").value.trim(),
  };
}

function toQuery(params) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "") {
      query.set(key, value);
    }
  });
  return query.toString();
}

async function loadAssets() {
  const params = currentFilters();
  const query = toQuery({ page: 1, size: 200, ...params });
  const data = await request(`/assets?${query}`);
  state.assets = data.items || [];
  document.getElementById("assetCountText").textContent = `\u5171 ${data.total} \u6761`;
  renderMetrics(state.assets);
  renderAssetTable(state.assets);
}

async function loadCoverage() {
  const coverage = await request("/security/coverage");
  document.getElementById("coverageSummary").textContent =
    `\u5df2\u8986\u76d6 ${coverage.protected}/${coverage.total} (${coverage.ratio}%)`;
  const list = document.getElementById("coverageTypeList");
  const rows = Object.entries(coverage.by_type || {});
  if (!rows.length) {
    list.innerHTML = `<div class="row-item"><span class="muted">\u6682\u65e0\u4f7f\u7528\u4e2d\u7684\u8d44\u4ea7\u3002</span></div>`;
    return;
  }

  list.innerHTML = rows
    .map(
      ([type, item]) => `
      <div class="row-item">
        <strong>${type}</strong>
        <span>${item.protected}/${item.total} (${item.ratio}%)</span>
      </div>
    `
    )
    .join("");
}

async function loadUncovered() {
  const result = await request("/security/uncovered");
  document.getElementById("uncoveredCountText").textContent =
    `\u4f7f\u7528\u4e2d\u672a\u8986\u76d6\u8d44\u4ea7 ${result.total} \u6761`;
  const list = document.getElementById("uncoveredList");
  if (!result.items.length) {
    list.innerHTML = `<span class="chip">\u5df2\u5168\u90e8\u8986\u76d6</span>`;
    return;
  }

  list.innerHTML = result.items
    .map(
      (item) =>
        `<span class="chip warn">#${item.id} ${item.asset_code} (${item.asset_type}/${item.env})</span>`
    )
    .join("");
}

async function loadChanges() {
  const data = await request("/audit/changes?page=1&size=8");
  const list = document.getElementById("changeLogList");
  if (!data.items.length) {
    list.innerHTML = `<div class="row-item"><span class="muted">\u6682\u65e0\u53d8\u66f4\u65e5\u5fd7\u3002</span></div>`;
    return;
  }

  list.innerHTML = data.items
    .map(
      (item) => `
      <div class="row-item">
        <span><strong>#${item.asset_id}</strong> ${item.change_type}</span>
        <span>${new Date(item.changed_at).toLocaleString()}</span>
      </div>
    `
    )
    .join("");
}

async function loadAll() {
  try {
    await Promise.all([loadAssets(), loadCoverage(), loadUncovered(), loadChanges()]);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function createAsset(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  const assetType = String(formData.get("asset_type")).trim();
  try {
    const payload = {
      asset_code: String(formData.get("asset_code")).trim(),
      asset_type: assetType,
      name: String(formData.get("name")).trim(),
      env: String(formData.get("env")).trim(),
      status: String(formData.get("status")).trim(),
      owner: String(formData.get("owner")).trim(),
      org: String(formData.get("org")).trim(),
      region: String(formData.get("region")).trim(),
      tags: parseTags(String(formData.get("tags") || "")),
    };

    const extension = buildExtensionPayload(assetType);
    payload[extension.payloadKey] = extension.data;

    await request("/assets", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    showToast(`\u8d44\u4ea7 ${payload.asset_code} \u521b\u5efa\u6210\u529f`);
    form.reset();
    document.getElementById("assetType").value = assetType;
    renderExtensionFields(assetType);
    await loadAll();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function triggerSync() {
  try {
    const result = await request("/discovery/sync", { method: "POST" });
    showToast(
      `\u540c\u6b65\u5df2\u89e6\u53d1\uff1a\u672c\u6b21\u68c0\u67e5 ${result.summary.checked_total} \u6761\u8d44\u4ea7`
    );
  } catch (error) {
    showToast(error.message, true);
  }
}

async function exportAssets() {
  const params = currentFilters();
  const query = toQuery(params);
  const url = query ? `${API_BASE}/assets/export?${query}` : `${API_BASE}/assets/export`;
  const link = document.createElement("a");
  link.href = url;
  link.download = "";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

async function importAssets(event) {
  const file = event.target.files[0];
  if (!file) {
    return;
  }
  try {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/assets/import`, { method: "POST", body: formData });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok || payload.code !== 0) {
      const msg = payload.detail || payload.message || `\u5bfc\u5165\u5931\u8d25: ${res.status}`;
      throw new Error(msg);
    }
    const data = payload.data || {};
    showToast(`\u5bfc\u5165\u5b8c\u6210: \u6210\u529f ${data.success || 0} \u6761, \u5931\u8d25 ${data.failed || 0} \u6761`);
    await loadAll();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    event.target.value = "";
  }
}

async function deleteAsset(id, code) {
  const confirmed = window.confirm(`\u786e\u8ba4\u5220\u9664\u8d44\u4ea7 ${code} (#${id})?`);
  if (!confirmed) {
    return;
  }
  try {
    await request(`/assets/${id}`, { method: "DELETE" });
    showToast(`\u8d44\u4ea7 ${code} \u5df2\u5220\u9664`);
    await loadAll();
  } catch (error) {
    showToast(error.message, true);
  }
}

function bindEvents() {
  document.getElementById("filterBtn").addEventListener("click", loadAssets);
  document.getElementById("refreshAllBtn").addEventListener("click", loadAll);
  document.getElementById("syncBtn").addEventListener("click", triggerSync);
  document.getElementById("createAssetForm").addEventListener("submit", createAsset);
  document.getElementById("assetType").addEventListener("change", (event) => {
    renderExtensionFields(event.target.value);
  });
  document.getElementById("exportBtn").addEventListener("click", exportAssets);
  const importInput = document.getElementById("importFile");
  document.getElementById("importBtn").addEventListener("click", () => importInput.click());
  importInput.addEventListener("change", importAssets);
  document.getElementById("assetTableBody").addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    if (target.dataset.action === "delete") {
      const id = target.dataset.id;
      const code = target.dataset.code;
      if (id && code) {
        deleteAsset(id, code);
      }
    }
  });
}

function bootstrap() {
  renderExtensionFields("CLOUD_SERVER");
  bindEvents();
  loadAll();
}

bootstrap();
