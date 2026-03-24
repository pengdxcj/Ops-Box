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

const esState = {
  clusters: [],
  activeClusterId: 1,
  unbacked: [],
  unbackedAll: [],
  unbackedKeyword: "",
  unbackedPage: 1,
  unbackedPageSize: 10,
  unbackedLoading: false,
  unbackedError: null,
  unbackedRepo: "test-repo",
  selectedIndex: null,
  initialized: false,
  formMode: "create",
  editingClusterId: null,
  snapshotRepos: {},
  autoRefreshTimer: null,
  clusterLoading: false,
};

const esTaskState = {
  items: [],
  total: 0,
  page: 1,
  size: 10,
  loading: false,
  error: null,
  editingId: null,
};

const pythonState = {
  scripts: [],
  editingScript: null,
  loading: false,
  error: null,
};

const PYTHON_SCRIPTS_KEY = "python_scripts";

function savePythonScripts() {
  try {
    localStorage.setItem(PYTHON_SCRIPTS_KEY, JSON.stringify(pythonState.scripts));
    console.log("脚本数据已保存");
  } catch (error) {
    console.error("保存脚本数据失败:", error);
    showToast("保存脚本数据失败", true);
  }
}

function loadPythonScriptsFromStorage() {
  try {
    const stored = localStorage.getItem(PYTHON_SCRIPTS_KEY);
    if (stored) {
      pythonState.scripts = JSON.parse(stored);
      console.log("脚本数据已从存储加载");
    }
  } catch (error) {
    console.error("加载脚本数据失败:", error);
    showToast("加载脚本数据失败", true);
    pythonState.scripts = [];
  }
}

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

const modalState = { resolve: null };

const ES_PAGE_SIZE_KEY = "es_unbacked_page_size";

function readEsPageSize() {
  try {
    const value = Number(sessionStorage.getItem(ES_PAGE_SIZE_KEY));
    if ([10, 20, 50].includes(value)) {
      return value;
    }
  } catch (error) {
    return 10;
  }
  return 10;
}

function writeEsPageSize(size) {
  try {
    sessionStorage.setItem(ES_PAGE_SIZE_KEY, String(size));
  } catch (error) {
    return;
  }
}

function debounce(fn, delay = 200) {
  let timer = null;
  return (...args) => {
    if (timer) {
      window.clearTimeout(timer);
    }
    timer = window.setTimeout(() => fn(...args), delay);
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function setButtonLoading(button, loading, label) {
  if (!button) {
    return;
  }
  if (loading) {
    button.dataset.originalText = button.textContent || "";
    button.textContent = label || "处理�?..";
    button.classList.add("is-loading");
    button.disabled = true;
  } else {
    const original = button.dataset.originalText;
    if (original !== undefined) {
      button.textContent = original;
    }
    button.classList.remove("is-loading");
    button.disabled = false;
  }
}

function closeModal(result = null) {
  const modal = document.getElementById("esModal");
  if (!modal) {
    return;
  }
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  if (modalState.resolve) {
    const resolve = modalState.resolve;
    modalState.resolve = null;
    resolve(result);
  }
}

function showModal({ title, body, actions }) {
  const modal = document.getElementById("esModal");
  if (!modal) {
    return Promise.resolve(null);
  }
  const titleEl = document.getElementById("esModalTitle");
  const bodyEl = document.getElementById("esModalBody");
  const actionsEl = document.getElementById("esModalActions");
  if (titleEl) {
    titleEl.textContent = title || "";
  }
  if (bodyEl) {
    bodyEl.innerHTML = body || "";
  }
  if (actionsEl) {
    actionsEl.innerHTML = "";
    (actions || []).forEach((action) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = action.className || "btn";
      btn.textContent = action.label;
      btn.onclick = () => {
        const value = action.onClick ? action.onClick() : action.value;
        closeModal(value);
      };
      actionsEl.appendChild(btn);
    });
  }

  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  modal.querySelectorAll("[data-modal-close]").forEach((el) => {
    el.onclick = () => closeModal(null);
  });

  return new Promise((resolve) => {
    modalState.resolve = resolve;
  });
}

async function confirmModal({ title, message, confirmText }) {
  const body = `<p>${escapeHtml(message)}</p>`;
  const result = await showModal({
    title,
    body,
    actions: [
      { label: confirmText || "确认", className: "btn btn-danger", value: true },
      { label: "取消", className: "btn btn-ghost", value: false },
    ],
  });
  return result === true;
}

async function showTestResultModal({ success, status, detail }) {
  const statusText = success ? "连接成功" : "连接失败";
  const statusClass = success ? "success" : "danger";
  const info = success
    ? `集群状态: ${escapeHtml(status || "-")}`
    : "请检查连接信息与网络后重试。";
  const detailBlock = detail ? `<pre class="modal-detail">${escapeHtml(detail)}</pre>` : "";
  await showModal({
    title: "ES 连接测试",
    body: `<div class="modal-status ${statusClass}">${statusText}</div><div>${info}</div>${detailBlock}`,
    actions: [{ label: "关闭", className: "btn", value: true }],
  });
}

async function selectSnapshotRepoModal(repos, current) {
  const options = repos
    .map((name) => {
      const safe = escapeHtml(name);
      const selected = name === current ? " selected" : "";
      return `<option value="${safe}"${selected}>${safe}</option>`;
    })
    .join("");
  const body = `
    <label class="modal-field">
      目标仓库
      <select id="esRepoSelect" class="es-input">${options}</select>
    </label>
    <p class="muted">请选择需要绑定的快照仓库。</p>
  `;
  const result = await showModal({
    title: "选择快照仓库",
    body,
    actions: [
      {
        label: "确认",
        className: "btn",
        onClick: () => {
          const select = document.getElementById("esRepoSelect");
          return select ? select.value : null;
        },
      },
      { label: "取消", className: "btn btn-ghost", value: null },
    ],
  });
  return result || null;
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
    try {
      const raw = input.value.trim();
      if (!raw && field.required) {
        throw new Error(`${field.label} \u4e3a\u5fc5\u586b\u9879`);
      }
      if (!raw) {
        continue;
      }
      extension[field.key] = toNumberIfNeeded(raw, field.type);
    } catch (error) {
      console.error(`Error processing field ${field.key}:`, error);
      // 继续处理其他字段，避免因单个字段错误而中断整个流程
    }
  }
  return { payloadKey: conf.payloadKey, data: extension };
}

function renderExtensionFields(assetType) {
  const container = document.getElementById("extensionFields");
  if (!container) {
    return;
  }
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
    asset_type: (document.getElementById("filterType")?.value || "").trim(),
    env: (document.getElementById("filterEnv")?.value || "").trim(),
    status: (document.getElementById("filterStatus")?.value || "").trim(),
    owner: (document.getElementById("filterOwner")?.value || "").trim(),
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
    await Promise.all([loadAssets(), loadChanges()]);
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

function downloadTemplate() {
  const header = [
    "asset_code",
    "asset_type",
    "name",
    "env",
    "status",
    "owner",
    "org",
    "region",
    "tags",
    "instance_id",
    "vpc_id",
    "cpu",
    "memory_gb",
    "os",
    "private_ip",
    "public_ip",
    "expire_time",
    "db_type",
    "db_version",
    "db_endpoint",
    "db_port",
    "db_role",
    "db_storage_gb",
    "db_backup_policy",
    "mw_type",
    "mw_cluster_name",
    "mw_version",
    "mw_node_count",
    "mw_ha_mode",
    "sec_product_type",
    "sec_vendor",
    "sec_version",
    "sec_deploy_mode",
    "sec_coverage_scope",
    "sec_license_expire",
  ];
  const sample = [
    "ecs-prod-012",
    "CLOUD_SERVER",
    "prod-app-ecs-012",
    "prod",
    "IN_USE",
    "ops_team",
    "platform",
    "cn-east-1",
    "service=order;tier=app",
    "i-ecs-prod-012",
    "vpc-001",
    "4",
    "8",
    "Ubuntu 22.04",
    "10.0.1.12",
    "1.2.3.4",
    "2026-12-31T12:00:00",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
  ];
  const content = `${header.join(",")}\n${sample.join(",")}\n`;
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "cmdb_import_template.csv";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
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

// Python脚本管理相关函数
async function loadPythonScripts() {
  // 从API加载脚本列表
  pythonState.loading = true;
  try {
    const data = await request("/scripts");
    pythonState.scripts = data.items.map(script => ({
      id: script.filename,
      name: script.filename,
      description: `上传的脚本: ${script.original_filename || script.filename}`,
      content: "", // 内容将在编辑时加载
      created_at: script.created_at,
      updated_at: script.modified_at,
      url: script.url
    }));
    pythonState.error = null;
  } catch (error) {
    console.error("加载脚本失败:", error);
    pythonState.error = error.message;
    showToast("加载脚本失败", true);
    // 加载失败时使用本地存储作为备用
    loadPythonScriptsFromStorage();
  } finally {
    pythonState.loading = false;
    renderPythonScriptList();
  }
}

function renderPythonScriptList() {
  const container = document.getElementById("pythonScriptList");
  if (!container) {
    return;
  }
  
  if (pythonState.loading) {
    container.innerHTML = `<div class="row-item"><span class="muted">加载中...</span></div>`;
    return;
  }
  
  if (pythonState.error) {
    container.innerHTML = `<div class="row-item"><span class="muted">加载失败: ${escapeHtml(pythonState.error)}</span></div>`;
    return;
  }
  
  if (!pythonState.scripts.length) {
    container.innerHTML = `<div class="row-item"><span class="muted">暂无脚本</span></div>`;
    return;
  }
  
  container.innerHTML = pythonState.scripts.map(script => {
    const createdAt = new Date(script.created_at).toLocaleString();
    const updatedAt = new Date(script.updated_at).toLocaleString();
    return `
    <div class="row-item">
      <div>
        <strong>${escapeHtml(script.name)}</strong>
        <div class="muted" style="font-size: 0.8rem; margin-top: 0.2rem;">
          ${escapeHtml(script.description || '无描述')}
        </div>
        <div class="muted" style="font-size: 0.7rem; margin-top: 0.2rem;">
          创建: ${createdAt} | 更新: ${updatedAt}
        </div>
      </div>
      <div style="display: flex; gap: 0.4rem; align-items: center;">
        <button class="btn btn-ghost btn-small" data-action="edit" data-id="${script.id}">编辑</button>
        <button class="btn btn-danger btn-small" data-action="delete" data-id="${script.id}">删除</button>
      </div>
    </div>
  `;
  }).join('');
}

function newPythonScript() {
  pythonState.editingScript = null;
  document.getElementById("pythonScriptId").value = "";
  document.getElementById("pythonScriptName").value = "";
  document.getElementById("pythonScriptDescription").value = "";
  document.getElementById("pythonScriptContent").value = "";
  document.getElementById("pythonEditorTitle").textContent = "新建脚本";
  document.getElementById("pythonScriptResult").classList.add("hidden");
}

async function editPythonScript(script) {
  pythonState.editingScript = script;
  document.getElementById("pythonScriptId").value = script.id;
  document.getElementById("pythonScriptName").value = script.name;
  document.getElementById("pythonScriptDescription").value = script.description || "";
  document.getElementById("pythonEditorTitle").textContent = "编辑脚本";
  document.getElementById("pythonScriptResult").classList.add("hidden");
  
  // 从API加载脚本内容
  try {
    const data = await request(`/scripts/${script.id}`);
    document.getElementById("pythonScriptContent").value = data.content;
  } catch (error) {
    console.error("加载脚本内容失败:", error);
    showToast("加载脚本内容失败", true);
    document.getElementById("pythonScriptContent").value = script.content || "";
  }
}

function cancelPythonEdit() {
  pythonState.editingScript = null;
  document.getElementById("pythonScriptId").value = "";
  document.getElementById("pythonScriptName").value = "";
  document.getElementById("pythonScriptDescription").value = "";
  document.getElementById("pythonScriptContent").value = "";
  document.getElementById("pythonEditorTitle").textContent = "脚本编辑器";
  document.getElementById("pythonScriptResult").classList.add("hidden");
}

async function savePythonScript(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  const id = formData.get("id");
  const name = formData.get("name").trim();
  const description = formData.get("description").trim();
  const content = formData.get("content").trim();
  
  if (!name || !content) {
    showToast("脚本名称和内容不能为空", true);
    return;
  }
  
  try {
    // 创建临时文件并上传
    const blob = new Blob([content], { type: "text/plain" });
    const file = new File([blob], name, { type: "text/plain" });
    const uploadFormData = new FormData();
    uploadFormData.append("file", file);
    
    // 上传脚本
    const response = await fetch(`${API_BASE}/scripts/upload`, {
      method: "POST",
      body: uploadFormData
    });
    
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.code !== 0) {
      const msg = payload.detail || payload.message || `请求失败: ${response.status}`;
      throw new Error(msg);
    }
    
    // 如果是更新现有脚本，删除旧脚本
    if (id) {
      try {
        await request(`/scripts/${id}`, {
          method: "DELETE"
        });
      } catch (error) {
        console.error("删除旧脚本失败:", error);
        // 继续执行，不中断流程
      }
    }
    
    showToast("脚本保存成功");
    await loadPythonScripts(); // 重新加载脚本列表
    cancelPythonEdit();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function deletePythonScript(id) {
  const script = pythonState.scripts.find(s => s.id == id);
  if (!script) {
    return;
  }
  
  const confirmed = await confirmModal({
    title: "删除脚本",
    message: `确认彻底删除脚本 ${script.name} ？此操作不可撤销。`,
    confirmText: "删除"
  });
  
  if (!confirmed) {
    return;
  }
  
  try {
    // 调用API删除脚本
    await request(`/scripts/${id}`, {
      method: "DELETE"
    });
    
    // 更新本地状态
    pythonState.scripts = pythonState.scripts.filter(s => s.id != id);
    renderPythonScriptList();
    savePythonScripts(); // 同时更新本地存储作为备用
    showToast(`脚本 ${script.name} 已彻底删除`);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function importPythonScript(event) {
  const file = event.target.files[0];
  if (!file) {
    return;
  }
  
  // 检查文件类型
  if (!file.name.endsWith('.py')) {
    showToast("请上传Python脚本文件 (.py)", true);
    event.target.value = "";
    return;
  }
  
  const importBtn = document.getElementById("pythonImportBtn");
  setButtonLoading(importBtn, true, "导入中...");
  
  try {
    // 直接上传文件到API
    const formData = new FormData();
    formData.append("file", file);
    
    const response = await fetch(`${API_BASE}/scripts/upload`, {
      method: "POST",
      body: formData
    });
    
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.code !== 0) {
      const msg = payload.detail || payload.message || `请求失败: ${response.status}`;
      throw new Error(msg);
    }
    
    showToast(`脚本 "${file.name}" 导入成功`);
    await loadPythonScripts(); // 重新加载脚本列表
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setButtonLoading(importBtn, false);
    event.target.value = ""; // 重置文件输入
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
  document.getElementById("templateBtn").addEventListener("click", downloadTemplate);
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
  
  // 导航按钮事件监听
  document.getElementById("navCmdb").addEventListener("click", () => setView("cmdb"));
  document.getElementById("navEs").addEventListener("click", () => setView("es"));
  document.getElementById("navPython").addEventListener("click", () => {
    setView("python");
    loadPythonScripts();
  });
  
  // Python脚本管理事件监听
  if (document.getElementById("pythonRefreshBtn")) {
    document.getElementById("pythonRefreshBtn").addEventListener("click", loadPythonScripts);
  }
  if (document.getElementById("pythonImportBtn")) {
    document.getElementById("pythonImportBtn").addEventListener("click", () => {
      document.getElementById("pythonImportFile").click();
    });
  }
  if (document.getElementById("pythonImportFile")) {
    document.getElementById("pythonImportFile").addEventListener("change", importPythonScript);
  }
  if (document.getElementById("pythonScriptForm")) {
    document.getElementById("pythonScriptForm").addEventListener("submit", savePythonScript);
  }
  if (document.getElementById("pythonCancelEdit")) {
    document.getElementById("pythonCancelEdit").addEventListener("click", cancelPythonEdit);
  }
  if (document.getElementById("pythonScriptList")) {
    document.getElementById("pythonScriptList").addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      if (target.dataset.action === "edit") {
        const id = target.dataset.id;
        const script = pythonState.scripts.find(s => s.id == id);
        if (script) {
          editPythonScript(script);
        }
      } else if (target.dataset.action === "delete") {
        const id = target.dataset.id;
        deletePythonScript(id);
      }
    });
  }
}


function setView(view) {
  const cmdbView = document.getElementById("cmdbView");
  const esView = document.getElementById("esView");
  const pythonView = document.getElementById("pythonView");
  if (!cmdbView || !esView || !pythonView) {
    return;
  }
  const isEs = view === "es";
  const isPython = view === "python";
  cmdbView.classList.toggle("view-active", !isEs && !isPython);
  esView.classList.toggle("view-active", isEs);
  pythonView.classList.toggle("view-active", isPython);
  document.body.classList.toggle("theme-es", isEs);

  const cmdbBtn = document.getElementById("navCmdb");
  const esBtn = document.getElementById("navEs");
  const pythonBtn = document.getElementById("navPython");
  if (cmdbBtn && esBtn && pythonBtn) {
    cmdbBtn.classList.toggle("active", !isEs && !isPython);
    esBtn.classList.toggle("active", isEs);
    pythonBtn.classList.toggle("active", isPython);
    
    if (isEs) {
      cmdbBtn.classList.add("btn-ghost");
      esBtn.classList.remove("btn-ghost");
      pythonBtn.classList.add("btn-ghost");
    } else if (isPython) {
      cmdbBtn.classList.add("btn-ghost");
      esBtn.classList.add("btn-ghost");
      pythonBtn.classList.remove("btn-ghost");
    } else {
      cmdbBtn.classList.remove("btn-ghost");
      esBtn.classList.add("btn-ghost");
      pythonBtn.classList.add("btn-ghost");
    }
  }

  if (isEs) {
    startEsAutoRefresh();
    if (!esState.initialized) {
      esState.initialized = true;
      loadEsClusters({ keepPage: true, forceUnbackedRefresh: true });
    }
  } else {
    stopEsAutoRefresh();
  }
}
function startEsAutoRefresh() {
  // 取消自动刷新，只在特定场景下触发刷新
  // 根据用户要求，仅在以下三种场景下触发页面刷新：
  // a) 页面处于明确的刷新状态时
  // b) 用户切换不同的集群连接时
  // c) 用户执行删除集群操作后
  if (esState.autoRefreshTimer) {
    stopEsAutoRefresh();
  }
}

function stopEsAutoRefresh() {
  if (esState.autoRefreshTimer) {
    window.clearInterval(esState.autoRefreshTimer);
    esState.autoRefreshTimer = null;
  }
}


function setEsFormVisible(visible) {
  const form = document.getElementById("esCreateForm");
  if (!form) {
    return;
  }
  form.classList.toggle("hidden", !visible);
  if (!visible) {
    setEsFormMode("create");
  }
}

function setEsClusterActions(enabled) {
  const elements = [
  document.getElementById("esClusterSelect"),
  document.getElementById("esTestBtn"),
  document.getElementById("esRefreshBtn"),
  document.getElementById("esSearchBtn"),
  document.getElementById("esIndexSearch"),
  document.getElementById("esPageSize"),
  document.querySelector("#esSnapshotForm button"),
];
  elements.forEach((el) => {
    if (el) {
      el.disabled = !enabled;
    }
  });
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = value;
  }
}

function formatCount(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  return new Intl.NumberFormat().format(value);
}

function formatTb(bytes) {
  if (bytes === null || bytes === undefined) {
    return "-";
  }
  const tb = bytes / Math.pow(1024, 4);
  return `${tb.toFixed(2)} TB`;
}

function setHealthStatus(status) {
  const el = document.getElementById("esHealthStatus");
  if (!el) {
    return;
  }
  const text = el.querySelector(".es-health-text");
  if (text) {
    text.textContent = status || "-";
  }
  el.classList.remove("green", "yellow", "red");
  if (status) {
    el.classList.add(status);
  }
}

function setEsSummaryLoading() {
  setText("esClusterName", "\u52a0\u8f7d\u4e2d...");
  setText("esClusterUuid", "\u52a0\u8f7d\u4e2d...");
  setHealthStatus("");
  setText("esNodesTotal", "\u52a0\u8f7d\u4e2d...");
  setText("esNodesMaster", "\u52a0\u8f7d\u4e2d...");
  setText("esNodesData", "\u52a0\u8f7d\u4e2d...");
  setText("esShardsTotal", "\u52a0\u8f7d\u4e2d...");
  setText("esShardsPrimary", "\u52a0\u8f7d\u4e2d...");
  setText("esShardsReplica", "\u52a0\u8f7d\u4e2d...");
  setText("esIndicesTotal", "\u52a0\u8f7d\u4e2d...");
  setText("esDocsTotal", "\u52a0\u8f7d\u4e2d...");
  setText("esStoreSize", "\u52a0\u8f7d\u4e2d...");
}

function resetEsSummary() {
  [
    "esClusterName",
    "esClusterUuid",
    "esNodesTotal",
    "esNodesMaster",
    "esNodesData",
    "esShardsTotal",
    "esShardsPrimary",
    "esShardsReplica",
    "esIndicesTotal",
    "esDocsTotal",
    "esStoreSize",
  ].forEach((id) => setText(id, "-"));
  setHealthStatus("");
}

function renderEsSummary(data) {
  if (!data) {
    resetEsSummary();
    return;
  }
  
  // 尝试从不同的数据结构中获取集群信息
  const clusterInfo = data.cluster || data;
  setText("esClusterName", clusterInfo.name ?? "-");
  setText("esClusterUuid", clusterInfo.uuid ?? "-");
  setHealthStatus(clusterInfo.status || clusterInfo.health || "");

  // 确保nodes对象存在
  const nodes = data.nodes || {};
  setText("esNodesTotal", formatCount(nodes.total));
  setText("esNodesMaster", formatCount(nodes.master));
  setText("esNodesData", formatCount(nodes.data));

  // 尝试从不同的数据结构中获取分片信息
  const shards = data.shards || data.shard || data.sharding || {};
  setText("esShardsTotal", formatCount(shards.total || shards.count || shards.total_shards));
  setText("esShardsPrimary", formatCount(shards.primary || shards.primary_shards));
  setText("esShardsReplica", formatCount(shards.replica || shards.replica_shards));

  // 确保indices对象存在
  const indices = data.indices || {};
  setText("esIndicesTotal", formatCount(indices.count));
  setText("esDocsTotal", formatCount(indices.docs));
  setText("esStoreSize", formatTb(indices.store_bytes));
}

function setSnapshotRepoOptions(repos, selected, hint, disabled) {
  const select = document.getElementById("esSnapshotRepoSelect");
  const hintEl = document.getElementById("esSnapshotRepoHint");
  if (!select) {
    return;
  }
  const repoCount = Array.isArray(repos) ? repos.length : 0;
  if (repoCount === 0) {
    const placeholder = hint || "保存后自动获取";
    select.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>`;
    select.value = selected || "";
    select.disabled = !!disabled;
  } else {
    const options = repos
      .map((repo) => {
        const safe = escapeHtml(repo);
        return `<option value="${safe}">${safe}</option>`;
      })
      .join("");
    select.innerHTML = `<option value="">不指定</option>${options}`;
    if (selected) {
      select.value = selected;
    }
    select.disabled = false;
  }
  if (hintEl) {
    hintEl.textContent = hint || (repoCount ? "已获取仓库列表" : "");
  }
}

function setEsFormMode(mode, cluster) {
  esState.formMode = mode;
  esState.editingClusterId = cluster ? cluster.id : null;
  const form = document.getElementById("esCreateForm");
  if (!form) {
    return;
  }
  form.reset();
  const titleEl = document.getElementById("esFormTitle");
  const submitBtn = document.getElementById("esFormSubmit");
  const cancelBtn = document.getElementById("esCancelCreate");
  if (titleEl) {
    titleEl.textContent = mode === "edit" ? "编辑集群" : "新建集群";
  }
  if (submitBtn) {
    submitBtn.textContent = mode === "edit" ? "保存修改" : "保存集群";
  }
  if (cancelBtn) {
    cancelBtn.textContent = mode === "edit" ? "取消编辑" : "取消";
  }
  if (cluster) {
    const nameInput = form.querySelector('[name="name"]');
    const baseInput = form.querySelector('[name="base_url"]');
    const userInput = form.querySelector('[name="username"]');
    if (nameInput) {
      nameInput.value = cluster.name || "";
    }
    if (baseInput) {
      baseInput.value = cluster.base_url || "";
    }
    if (userInput) {
      userInput.value = cluster.username || "";
    }
  }
  if (mode === "edit" && cluster) {
    setSnapshotRepoOptions([], cluster.snapshot_repo || "", "加载中...", true);
    loadSnapshotReposForForm(cluster.id);
  } else {
    setSnapshotRepoOptions([], "", "保存后自动获取", true);
  }
}
function openCreateForm() {
  setEsFormMode("create");
  setEsFormVisible(true);
}

function openEditForm(cluster) {
  setEsFormMode("edit", cluster);
  setEsFormVisible(true);
}

function renderEsClusterList() {
  const list = document.getElementById("esClusterList");
  const count = document.getElementById("esClusterCount");
  if (!list) {
    return;
  }
  if (count) {
    count.textContent = `${esState.clusters.length} 个`;
  }
  if (!esState.clusters.length) {
    list.innerHTML = `<div class="es-empty">暂无集群配置</div>`;
    return;
  }
  list.innerHTML = esState.clusters
    .map((cluster) => {
      const active = esState.activeClusterId === cluster.id ? " active" : "";
      const repoTag = cluster.snapshot_repo
        ? `<span class="es-tag">仓库: ${escapeHtml(cluster.snapshot_repo)}</span>`
        : `<span class="es-tag warn">未设置仓库</span>`;
      return `
      <div class="es-cluster-item${active}" data-id="${cluster.id}">
        <div class="es-cluster-meta">
          <div class="es-cluster-name">${escapeHtml(cluster.name)}</div>
          <div class="es-cluster-url">${escapeHtml(cluster.base_url)}</div>
          <div class="es-cluster-tags">${repoTag}</div>
        </div>
        <div class="es-cluster-actions">
          <button class="btn btn-ghost btn-small" data-action="edit" type="button">编辑</button>
          <button class="btn btn-danger btn-small" data-action="delete" type="button">删除</button>
        </div>
      </div>`;
    })
    .join("");
}

async function updateEsClusterSnapshotRepo(clusterId, repo, silent = false) {
  await request(`/es/clusters/${clusterId}`, {
    method: "PUT",
    body: JSON.stringify({ snapshot_repo: repo || "" }),
  });
  if (!silent) {
    showToast(repo ? `已绑定快照仓库: ${repo}` : "已清空快照仓库");
  }
}

async function handleSnapshotRepoAutoSelect(clusterId) {
  try {
    const data = await request(`/es/clusters/${clusterId}/repositories`);
    const repos = data.items || [];
    if (!repos.length) {
      await showModal({
        title: "未发现快照仓库",
        body: "<p>该集群未发现可用快照仓库，请检查 ES 中快照仓库配置。</p>",
        actions: [{ label: "关闭", className: "btn", value: true }],
      });
      return;
    }
    if (repos.length === 1) {
      await updateEsClusterSnapshotRepo(clusterId, repos[0], true);
      showToast(`已自动绑定仓库: ${repos[0]}`);
      await loadEsClusters();
      return;
    }
    const current = esState.clusters.find((item) => item.id === clusterId)?.snapshot_repo || "";
    const selected = await selectSnapshotRepoModal(repos, current);
    if (!selected) {
      showToast("未选择快照仓库", true);
      return;
    }
    await updateEsClusterSnapshotRepo(clusterId, selected, true);
    showToast(`已绑定仓库: ${selected}`);
    await loadEsClusters();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function loadSnapshotReposForForm(clusterId) {
  const cluster = esState.clusters.find((item) => item.id === clusterId);
  try {
    const data = await request(`/es/clusters/${clusterId}/repositories`);
    const repos = data.items || [];
    if (!repos.length) {
      setSnapshotRepoOptions([], cluster?.snapshot_repo || "", "当前无可用仓库", true);
      return;
    }
    setSnapshotRepoOptions(repos, cluster?.snapshot_repo || "", "", false);
  } catch (error) {
    setSnapshotRepoOptions([], cluster?.snapshot_repo || "", "获取仓库失败", true);
  }
}

async function deleteEsCluster(clusterId, name, button) {
  const confirmed = await confirmModal({
    title: "删除集群",
    message: `确认删除集群 ${name} ？此操作不可撤销。`,
    confirmText: "删除",
  });
  if (!confirmed) {
    return;
  }
  setButtonLoading(button, true, "删除中...");
  try {
    await request(`/es/clusters/${clusterId}`, { method: "DELETE" });
    showToast(`集群 ${name} 已删除`);
    if (esState.activeClusterId === clusterId) {
      esState.activeClusterId = null;
    }
    await loadEsClusters();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setButtonLoading(button, false);
  }
}
async function loadEsClusters(options = {}) {
  const { keepPage = true, silent = false, forceUnbackedRefresh = true } = options;
  if (esState.clusterLoading) {
    return;
  }
  esState.clusterLoading = true;
  const previousIds = esState.clusters.map((c) => c.id).join(",");
  const previousActive = esState.activeClusterId;
  const select = document.getElementById("esClusterSelect");
  const hint = document.getElementById("esConnectionHint");
  if (select) {
    select.innerHTML = `<option value="">加载中...</option>`;
  }
  if (!silent) {
    setEsClusterActions(false);
    resetEsSummary();
  }

  try {
    const data = await request("/es/clusters");
    esState.clusters = Array.isArray(data) ? data : [];
    renderEsClusterList();

    if (!esState.clusters.length) {
      esState.activeClusterId = null;
      if (select) {
        select.innerHTML = `<option value="">暂无集群</option>`;
      }
      if (hint) {
        hint.textContent = "暂无可用连接，请新建集群配置。";
      }
      esState.clusterLoading = false;
      await refreshUnbacked({ keepPage: false });
      await loadSnapshotTasks({ keepPage: false });
      return;
    }

    const active = esState.clusters.find((c) => c.id === esState.activeClusterId) || esState.clusters[0];
    esState.activeClusterId = active.id;

    if (select) {
      // 保存当前值
      const currentValue = select.value;
      select.innerHTML = esState.clusters
        .map((cluster) => `<option value="${cluster.id}">${cluster.name}</option>`)
        .join("");
      // 只有当值发生变化时才更新，避免触发change事件
      if (currentValue !== String(esState.activeClusterId)) {
        select.value = String(esState.activeClusterId);
      }
    }

    if (hint) {
      hint.textContent = "已连接到集群，可进行健康检查与快照管理。";
    }

    setEsClusterActions(true);
    await refreshEsSummary();
    const newIds = esState.clusters.map((c) => c.id).join(",");
    const clusterChanged = newIds !== previousIds;
    const activeChanged = previousActive !== esState.activeClusterId;
    if (forceUnbackedRefresh || clusterChanged || activeChanged) {
      await refreshUnbacked({ keepPage });
    } else {
      applyUnbackedFilter({ resetPage: false });
    }
    if (activeChanged) {
      esTaskState.page = 1;
    }
    await loadSnapshotTasks({ keepPage: !activeChanged });
  } catch (error) {
    showToast(error.message, true);
    if (select) {
      select.innerHTML = `<option value="">加载失败</option>`;
    }
    if (hint) {
      hint.textContent = "获取集群失败，请稍后重试。";
    }
    renderEsClusterList();
  } finally {
    esState.clusterLoading = false;
  }
}
async function refreshEsSummary() {
  if (!esState.activeClusterId) {
    return;
  }
  setEsSummaryLoading();
  try {
    const data = await request(`/es/clusters/${esState.activeClusterId}/summary`);
    // 添加调试信息
    console.log('Cluster summary data:', data);
    renderEsSummary(data);
  } catch (error) {
    showToast(error.message, true);
    resetEsSummary();
  }
}

async function testEsCluster() {
  const testBtn = document.getElementById("esTestBtn");
  const form = document.getElementById("esCreateForm");
  const formVisible = form && !form.classList.contains("hidden");

  if (formVisible) {
    const formData = new FormData(form);
    const baseUrl = String(formData.get("base_url") || "").trim();
    if (!baseUrl) {
      showToast("请先输入 ES 地址", true);
      return;
    }
    const payload = {
      base_url: baseUrl,
      username: String(formData.get("username") || "").trim(),
      password: String(formData.get("password") || "").trim(),
    };
    setButtonLoading(testBtn, true, "测试中...");
    try {
      const data = await request("/es/clusters/test", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await showTestResultModal({ success: true, status: data?.status });
    } catch (error) {
      await showTestResultModal({ success: false, detail: error.message });
    } finally {
      setButtonLoading(testBtn, false);
    }
    return;
  }

  if (!esState.activeClusterId) {
    showToast("请先选择集群", true);
    return;
  }
  setButtonLoading(testBtn, true, "测试中...");
  try {
    const data = await request(`/es/clusters/${esState.activeClusterId}/test`, { method: "POST" });
    await showTestResultModal({ success: true, status: data?.status });
  } catch (error) {
    await showTestResultModal({ success: false, detail: error.message });
  } finally {
    setButtonLoading(testBtn, false);
  }
}

function getActiveCluster() {
  return esState.clusters.find((c) => c.id === esState.activeClusterId);
}

function getUnbackedPageCount(total) {
  return Math.max(1, Math.ceil(total / esState.unbackedPageSize));
}

function clampUnbackedPage(total) {
  const pageCount = getUnbackedPageCount(total);
  if (esState.unbackedPage > pageCount) {
    esState.unbackedPage = pageCount;
  }
  if (esState.unbackedPage < 1) {
    esState.unbackedPage = 1;
  }
  return pageCount;
}

function updateSnapshotHint(message) {
  const hint = document.getElementById("esSnapshotHint");
  if (!hint) {
    return;
  }
  if (message) {
    hint.textContent = message;
    return;
  }
  if (!esState.activeClusterId) {
    hint.textContent = "请先选择集群";
    return;
  }
  const currentCluster = getActiveCluster();
  if (!currentCluster || !currentCluster.snapshot_repo) {
    hint.textContent = "当前集群未设置快照仓库，请先配置。";
    return;
  }
  const keyword = esState.unbackedKeyword ? ` | 关键词: ${esState.unbackedKeyword}` : "";
  const repoLabel = esState.unbackedRepo || currentCluster.snapshot_repo;
  hint.textContent = repoLabel
    ? `仅展示未备份索引 | 仓库: ${repoLabel}${keyword}`
    : `仅展示未备份索引${keyword}`;
}

function updateUnbackedSummary(totalFiltered, totalAll, pageCount) {
  const countEl = document.getElementById("esIndexCountText");
  const pageEl = document.getElementById("esIndexPageText");
  if (countEl) {
    if (esState.unbackedLoading) {
      countEl.textContent = "加载中...";
    } else if (esState.unbackedError) {
      countEl.textContent = "加载失败";
    } else if (esState.unbackedKeyword) {
      countEl.textContent = `匹配 ${totalFiltered} / 共 ${totalAll}`;
    } else {
      countEl.textContent = `共 ${totalAll} 个`;
    }
  }
  if (pageEl) {
    if (esState.unbackedLoading || esState.unbackedError) {
      pageEl.textContent = "";
    } else if (totalFiltered === 0) {
      pageEl.textContent = "无结果";
    } else {
      pageEl.textContent = `第 ${esState.unbackedPage} / ${pageCount} 页`;
    }
  }
}

function renderUnbackedPagination(totalFiltered, pageCount) {
  const container = document.getElementById("esPagination");
  if (!container) {
    return;
  }
  if (esState.unbackedLoading || esState.unbackedError || totalFiltered === 0) {
    container.innerHTML = "";
    return;
  }
  const current = esState.unbackedPage;
  const pages = [];
  const windowSize = 2;
  const start = Math.max(1, current - windowSize);
  const end = Math.min(pageCount, current + windowSize);
  if (start > 1) {
    pages.push(1);
  }
  if (start > 2) {
    pages.push("ellipsis");
  }
  for (let i = start; i <= end; i += 1) {
    pages.push(i);
  }
  if (end < pageCount - 1) {
    pages.push("ellipsis");
  }
  if (end < pageCount) {
    pages.push(pageCount);
  }

  const parts = [];
  parts.push(
    `<button class="es-page-btn" data-page="${current - 1}" ${current === 1 ? "disabled" : ""}>上一页</button>`
  );
  pages.forEach((page) => {
    if (page === "ellipsis") {
      parts.push('<span class="es-page-ellipsis">...</span>');
      return;
    }
    const active = page === current ? " active" : "";
    parts.push(`<button class="es-page-btn${active}" data-page="${page}">${page}</button>`);
  });
  parts.push(
    `<button class="es-page-btn" data-page="${current + 1}" ${current === pageCount ? "disabled" : ""}>下一页</button>`
  );
  container.innerHTML = parts.join("");
}

function updateSelectedIndexInputs() {
  const selectedInput = document.getElementById("esSelectedIndex");
  const snapshotInput = document.getElementById("esSnapshotName");
  if (selectedInput) {
    selectedInput.value = esState.selectedIndex || "";
  }
  if (snapshotInput) {
    snapshotInput.value = esState.selectedIndex ? `snapshot_${esState.selectedIndex}` : "";
  }
}
function renderUnbackedList() {
  const container = document.getElementById("esIndexList");
  if (!container) {
    return;
  }
  const totalAll = Array.isArray(esState.unbackedAll) ? esState.unbackedAll.length : 0;
  const totalFiltered = Array.isArray(esState.unbacked) ? esState.unbacked.length : 0;
  const pageCount = clampUnbackedPage(totalFiltered);
  updateUnbackedSummary(totalFiltered, totalAll, pageCount);

  if (esState.unbackedLoading) {
    container.innerHTML = `<div class="es-loading"><span class="spinner"></span>加载中...</div>`;
    renderUnbackedPagination(0, 1);
    return;
  }
  if (esState.unbackedError) {
    container.innerHTML = `<div class="es-empty">${escapeHtml(esState.unbackedError)} <button class="btn btn-ghost btn-small" data-action="retry-unbacked" type="button">重试</button></div>`;
    renderUnbackedPagination(0, 1);
    return;
  }

  if (!esState.activeClusterId) {
    container.innerHTML = `<div class="es-empty">请先选择集群</div>`;
    renderUnbackedPagination(0, 1);
    return;
  }

  const currentCluster = getActiveCluster();
  if (!currentCluster || !currentCluster.snapshot_repo) {
    container.innerHTML = `<div class="es-empty">当前集群未设置快照仓库，请先配置。</div>`;
    renderUnbackedPagination(0, 1);
    return;
  }

  if (!totalFiltered) {
    container.innerHTML = `<div class="es-empty">未查询到未备份索引</div>`;
    renderUnbackedPagination(0, 1);
    return;
  }

  const start = (esState.unbackedPage - 1) * esState.unbackedPageSize;
  const pageItems = esState.unbacked.slice(start, start + esState.unbackedPageSize);
  container.innerHTML = pageItems
    .map((name) => {
      const safeName = escapeHtml(name);
      const active = esState.selectedIndex === name ? " active" : "";
      return `\
      <div class=\"es-index-item${active}\" data-index=\"${safeName}\">\
        <span class=\"es-index-name\">${safeName}</span>\
        <span class=\"es-index-tag\">未备份</span>\
      </div>`;
    })
    .join("");
  renderUnbackedPagination(totalFiltered, pageCount);
}

function setSelectedIndex(index) {
  esState.selectedIndex = index || null;
  updateSelectedIndexInputs();
  renderUnbackedList();
}

function applyUnbackedFilter(options = {}) {
  const { resetPage = false } = options;
  const source = Array.isArray(esState.unbackedAll) ? esState.unbackedAll : [];
  const keyword = esState.unbackedKeyword.trim().toLowerCase();
  esState.unbacked = keyword
    ? source.filter((name) => String(name).toLowerCase().includes(keyword))
    : source.slice();
  if (resetPage) {
    esState.unbackedPage = 1;
  }
  if (esState.selectedIndex && !esState.unbacked.includes(esState.selectedIndex)) {
    esState.selectedIndex = null;
    updateSelectedIndexInputs();
  }
  updateSnapshotHint();
  renderUnbackedList();
}

async function fetchUnbackedIndexes() {
  if (!esState.activeClusterId || esState.unbackedLoading) {
    return;
  }
  const currentCluster = getActiveCluster();
  if (!currentCluster || !currentCluster.snapshot_repo) {
    esState.unbackedAll = [];
    esState.unbacked = [];
    esState.unbackedRepo = "";
    esState.unbackedError = null;
    updateSnapshotHint();
    renderUnbackedList();
    return;
  }
  esState.unbackedLoading = true;
  esState.unbackedError = null;
  updateSnapshotHint("正在获取未备份索引...");
  renderUnbackedList();
  try {
    // 调用真实API获取未备份索引
    const data = await request(`/es/clusters/${esState.activeClusterId}/unbacked`);
    esState.unbackedAll = data.items || [];
    esState.unbackedRepo = currentCluster.snapshot_repo || "";
    esState.unbackedError = null;
  } catch (error) {
    esState.unbackedAll = [];
    esState.unbackedError = error.message;
    updateSnapshotHint("获取未备份索引失败");
    showToast(error.message, true);
  } finally {
    esState.unbackedLoading = false;
  }
}

async function refreshUnbacked(options = {}) {
  const { keepPage = true } = options;
  if (!esState.activeClusterId) {
    esState.unbackedAll = [];
    esState.unbacked = [];
    esState.unbackedError = null;
    updateSnapshotHint();
    renderUnbackedList();
    return;
  }
  const previousPage = esState.unbackedPage;
  await fetchUnbackedIndexes();
  esState.unbackedPage = keepPage ? previousPage : 1;
  applyUnbackedFilter({ resetPage: !keepPage });
}

async function searchUnbacked(forceFetch = false) {
  if (!esState.activeClusterId) {
    showToast("请先选择集群", true);
    return;
  }
  const keywordInput = document.getElementById("esIndexSearch");
  esState.unbackedKeyword = keywordInput ? keywordInput.value.trim() : "";
  if (forceFetch || (!esState.unbackedAll.length && !esState.unbackedLoading)) {
    await refreshUnbacked({ keepPage: false });
    return;
  }
  applyUnbackedFilter({ resetPage: true });
}

async function createSnapshot(event) {
  event.preventDefault();
  if (!esState.activeClusterId) {
    showToast("\u8bf7\u5148\u9009\u62e9\u96c6\u7fa4", true);
    return;
  }
  if (!esState.selectedIndex) {
    showToast("\u8bf7\u9009\u62e9\u8981\u5907\u4efd\u7684\u7d22\u5f15", true);
    return;
  }
  const snapshotInput = document.getElementById("esSnapshotName");
  const snapshot = snapshotInput ? snapshotInput.value.trim() : "";
  if (!snapshot) {
    showToast("\u8bf7\u8f93\u5165\u5907\u4efd\u540d\u79f0", true);
    return;
  }
  try {
    await request(`/es/clusters/${esState.activeClusterId}/snapshots`, {
      method: "POST",
      body: JSON.stringify({ index: esState.selectedIndex, snapshot }),
    });
    showToast("\u5df2\u63d0\u4ea4\u5feb\u7167\u4efb\u52a1");
    await refreshUnbacked({ keepPage: true });
  } catch (error) {
    showToast(error.message, true);
  }
}

async function submitEsCluster(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  const payload = {
    name: String(formData.get("name") || "").trim(),
    base_url: String(formData.get("base_url") || "").trim(),
    username: String(formData.get("username") || "").trim(),
    password: String(formData.get("password") || "").trim(),
    snapshot_repo: String(formData.get("snapshot_repo") || "").trim(),
  };

  if (!payload.name || !payload.base_url) {
    showToast("请完善集群名称与地址", true);
    return;
  }

  const isEdit = esState.formMode === "edit" && esState.editingClusterId;
  const submitBtn = document.getElementById("esFormSubmit");
  setButtonLoading(submitBtn, true, isEdit ? "保存中..." : "创建中...");

  try {
    let data;
    if (isEdit) {
      const updatePayload = {
        name: payload.name,
        base_url: payload.base_url,
        username: payload.username,
      };
      if (payload.password) {
        updatePayload.password = payload.password;
      }
      const repoSelect = document.getElementById("esSnapshotRepoSelect");
      if (repoSelect && !repoSelect.disabled) {
        updatePayload.snapshot_repo = repoSelect.value.trim();
      }
      data = await request(`/es/clusters/${esState.editingClusterId}`, {
        method: "PUT",
        body: JSON.stringify(updatePayload),
      });
      showToast("连接更新成功");
    } else {
      data = await request("/es/clusters", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("连接创建成功");
    }

    form.reset();
    setEsFormVisible(false);
    if (data?.id) {
      esState.activeClusterId = data.id;
    }
    await loadEsClusters();
    if (data?.id) {
      await handleSnapshotRepoAutoSelect(data.id);
    }
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setButtonLoading(submitBtn, false);
  }
}

function formatLocalDateTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleString();
}

function formatLocalInput(date) {
  const pad = (num) => String(num).padStart(2, "0");
  const year = date.getFullYear();
  const month = pad(date.getMonth() + 1);
  const day = pad(date.getDate());
  const hours = pad(date.getHours());
  const minutes = pad(date.getMinutes());
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function setDefaultTaskTime() {
  const input = document.getElementById("esTaskTime");
  if (!input || input.value) {
    return;
  }
  const target = new Date();
  target.setSeconds(0, 0);
  target.setMinutes(target.getMinutes() + 10);
  input.value = formatLocalInput(target);
}

function formatTaskStatus(status) {
  const map = {
    PENDING: { label: "待执行", className: "pending" },
    RUNNING: { label: "执行中", className: "running" },
    SUCCESS: { label: "成功", className: "success" },
    FAILED: { label: "失败", className: "failed" },
    RETRYING: { label: "重试中", className: "retrying" },
    CANCELED: { label: "已取消", className: "canceled" },
  };
  return map[status] || { label: status || "-", className: "pending" };
}

function renderTaskPagination() {
  const container = document.getElementById("esTaskPagination");
  if (!container) {
    return;
  }
  if (esTaskState.loading || esTaskState.error || esTaskState.total <= esTaskState.size) {
    container.innerHTML = "";
    return;
  }
  const pageCount = Math.max(1, Math.ceil(esTaskState.total / esTaskState.size));
  const current = esTaskState.page;
  const pages = [];
  const windowSize = 2;
  const start = Math.max(1, current - windowSize);
  const end = Math.min(pageCount, current + windowSize);
  if (start > 1) {
    pages.push(1);
  }
  if (start > 2) {
    pages.push("ellipsis");
  }
  for (let i = start; i <= end; i += 1) {
    pages.push(i);
  }
  if (end < pageCount - 1) {
    pages.push("ellipsis");
  }
  if (end < pageCount) {
    pages.push(pageCount);
  }

  const parts = [];
  parts.push(
    `<button class="es-page-btn" data-task-page="${current - 1}" ${current === 1 ? "disabled" : ""}>上一页</button>`
  );
  pages.forEach((page) => {
    if (page === "ellipsis") {
      parts.push('<span class="es-page-ellipsis">...</span>');
      return;
    }
    const active = page === current ? " active" : "";
    parts.push(`<button class="es-page-btn${active}" data-task-page="${page}">${page}</button>`);
  });
  parts.push(
    `<button class="es-page-btn" data-task-page="${current + 1}" ${current === pageCount ? "disabled" : ""}>下一页</button>`
  );
  container.innerHTML = parts.join("");
}

function renderSnapshotTasks() {
  const container = document.getElementById("esTaskTable");
  const countEl = document.getElementById("esTaskCount");
  if (countEl) {
    if (esTaskState.loading) {
      countEl.textContent = "加载中...";
    } else if (esTaskState.error) {
      countEl.textContent = "加载失败";
    } else {
      countEl.textContent = `共 ${esTaskState.total} 个`;
    }
  }
  if (!container) {
    return;
  }
  if (esTaskState.loading) {
    container.innerHTML = `<div class="es-loading"><span class="spinner"></span>加载中...</div>`;
    renderTaskPagination();
    return;
  }
  if (esTaskState.error) {
    container.innerHTML = `<div class="es-empty">${escapeHtml(esTaskState.error)} <button class="btn btn-ghost btn-small" data-action="retry-task" type="button">重试</button></div>`;
    renderTaskPagination();
    return;
  }
  if (!esState.activeClusterId) {
    container.innerHTML = `<div class="es-empty">请先选择集群</div>`;
    renderTaskPagination();
    return;
  }
  if (!esTaskState.total) {
    container.innerHTML = `<div class="es-empty">暂无定时任务</div>`;
    renderTaskPagination();
    return;
  }

  const header = `
    <div class="es-task-row header">
      <div class="es-task-cell">索引</div>
      <div class="es-task-cell">计划执行</div>
      <div class="es-task-cell">执行状态</div>
      <div class="es-task-cell">重试</div>
      <div class="es-task-cell">操作</div>
    </div>`;
  const rows = esTaskState.items
    .map((task) => {
      const status = formatTaskStatus(task.status);
      const retryText = `${task.retry_count}/${task.max_retries}`;
      return `
      <div class="es-task-row" data-task-id="${task.id}">
        <div class="es-task-cell" title="${escapeHtml(task.index_name)}">${escapeHtml(task.index_name)}</div>
        <div class="es-task-cell">${formatLocalDateTime(task.scheduled_at)}</div>
        <div class="es-task-cell"><span class="es-task-status ${status.className}">${status.label}</span></div>
        <div class="es-task-cell">${retryText}</div>
        <div class="es-task-cell es-task-actions-cell">
          <button class="btn btn-ghost btn-small" data-action="task-logs" type="button">日志</button>
          <button class="btn btn-ghost btn-small" data-action="task-edit" type="button">编辑</button>
          ${task.status === 'RUNNING' ? '<button class="btn btn-warning btn-small" data-action="task-terminate" type="button">终止</button>' : ''}
          <button class="btn btn-danger btn-small" data-action="task-delete" type="button">删除</button>
        </div>
      </div>`;
    })
    .join("");
  container.innerHTML = header + rows;
  renderTaskPagination();
}

function resetTaskForm() {
  const form = document.getElementById("esTaskForm");
  if (!form) {
    return;
  }
  form.reset();
  setDefaultTaskTime();
}

function setTaskFormMode(mode, task) {
  const submitBtn = document.getElementById("esTaskSubmitBtn");
  const cancelBtn = document.getElementById("esTaskCancelEdit");
  if (mode === "edit" && task) {
    esTaskState.editingId = task.id;
    if (submitBtn) {
      submitBtn.textContent = "更新任务";
    }
    if (cancelBtn) {
      cancelBtn.classList.remove("hidden");
    }
    const indexInput = document.getElementById("esTaskIndex");
    const timeInput = document.getElementById("esTaskTime");
    const nameInput = document.getElementById("esTaskSnapshotName");
    const retriesSelect = document.getElementById("esTaskMaxRetries");
    const intervalSelect = document.getElementById("esTaskRetryInterval");
    if (indexInput) {
      indexInput.value = task.index_name || "";
    }
    if (timeInput) {
      const scheduled = task.scheduled_at ? new Date(task.scheduled_at) : null;
      timeInput.value = scheduled ? formatLocalInput(scheduled) : "";
    }
    if (nameInput) {
      nameInput.value = task.snapshot_name || "";
    }
    if (retriesSelect) {
      retriesSelect.value = String(task.max_retries ?? 2);
    }
    if (intervalSelect) {
      intervalSelect.value = String(task.retry_interval_minutes ?? 2);
    }
    return;
  }
  esTaskState.editingId = null;
  if (submitBtn) {
    submitBtn.textContent = "创建任务";
  }
  if (cancelBtn) {
    cancelBtn.classList.add("hidden");
  }
  resetTaskForm();
}

function getTaskFormPayload() {
  const indexInput = document.getElementById("esTaskIndex");
  const timeInput = document.getElementById("esTaskTime");
  const nameInput = document.getElementById("esTaskSnapshotName");
  const retriesSelect = document.getElementById("esTaskMaxRetries");
  const intervalSelect = document.getElementById("esTaskRetryInterval");
  const indexName = indexInput ? indexInput.value.trim() : "";
  if (!indexName) {
    showToast("请输入索引名称", true);
    return null;
  }
  const timeValue = timeInput ? timeInput.value.trim() : "";
  if (!timeValue) {
    showToast("请选择执行时间", true);
    return null;
  }
  const date = new Date(timeValue);
  if (Number.isNaN(date.getTime())) {
    showToast("执行时间无效", true);
    return null;
  }
  date.setSeconds(0, 0);
  // 构建本地时间的ISO格式字符串，包含正确的时区偏移
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const offset = -date.getTimezoneOffset();
  const offsetSign = offset >= 0 ? '+' : '-';
  const offsetHours = String(Math.abs(Math.floor(offset / 60))).padStart(2, '0');
  const offsetMinutes = String(Math.abs(offset % 60)).padStart(2, '0');
  const scheduledAt = `${year}-${month}-${day}T${hours}:${minutes}:00${offsetSign}${offsetHours}:${offsetMinutes}`;
  const snapshotName = nameInput ? nameInput.value.trim() : "";
  const maxRetries = retriesSelect ? Number(retriesSelect.value) : 2;
  const retryInterval = intervalSelect ? Number(intervalSelect.value) : 2;

  return {
    create: {
      cluster_id: esState.activeClusterId,
      index_name: indexName,
      scheduled_at: scheduledAt,
      snapshot_name: snapshotName || undefined,
      max_retries: maxRetries,
      retry_interval_minutes: retryInterval,
    },
    update: {
      index_name: indexName,
      scheduled_at: scheduledAt,
      snapshot_name: snapshotName || "",
      max_retries: maxRetries,
      retry_interval_minutes: retryInterval,
    },
  };
}

async function loadSnapshotTasks(options = {}) {
  const { keepPage = true } = options;
  if (!esState.activeClusterId) {
    esTaskState.items = [];
    esTaskState.total = 0;
    esTaskState.page = 1;
    esTaskState.loading = false;
    esTaskState.error = null;
    renderSnapshotTasks();
    return;
  }
  if (!keepPage) {
    esTaskState.page = 1;
  }
  esTaskState.loading = true;
  esTaskState.error = null;
  renderSnapshotTasks();
  try {
    const query = new URLSearchParams({
      page: String(esTaskState.page),
      size: String(esTaskState.size),
      cluster_id: String(esState.activeClusterId),
    });
    const data = await request(`/es/snapshots/tasks?${query.toString()}`);
    esTaskState.items = data.items || [];
    esTaskState.total = data.total || 0;
    esTaskState.page = data.page || esTaskState.page;
  } catch (error) {
    esTaskState.items = [];
    esTaskState.total = 0;
    esTaskState.error = error.message;
    showToast(error.message, true);
  } finally {
    esTaskState.loading = false;
    renderSnapshotTasks();
  }
}

async function submitSnapshotTask(event) {
  event.preventDefault();
  if (!esState.activeClusterId) {
    showToast("请先选择集群", true);
    return;
  }
  const payloads = getTaskFormPayload();
  if (!payloads) {
    return;
  }
  const submitBtn = document.getElementById("esTaskSubmitBtn");
  setButtonLoading(submitBtn, true, esTaskState.editingId ? "更新中..." : "创建中...");
  try {
    if (esTaskState.editingId) {
      await request(`/es/snapshots/tasks/${esTaskState.editingId}`, {
        method: "PUT",
        body: JSON.stringify(payloads.update),
      });
      showToast("定时任务已更新");
    } else {
      await request("/es/snapshots/tasks", {
        method: "POST",
        body: JSON.stringify(payloads.create),
      });
      showToast("定时任务已创建");
    }
    setTaskFormMode("create");
    await loadSnapshotTasks({ keepPage: false });
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setButtonLoading(submitBtn, false);
  }
}

async function openTaskLogsModal(taskId) {
  try {
    const data = await request(`/es/snapshots/tasks/${taskId}`);
    const task = data.task;
    const logs = data.logs || [];
    const logContent = logs.length
      ? `<div class="es-task-log">${logs
          .map((log) => {
            const status = formatTaskStatus(log.status);
            const errorBlock = log.error_message
              ? `<div class=\"muted\">${escapeHtml(log.error_message)}</div>`
              : "";
            return `
            <div class=\"es-task-log-item\">
              <div><strong>${status.label}</strong> 于 ${formatLocalDateTime(log.executed_at)}</div>
              <div class=\"muted\">索引: ${escapeHtml(log.index_name)}</div>
              ${errorBlock}
            </div>`;
          })
          .join("")}</div>`
      : "<div class=\"es-empty\">暂无执行日志</div>";

    const body = `
      <div class=\"modal-field\">任务ID: ${task.id}</div>
      <div class=\"modal-field\">索引: ${escapeHtml(task.index_name)}</div>
      <div class=\"modal-field\">计划执行: ${formatLocalDateTime(task.scheduled_at)}</div>
      ${logContent}
    `;
    await showModal({
      title: "任务执行日志",
      body,
      actions: [{ label: "关闭", className: "btn", value: true }],
    });
  } catch (error) {
    showToast(error.message, true);
  }
}
function bindEsEvents() {
  // 初始化每页显示数量
  esState.unbackedPageSize = readEsPageSize();
  const pageSizeSelectInit = document.getElementById("esPageSize");
  if (pageSizeSelectInit) {
    pageSizeSelectInit.value = String(esState.unbackedPageSize);
  }
  
  const navCmdb = document.getElementById("navCmdb");
  const navEs = document.getElementById("navEs");
  if (navCmdb) {
    navCmdb.addEventListener("click", () => setView("cmdb"));
  }
  if (navEs) {
    navEs.addEventListener("click", () => setView("es"));
  }

  const newBtn = document.getElementById("esNewBtn");
  if (newBtn) {
    newBtn.addEventListener("click", openCreateForm);
  }
  const cancelBtn = document.getElementById("esCancelCreate");
  if (cancelBtn) {
    cancelBtn.addEventListener("click", () => setEsFormVisible(false));
  }
  const createForm = document.getElementById("esCreateForm");
  if (createForm) {
    createForm.addEventListener("submit", submitEsCluster);
  }
  const select = document.getElementById("esClusterSelect");
  if (select) {
    select.addEventListener("change", (event) => {
      const value = event.target.value;
      esState.activeClusterId = value ? Number(value) : null;
      renderEsClusterList();
      if (esState.activeClusterId) {
        setSelectedIndex("");
        refreshEsSummary();
        searchUnbacked();
        loadSnapshotTasks({ keepPage: false });
      } else {
        resetEsSummary();
        loadSnapshotTasks({ keepPage: false });
      }
    });
  }
  const testBtn = document.getElementById("esTestBtn");
  if (testBtn) {
    testBtn.addEventListener("click", testEsCluster);
  }
  const refreshBtn = document.getElementById("esRefreshBtn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      refreshEsSummary();
      searchUnbacked();
    });
  }
  const searchBtn = document.getElementById("esSearchBtn");
  if (searchBtn) {
    searchBtn.addEventListener("click", searchUnbacked);
  }
  const snapshotForm = document.getElementById("esSnapshotForm");
  if (snapshotForm) {
    snapshotForm.addEventListener("submit", createSnapshot);
  }
  const taskForm = document.getElementById("esTaskForm");
  if (taskForm) {
    taskForm.addEventListener("submit", submitSnapshotTask);
    setDefaultTaskTime();
  }
  const taskRefreshBtn = document.getElementById("esTaskRefreshBtn");
  if (taskRefreshBtn) {
    taskRefreshBtn.addEventListener("click", () => loadSnapshotTasks({ keepPage: true }));
  }
  const taskUseSelected = document.getElementById("esTaskUseSelected");
  if (taskUseSelected) {
    taskUseSelected.addEventListener("click", () => {
      if (!esState.selectedIndex) {
        showToast("请先选择索引", true);
        return;
      }
      const indexInput = document.getElementById("esTaskIndex");
      const nameInput = document.getElementById("esTaskSnapshotName");
      if (indexInput) {
        indexInput.value = esState.selectedIndex;
      }
      if (nameInput && !nameInput.value) {
        nameInput.value = `snapshot_${esState.selectedIndex}`;
      }
    });
  }
  const taskCancelEdit = document.getElementById("esTaskCancelEdit");
  if (taskCancelEdit) {
    taskCancelEdit.addEventListener("click", () => setTaskFormMode("create"));
  }
  const taskPagination = document.getElementById("esTaskPagination");
  if (taskPagination) {
    taskPagination.addEventListener("click", (event) => {
      const target = event.target;
      const button = target instanceof HTMLElement ? target.closest("button[data-task-page]") : null;
      if (!button) {
        return;
      }
      const page = Number(button.dataset.taskPage);
      if (!Number.isFinite(page) || page < 1) {
        return;
      }
      esTaskState.page = page;
      loadSnapshotTasks({ keepPage: true });
    });
  }
  
  // 未备份索引列表分页控件事件绑定
  const unbackedPagination = document.getElementById("esPagination");
  if (unbackedPagination) {
    unbackedPagination.addEventListener("click", (event) => {
      const target = event.target;
      const button = target instanceof HTMLElement ? target.closest("button[data-page]") : null;
      if (!button) {
        return;
      }
      const page = Number(button.dataset.page);
      if (!Number.isFinite(page) || page < 1) {
        return;
      }
      esState.unbackedPage = page;
      renderUnbackedList();
    });
  }
  
  // 每页显示数量选择器事件绑定
  const pageSizeSelect = document.getElementById("esPageSize");
  if (pageSizeSelect) {
    pageSizeSelect.addEventListener("change", (event) => {
      const size = Number(event.target.value);
      if (!Number.isFinite(size) || size <= 0) {
        return;
      }
      esState.unbackedPageSize = size;
      writeEsPageSize(size);
      esState.unbackedPage = 1;
      applyUnbackedFilter({ resetPage: true });
    });
  }
  const taskTable = document.getElementById("esTaskTable");
  if (taskTable) {
    taskTable.addEventListener("click", async (event) => {
      const target = event.target;
      const button = target instanceof HTMLElement ? target.closest("button[data-action]") : null;
      if (!button) {
        return;
      }
      const action = button.dataset.action;
      if (action === "retry-task") {
        loadSnapshotTasks({ keepPage: true });
        return;
      }
      const row = button.closest("[data-task-id]");
      const taskId = row ? Number(row.dataset.taskId) : null;
      if (!taskId) {
        return;
      }
      const task = esTaskState.items.find((item) => Number(item.id) === taskId);
      if (action === "task-edit" && task) {
        setTaskFormMode("edit", task);
        return;
      }
      if (action === "task-logs") {
        await openTaskLogsModal(taskId);
        return;
      }
      if (action === "task-delete") {
        const confirmed = await confirmModal({
          title: "删除定时任务",
          message: `确认删除定时任务 #${taskId} ？`,
          confirmText: "删除",
        });
        if (!confirmed) {
          return;
        }
        try {
          await request(`/es/snapshots/tasks/${taskId}`, { method: "DELETE" });
          showToast("定时任务已删除");
          await loadSnapshotTasks({ keepPage: true });
        } catch (error) {
          showToast(error.message, true);
        }
      }
      if (action === "task-terminate") {
        const confirmed = await confirmModal({
          title: "终止定时任务",
          message: `确认终止正在执行的定时任务 #${taskId} ？`,
          confirmText: "终止",
        });
        if (!confirmed) {
          return;
        }
        try {
          await request(`/es/snapshots/tasks/${taskId}/terminate`, { method: "POST" });
          showToast("定时任务已终止");
          await loadSnapshotTasks({ keepPage: true });
        } catch (error) {
          showToast(error.message, true);
        }
      }
    });
  }
  const list = document.getElementById("esIndexList");
  if (list) {
    list.addEventListener("click", (event) => {
      const target = event.target;
      const item = target instanceof HTMLElement ? target.closest(".es-index-item") : null;
      if (!item) {
        return;
      }
      const index = item.dataset.index;
      if (index) {
        setSelectedIndex(index);
      }
    });
  }
  const clusterList = document.getElementById("esClusterList");
  if (clusterList) {
    clusterList.addEventListener("click", (event) => {
      const target = event.target;
      const button = target instanceof HTMLElement ? target.closest("button[data-action]") : null;
      if (!button) {
        return;
      }
      const item = button.closest(".es-cluster-item");
      const id = item?.dataset.id;
      const cluster = esState.clusters.find((c) => String(c.id) === String(id));
      if (!cluster) {
        return;
      }
      if (button.dataset.action === "edit") {
        openEditForm(cluster);
      } else if (button.dataset.action === "delete") {
        deleteEsCluster(cluster.id, cluster.name, button);
      }
    });
  }
}

function bootstrap() {
  renderExtensionFields("CLOUD_SERVER");
  bindEvents();
  bindEsEvents();
  setEsFormMode("create");
  setView("cmdb");
  loadAll();
}

bootstrap();






























