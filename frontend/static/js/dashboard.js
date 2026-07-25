const fmtMoney = (n) => '₦' + Number(n || 0).toLocaleString('en-NG', { maximumFractionDigits: 2 });
const fmtInt = (n) => Number(n || 0).toLocaleString('en-NG');
const SALARY_TYPE_LABEL = { base: '底薪批次', bonus: '奖金', backpay: '补发薪资' };
const STATUS_LABEL = { pending_review: '待确认', confirmed: '已入库', rejected: '已放弃', superseded: '已被替换' };

let currentBatchId = null;
let trendChart = null;
let currentUserRole = null;
let metaCategories = []; // [{value, label}] - cached from /api/meta, see populateMeta()

// ---------- shell: tabs + whoami ----------
async function initShell() {
  try {
    const me = await apiJson('/api/auth/me');
    currentUserRole = me.role;
    document.getElementById('whoami').textContent = `${me.username}（${me.role === 'admin' ? '管理员' : '只读'}）`;
  } catch (e) {
    return;
  }
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    });
  });
  document.getElementById('logoutBtn').addEventListener('click', async () => {
    await apiFetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/';
  });

  if (currentUserRole === 'admin') {
    document.querySelectorAll('.admin-only').forEach((el) => (el.style.display = ''));
  } else {
    // Viewers never upload/manage permissions - hide both tabs (the "上传数据"
    // button has no default inline hide style in the HTML, unlike "用户权限",
    // so it must be hidden here explicitly) and land on trend instead.
    document.querySelectorAll('.admin-only').forEach((el) => (el.style.display = 'none'));
    document.querySelectorAll('.tab-btn.active').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel.active').forEach((p) => p.classList.remove('active'));
    document.querySelector('.tab-btn[data-tab="trend"]').classList.add('active');
    document.getElementById('tab-trend').classList.add('active');
  }
}

// ---------- upload tab ----------
function issueSeverity(issue) {
  // field_mapping_check (PRD V1.8 §4) fires on every upload, success or not
  // - only the "some target field didn't match" case should read as a
  // warning; the "✓ 全部匹配" case is a positive confirmation, not a problem.
  if (issue.issue_type === 'field_mapping_check') {
    return issue.issue_detail.includes('✓') ? 'good' : 'severe';
  }
  return ['missing_field', 'unrecognized_sheet'].includes(issue.issue_type) ? 'severe' : '';
}

function renderBatch(batch) {
  currentBatchId = batch.id;
  const card = document.getElementById('reviewCard');
  card.style.display = 'block';
  document.getElementById('reviewMonth').textContent = `${batch.month}（${batch.original_filename}）`;
  document.getElementById('reviewSalaryType').textContent = SALARY_TYPE_LABEL[batch.salary_type] || batch.salary_type;

  const s = batch.summary;
  if (batch.salary_type === 'base') {
    const deltaText = s.headcount_delta === null || s.headcount_delta === undefined
      ? '（无上月数据可比）'
      : (s.headcount_delta >= 0 ? `+${s.headcount_delta}` : s.headcount_delta);
    document.getElementById('reviewSummary').innerHTML = `
      <div class="stat"><div class="label">本月总人数（现金流口径）</div><div class="value">${fmtInt(s.headcount_total)}</div></div>
      <div class="stat"><div class="label">较上月净变化</div><div class="value">${deltaText}</div></div>
      <div class="stat"><div class="label">总HR Cost</div><div class="value">${fmtMoney(s.total_hr_cost)}</div></div>
      <div class="stat"><div class="label">本月内离职（仍在本月发薪）</div><div class="value">${fmtInt(s.headcount_resigned_this_month)}</div></div>
    `;
  } else {
    document.getElementById('reviewSummary').innerHTML = `
      <div class="stat"><div class="label">记录条数</div><div class="value">${fmtInt(s.row_count)}</div></div>
      <div class="stat"><div class="label">能关联到底薪员工</div><div class="value">${fmtInt(s.matched_count)}</div></div>
      <div class="stat"><div class="label">关联不到（仍计入总成本）</div><div class="value">${fmtInt(s.unmatched_count)}</div></div>
      <div class="stat"><div class="label">总金额</div><div class="value">${fmtMoney(s.total_amount)}</div></div>
    `;
  }

  const issuesEl = document.getElementById('reviewIssues');
  if (batch.issues.length === 0) {
    issuesEl.innerHTML = '<li style="background:rgba(30,158,99,0.12);border-color:rgba(30,158,99,0.3);">未发现异常，所有关键字段均成功映射</li>';
  } else {
    issuesEl.innerHTML = batch.issues
      .map((i) => `<li class="${issueSeverity(i)}"><strong>[${i.issue_type}]</strong> ${i.issue_detail}</li>`)
      .join('');
  }

  const busy = batch.status !== 'pending_review';
  document.getElementById('confirmBtn').disabled = busy;
  document.getElementById('rejectBtn').disabled = busy;
  document.getElementById('confirmBtn').textContent = batch.status === 'confirmed' ? '已入库' : '确认无误，正式入库';
  document.getElementById('reconciliationExportBtn').style.display = batch.salary_type === 'base' ? '' : 'none';
}

async function loadUploadHistory() {
  const statusFilter = document.getElementById('historyStatusFilter')?.value || '';
  const qs = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : '';
  const list = await apiJson(`/api/upload${qs}`);
  const el = document.getElementById('uploadHistory');
  if (list.length === 0) {
    el.innerHTML = '<div class="muted">暂无上传记录</div>';
    return;
  }
  const isAdmin = currentUserRole === 'admin';
  el.innerHTML = list
    .map(
      (b) => `
      <div class="upload-list-item">
        <span>${b.month} · ${SALARY_TYPE_LABEL[b.salary_type] || b.salary_type} · ${b.original_filename} · 上传人 ${b.uploaded_by} · ${new Date(b.uploaded_at).toLocaleString('zh-CN')}</span>
        <span>
          <span class="badge ${b.status}">${STATUS_LABEL[b.status] || b.status}</span>
          ${isAdmin && b.status === 'pending_review' ? `
            <button class="secondary" style="padding:2px 8px;font-size:12px;margin-left:6px;" onclick="reopenBatch(${b.id})">查看/处理</button>
          ` : ''}
          ${isAdmin && b.status === 'confirmed' ? `
            <button class="secondary" style="padding:2px 8px;font-size:12px;margin-left:6px;" onclick="reassignBatchMonth(${b.id}, '${b.month}')">改月份</button>
            <button class="danger" style="padding:2px 8px;font-size:12px;margin-left:4px;" onclick="deleteBatch(${b.id}, '${b.month}')">删除</button>
          ` : ''}
        </span>
      </div>`
    )
    .join('');
}

async function reopenBatch(batchId) {
  try {
    const batch = await apiJson(`/api/upload/${batchId}`);
    renderBatch(batch);
    document.getElementById('reviewCard').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    alert('打开批次失败：' + e.message);
  }
}

async function reassignBatchMonth(batchId, currentMonth) {
  const newMonth = prompt(`把这个批次的月份从 ${currentMonth} 改成（格式 YYYY-MM）：`, currentMonth);
  if (!newMonth || newMonth === currentMonth) return;
  try {
    await apiJson(`/api/upload/${batchId}/reassign-month`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_month: newMonth }),
    });
    await loadUploadHistory();
    await populateMeta();
  } catch (e) {
    alert('改月份失败：' + e.message);
  }
}

async function deleteBatch(batchId, month) {
  if (!confirm(`确定要删除 ${month} 的这个批次吗？这会把它写入的数据一并删掉，且不可恢复。`)) return;
  try {
    await apiJson(`/api/upload/${batchId}`, { method: 'DELETE' });
    await loadUploadHistory();
    await populateMeta();
  } catch (e) {
    alert('删除失败：' + e.message);
  }
}

function initUploadTab() {
  if (currentUserRole !== 'admin') return; // viewers never touch the upload router - see routers/upload.py's require_admin

  document.getElementById('uploadBtn').addEventListener('click', async () => {
    const month = document.getElementById('uploadMonth').value;
    const salaryType = document.getElementById('uploadSalaryType').value;
    const fileInput = document.getElementById('uploadFile');
    const errEl = document.getElementById('uploadError');
    errEl.textContent = '';
    if (!month || !fileInput.files[0]) {
      errEl.textContent = '请选择月份和文件';
      return;
    }
    const form = new FormData();
    form.append('file', fileInput.files[0]);
    try {
      const batch = await apiJson(`/api/upload?month=${encodeURIComponent(month)}&salary_type=${encodeURIComponent(salaryType)}`, {
        method: 'POST',
        body: form,
      });
      renderBatch(batch);
      loadUploadHistory();
    } catch (e) {
      errEl.textContent = e.message;
    }
  });

  document.getElementById('confirmBtn').addEventListener('click', async () => {
    const errEl = document.getElementById('reviewError');
    errEl.textContent = '';
    try {
      const batch = await apiJson(`/api/upload/${currentBatchId}/confirm`, { method: 'POST' });
      renderBatch(batch);
      loadUploadHistory();
      await populateMeta();
    } catch (e) {
      errEl.textContent = e.message;
    }
  });

  document.getElementById('rejectBtn').addEventListener('click', async () => {
    const errEl = document.getElementById('reviewError');
    errEl.textContent = '';
    try {
      const batch = await apiJson(`/api/upload/${currentBatchId}/reject`, { method: 'POST' });
      renderBatch(batch);
      loadUploadHistory();
    } catch (e) {
      errEl.textContent = e.message;
    }
  });

  document.getElementById('reconciliationExportBtn').addEventListener('click', async () => {
    const errEl = document.getElementById('reviewError');
    errEl.textContent = '';
    try {
      await downloadBlob(`/api/upload/${currentBatchId}/reconciliation-export`, {}, '分部门核对.xlsx');
    } catch (e) {
      errEl.textContent = e.message;
    }
  });

  document.getElementById('historyStatusFilter').addEventListener('change', loadUploadHistory);

  loadUploadHistory();
}

// ---------- meta (departments / entities / months) ----------
async function populateMeta() {
  const meta = await apiJson('/api/meta');
  metaCategories = meta.categories;
  const fillSelect = (id, values, withEmpty) => {
    const el = document.getElementById(id);
    const current = el.value;
    el.innerHTML = (withEmpty ? '<option value="">全部</option>' : '') + values.map((v) => `<option value="${v}">${v}</option>`).join('');
    if (values.includes(current)) el.value = current;
  };
  fillSelect('trendDept', meta.departments, true);
  fillSelect('trendEntity', meta.entities, true);
  fillSelect('trendStart', meta.months, false);
  fillSelect('trendEnd', meta.months, false);
  if (meta.months.length) {
    document.getElementById('trendStart').value = meta.months[0];
    document.getElementById('trendEnd').value = meta.months[meta.months.length - 1];
  }

  const fillCategorySelect = (id) => {
    const el = document.getElementById(id);
    const current = el.value;
    el.innerHTML = meta.categories.map((c) => `<option value="${c.value}">${c.label}</option>`).join('');
    if (meta.categories.some((c) => c.value === current)) el.value = current;
  };
  fillCategorySelect('catCompareCategory');
  renderCatTrendCategoryChecklist(meta.categories);

  fillSelect('catTrendDept', meta.departments, true);
  fillSelect('catTrendEntity', meta.entities, true);
  fillSelect('catCompareEntity', meta.entities, true);
  fillSelect('compDept', meta.departments, true);
  fillSelect('compEntity', meta.entities, true);
  fillSelect('catTrendStart', meta.months, false);
  fillSelect('catTrendEnd', meta.months, false);
  fillSelect('catCompareMonth', meta.months, false);
  fillSelect('compMonth', meta.months, false);
  if (meta.months.length) {
    document.getElementById('catTrendStart').value = meta.months[0];
    document.getElementById('catTrendEnd').value = meta.months[meta.months.length - 1];
    document.getElementById('catCompareMonth').value = meta.months[meta.months.length - 1];
    document.getElementById('compMonth').value = meta.months[meta.months.length - 1];
  }

  fillSelect('exportDept', meta.departments, true);
  fillSelect('exportEntity', meta.entities, true);
  fillSelect('exportStart', meta.months, false);
  fillSelect('exportEnd', meta.months, false);
  if (meta.months.length) {
    document.getElementById('exportStart').value = meta.months[0];
    document.getElementById('exportEnd').value = meta.months[meta.months.length - 1];
  }
}

// ---------- export tab (download employee-level salary detail) ----------
async function downloadBlob(path, fetchOptions, fallbackFilename) {
  const resp = await apiFetch(path, fetchOptions || {});
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败 (${resp.status})`);
  }
  const disposition = resp.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename\*=UTF-8''([^;]+)/);
  const filename = match ? decodeURIComponent(match[1]) : fallbackFilename || '导出.xlsx';
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function downloadPost(path, body, fallbackFilename) {
  return downloadBlob(
    path,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) },
    fallbackFilename
  );
}

function initExportTab() {
  document.getElementById('exportDownloadBtn').addEventListener('click', async () => {
    const errEl = document.getElementById('exportError');
    errEl.textContent = '';
    const salaryTypes = [];
    if (document.getElementById('exportTypeBase').checked) salaryTypes.push('base');
    if (document.getElementById('exportTypeBonus').checked) salaryTypes.push('bonus');
    if (document.getElementById('exportTypeBackpay').checked) salaryTypes.push('backpay');
    if (salaryTypes.length === 0) {
      errEl.textContent = '请至少勾选一个批次类型';
      return;
    }
    const payload = {
      department: document.getElementById('exportDept').value || null,
      entity: document.getElementById('exportEntity').value || null,
      start_month: document.getElementById('exportStart').value || null,
      end_month: document.getElementById('exportEnd').value || null,
      salary_types: salaryTypes,
    };
    try {
      await downloadPost('/api/export/detail', payload, '薪酬明细导出.xlsx');
    } catch (e) {
      errEl.textContent = e.message;
    }
  });
}

// ---------- trend tab ----------
function renderTrend(rows) {
  const ctx = document.getElementById('trendChart');
  const labels = rows.map((r) => r.month);
  const costData = rows.map((r) => r.total_hr_cost);
  const headcountData = rows.map((r) => r.headcount);

  if (trendChart) trendChart.destroy();
  trendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: '总HR Cost (₦)', data: costData, borderColor: '#2f6fed', backgroundColor: 'rgba(47,111,237,0.15)', yAxisID: 'y', tension: 0.25 },
        { label: '人数', data: headcountData, borderColor: '#1e9e63', backgroundColor: 'rgba(30,158,99,0.15)', yAxisID: 'y1', tension: 0.25 },
      ],
    },
    options: {
      scales: {
        y: { position: 'left', title: { display: true, text: 'HR Cost (₦)' } },
        y1: { position: 'right', title: { display: true, text: '人数' }, grid: { drawOnChartArea: false } },
      },
    },
  });

  const tbody = document.querySelector('#trendTable tbody');
  tbody.innerHTML = rows
    .map((r) => `<tr><td>${r.month}</td><td>${fmtInt(r.headcount)}</td><td>${fmtMoney(r.total_hr_cost)}</td><td>${fmtMoney(r.avg_hr_cost)}</td></tr>`)
    .join('');
}

function currentTrendMode() {
  return document.querySelector('input[name="trendMode"]:checked').value;
}

function updateTrendModeVisibility() {
  const isCompare = currentTrendMode() === 'compare';
  document.getElementById('trendTrendResult').style.display = isCompare ? 'none' : '';
  document.getElementById('trendCompareResult').style.display = isCompare ? '' : 'none';
}

// PRD V1.7 §1: "两点比较模式" is not a second implementation of attribution -
// it's the exact same /api/attribution endpoint (compute_attribution already
// supports any two months, not just adjacent ones) that the trend page's
// filters now call directly, instead of duplicating the diff logic here.
function initTrendTab() {
  document.querySelectorAll('input[name="trendMode"]').forEach((r) => r.addEventListener('change', updateTrendModeVisibility));
  updateTrendModeVisibility();

  document.getElementById('trendQueryBtn').addEventListener('click', async () => {
    const errEl = document.getElementById('trendError');
    errEl.textContent = '';
    const department = document.getElementById('trendDept').value || null;
    const entity = document.getElementById('trendEntity').value || null;
    const start = document.getElementById('trendStart').value;
    const end = document.getElementById('trendEnd').value;

    try {
      if (currentTrendMode() === 'trend') {
        const rows = await apiPost('/api/trend', { department, entity, start_month: start || null, end_month: end || null });
        renderTrend(rows);
      } else {
        if (!start || !end || start >= end) {
          errEl.textContent = '两点比较模式下，起始月份必须早于结束月份';
          return;
        }
        const r = await apiPost('/api/attribution', { department, entity, prev_month: start, cur_month: end });
        renderAttribution(r);
      }
    } catch (e) {
      errEl.textContent = e.message;
    }
  });
}

// ---------- salary categories tab ----------
let catTrendChart = null;
// { employmentTypeMode: 'all'|'Formal'|'Contract'|'compare', perCapita: bool,
//   data: { all?: rows, Formal?: rows, Contract?: rows } } - last query's
// response(s), re-rendered on view-toggle without refetching. PRD V1.9 §3.1:
// "compare" fetches Formal+Contract as two plain calls to the SAME
// get_categories_trend()/employment_type filter - no separate "compare"
// concept exists server-side.
let catTrendCache = null;
let catTrendCacheMeta = []; // [{value, label}] for the categories in catTrendCache

const CAT_TREND_COLORS = ['#2f6fed', '#1e9e63', '#e08a2b', '#c0392b', '#8e44ad', '#16a085', '#7f8c8d', '#d35400', '#2980b9', '#27ae60'];
const fmtSignedMoney = (n) => `${n >= 0 ? '+' : ''}${fmtMoney(n)}`;

function renderCatTrendCategoryChecklist(categories) {
  const container = document.getElementById('catTrendCategoryChecklist');
  const previouslyChecked = new Set(Array.from(container.querySelectorAll('input:checked')).map((cb) => cb.value));
  const isFirstRender = container.children.length === 0;
  container.innerHTML = categories
    .map((c) => `<label style="font-weight:normal;display:inline-flex;align-items:center;gap:4px;"><input type="checkbox" value="${c.value}"> ${c.label}</label>`)
    .join('');
  container.querySelectorAll('input').forEach((cb, idx) => {
    cb.checked = isFirstRender ? idx < 2 : previouslyChecked.has(cb.value);
  });
}

function selectedCatTrendCategories() {
  return Array.from(document.querySelectorAll('#catTrendCategoryChecklist input:checked')).map((cb) => cb.value);
}

function currentCatTrendMode() {
  return document.querySelector('input[name="catTrendMode"]:checked').value;
}

function currentCatTrendView() {
  return document.querySelector('input[name="catTrendView"]:checked').value;
}

function currentCatStatBasis() {
  return document.querySelector('input[name="catStatBasis"]:checked').value; // 'total' | 'per_capita'
}

function currentCatEmploymentTypeMode() {
  return document.getElementById('catTrendEmploymentType').value; // 'all' | 'Formal' | 'Contract' | 'compare'
}

function updateCatTrendModeVisibility() {
  const isCompare = currentCatTrendMode() === 'compare';
  document.getElementById('catTrendTrendResult').style.display = isCompare ? 'none' : '';
  document.getElementById('catTrendCompareResult').style.display = isCompare ? '' : 'none';
  document.getElementById('catTrendViewToggleWrap').style.display = isCompare ? 'none' : '';
}

// PRD V1.9 §3.1: "对比模式" is two plain calls to get_categories_trend()
// (employment_type='Formal' and 'Contract'), never a third server-side mode
// - this just describes, for rendering purposes, which of those calls (plus
// the always-available "全部" call) apply to the current selection.
function catSeriesList(cache) {
  if (cache.employmentTypeMode === 'compare') {
    return [
      { key: 'Formal', label: '正式工', rows: cache.data.Formal || [], dashed: false },
      { key: 'Contract', label: '合同工', rows: cache.data.Contract || [], dashed: true },
    ];
  }
  const label = cache.employmentTypeMode === 'Formal' ? '（仅正式工）' : cache.employmentTypeMode === 'Contract' ? '（仅合同工）' : '';
  return [{ key: 'all', label, rows: cache.data.all || [], dashed: false }];
}

function statValue(row, catKey, statKey) {
  const src = statKey === 'categories' ? row.categories : row[statKey];
  return (src && src[catKey]) ?? 0;
}

// Shared by the trend view's percentage mode and the two-point comparison
// table's 涨跌幅 column (PRD V1.7 §3.3): a 0 baseline can't produce a
// meaningful percentage, so both callers show "新增" instead of dividing by
// zero - written once so the two views can't disagree on this edge case.
function pctChange(baseline, current) {
  if (!baseline) return current ? { isNew: true, pct: null } : { isNew: false, pct: 0 };
  return { isNew: false, pct: ((current - baseline) / baseline) * 100 };
}

function pctChangeLabel(baseline, current) {
  const { isNew, pct } = pctChange(baseline, current);
  if (isNew) return '新增';
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
}

function renderCatTrendChartAndTable(cache, categoryMeta) {
  const { perCapita } = cache;
  const view = currentCatTrendView();
  const series = catSeriesList(cache);
  const months = Array.from(new Set(series.flatMap((s) => s.rows.map((r) => r.month)))).sort();

  document.getElementById('catTrendLineCountHint').style.display = series.length > 1 && categoryMeta.length > 4 ? '' : 'none';

  const rowsByMonthPerSeries = series.map((s) => Object.fromEntries(s.rows.map((r) => [r.month, r])));

  const datasets = [];
  categoryMeta.forEach((c, idx) => {
    const color = CAT_TREND_COLORS[idx % CAT_TREND_COLORS.length];
    series.forEach((s, si) => {
      const byMonth = rowsByMonthPerSeries[si];
      const raw = months.map((m) => (byMonth[m] ? statValue(byMonth[m], c.value, perCapita ? 'per_capita' : 'categories') : null));
      const baseline = raw.find((v) => v !== null) ?? 0;
      const plotData = view === 'pct' ? raw.map((v) => (v === null ? null : pctChange(baseline, v).pct)) : raw;
      datasets.push({
        label: `${c.label}${s.label}`,
        data: plotData,
        borderColor: color,
        backgroundColor: color + '26',
        borderDash: s.dashed ? [6, 4] : [],
        tension: 0.25,
        spanGaps: true,
      });
    });
    // PRD V1.9 §2.2: median must be shown alongside the mean, not hidden -
    // charted as a same-color dashed line when there's only one series so
    // it doesn't collide with the solid/dashed = Formal/Contract distinction
    // compare mode already uses (median stays visible in the table either way).
    if (perCapita && series.length === 1) {
      const byMonth = rowsByMonthPerSeries[0];
      const raw = months.map((m) => (byMonth[m] ? statValue(byMonth[m], c.value, 'median') : null));
      const baseline = raw.find((v) => v !== null) ?? 0;
      const plotData = view === 'pct' ? raw.map((v) => (v === null ? null : pctChange(baseline, v).pct)) : raw;
      datasets.push({
        label: `${c.label} 中位数`,
        data: plotData,
        borderColor: color,
        backgroundColor: 'transparent',
        borderDash: [3, 3],
        tension: 0.25,
        spanGaps: true,
      });
    }
  });

  if (catTrendChart) catTrendChart.destroy();
  catTrendChart = new Chart(document.getElementById('catTrendChart'), {
    type: 'line',
    data: { labels: months, datasets },
    options: { scales: { y: { title: { display: true, text: view === 'pct' ? '相对起始月涨跌 (%)' : (perCapita ? '人均金额 (₦)' : '金额 (₦)') } } } },
  });

  const headCells = ['月份'];
  series.forEach((s) => headCells.push(`人数${s.label}`));
  categoryMeta.forEach((c) => {
    series.forEach((s) => {
      if (perCapita) {
        headCells.push(`${c.label}${s.label} 人均`);
        headCells.push(`${c.label}${s.label} 中位数`);
      } else {
        headCells.push(`${c.label}${s.label}`);
      }
    });
  });
  document.getElementById('catTrendTableHead').innerHTML = `<tr>${headCells.map((h) => `<th>${h}</th>`).join('')}</tr>`;

  document.querySelector('#catTrendTable tbody').innerHTML = months
    .map((m) => {
      const cells = [`<td>${m}</td>`];
      series.forEach((s, si) => {
        const row = rowsByMonthPerSeries[si][m];
        cells.push(`<td>${row ? fmtInt(row.headcount) : '-'}</td>`);
      });
      categoryMeta.forEach((c) => {
        series.forEach((s, si) => {
          const row = rowsByMonthPerSeries[si][m];
          if (!row) {
            cells.push(perCapita ? '<td>-</td><td>-</td>' : '<td>-</td>');
            return;
          }
          if (perCapita) {
            cells.push(`<td>${fmtMoney(statValue(row, c.value, 'per_capita'))}</td>`);
            cells.push(`<td>${fmtMoney(statValue(row, c.value, 'median'))}</td>`);
          } else {
            cells.push(`<td>${fmtMoney(statValue(row, c.value, 'categories'))}</td>`);
          }
        });
      });
      return `<tr>${cells.join('')}</tr>`;
    })
    .join('');
}

function renderCatCompareTable(cache, categoryMeta, startMonth, endMonth) {
  const { perCapita, employmentTypeMode, data } = cache;
  if (employmentTypeMode === 'compare') {
    renderCatCompareTree(cache, categoryMeta, startMonth, endMonth);
    return;
  }
  document.getElementById('catCompareTreeView').innerHTML = '';

  const rows = data.all || [];
  const startRow = rows.find((r) => r.month === startMonth);
  const endRow = rows.find((r) => r.month === endMonth);

  const headCells = perCapita ? ['类目', '统计量', '起始月', '结束月', '差值', '涨跌幅'] : ['类目', '起始月金额 (₦)', '结束月金额 (₦)', '差值 (₦)', '涨跌幅'];
  document.getElementById('catCompareTwoPointHead').innerHTML = `<tr>${headCells.map((h) => `<th>${h}</th>`).join('')}</tr>`;

  const bodyRows = [];
  categoryMeta.forEach((c) => {
    if (!startRow || !endRow) {
      bodyRows.push(`<tr><td>${c.label}</td><td colspan="${perCapita ? 5 : 4}" class="muted">起始月或结束月在所选范围内没有数据</td></tr>`);
      return;
    }
    if (perCapita) {
      const meanStart = statValue(startRow, c.value, 'per_capita');
      const meanEnd = statValue(endRow, c.value, 'per_capita');
      const medStart = statValue(startRow, c.value, 'median');
      const medEnd = statValue(endRow, c.value, 'median');
      bodyRows.push(
        `<tr><td rowspan="2">${c.label}</td><td>人均（均值）</td><td>${fmtMoney(meanStart)}</td><td>${fmtMoney(meanEnd)}</td><td>${fmtSignedMoney(meanEnd - meanStart)}</td><td>${pctChangeLabel(meanStart, meanEnd)}</td></tr>`
      );
      bodyRows.push(`<tr><td>中位数</td><td>${fmtMoney(medStart)}</td><td>${fmtMoney(medEnd)}</td><td>${fmtSignedMoney(medEnd - medStart)}</td><td>${pctChangeLabel(medStart, medEnd)}</td></tr>`);
    } else {
      const startVal = statValue(startRow, c.value, 'categories');
      const endVal = statValue(endRow, c.value, 'categories');
      bodyRows.push(`<tr><td>${c.label}</td><td>${fmtMoney(startVal)}</td><td>${fmtMoney(endVal)}</td><td>${fmtSignedMoney(endVal - startVal)}</td><td>${pctChangeLabel(startVal, endVal)}</td></tr>`);
    }
  });
  document.querySelector('#catCompareTwoPointTable tbody').innerHTML = bodyRows.join('');
}

// PRD V1.9 §3.3: 用工类型对比 + 两点比较模式展示"全部/正式工/合同工"三级
// 树形结构，人均模式下均值和中位数两组数字并列展示（不能只做其中一个）。
function renderCatCompareTree(cache, categoryMeta, startMonth, endMonth) {
  document.getElementById('catCompareTwoPointHead').innerHTML = '';
  document.querySelector('#catCompareTwoPointTable tbody').innerHTML = '';
  const { perCapita, data } = cache;

  const pointsFor = (rows, catKey, statKey) => {
    if (!rows) return null;
    const startRow = rows.find((r) => r.month === startMonth);
    const endRow = rows.find((r) => r.month === endMonth);
    if (!startRow || !endRow) return null;
    return { start: statValue(startRow, catKey, statKey), end: statValue(endRow, catKey, statKey) };
  };

  const lineFor = (label, points) => {
    if (!points) return `${label}：起始月或结束月在所选范围内没有数据（如果刚切换了筛选条件，请重新点击"查询"）`;
    const diff = points.end - points.start;
    return `${label}：${fmtMoney(points.start)} → ${fmtMoney(points.end)}（${fmtSignedMoney(diff)}，${pctChangeLabel(points.start, points.end)}）`;
  };

  const buildBlock = (statKey) =>
    categoryMeta
      .map((c) => {
        const all = pointsFor(data.all, c.value, statKey);
        const formal = pointsFor(data.Formal, c.value, statKey);
        const contract = pointsFor(data.Contract, c.value, statKey);
        return `
        <div style="margin-bottom:10px;">
          <strong>${c.label}：</strong>
          <div>${lineFor('全部', all)}</div>
          <div style="padding-left:16px;">├─ ${lineFor('正式工', formal)}</div>
          <div style="padding-left:16px;">└─ ${lineFor('合同工', contract)}</div>
        </div>`;
      })
      .join('');

  document.getElementById('catCompareTreeView').innerHTML = perCapita
    ? `<h4>人均（均值）</h4>${buildBlock('per_capita')}<h4 style="margin-top:16px;">人均（中位数）</h4>${buildBlock('median')}`
    : buildBlock('categories');
}

function initCategoryTab() {
  document.querySelectorAll('input[name="catTrendMode"]').forEach((r) => r.addEventListener('change', updateCatTrendModeVisibility));
  document.querySelectorAll('input[name="catTrendView"]').forEach((r) =>
    r.addEventListener('change', () => {
      if (catTrendCache) renderCatTrendChartAndTable(catTrendCache, catTrendCacheMeta);
    })
  );
  updateCatTrendModeVisibility();

  document.getElementById('catTrendQueryBtn').addEventListener('click', async () => {
    const errEl = document.getElementById('catTrendError');
    errEl.textContent = '';
    const categories = selectedCatTrendCategories();
    if (categories.length === 0) {
      errEl.textContent = '请至少勾选一个薪资类目';
      return;
    }
    const start = document.getElementById('catTrendStart').value;
    const end = document.getElementById('catTrendEnd').value;
    const pageMode = currentCatTrendMode();
    if (pageMode === 'compare' && (!start || !end || start >= end)) {
      errEl.textContent = '两点比较模式下，起始月份必须早于结束月份';
      return;
    }

    const employmentTypeMode = currentCatEmploymentTypeMode();
    const perCapita = currentCatStatBasis() === 'per_capita';
    const baseParams = {
      categories,
      department: document.getElementById('catTrendDept').value || null,
      entity: document.getElementById('catTrendEntity').value || null,
      start_month: start || null,
      end_month: end || null,
      per_capita: perCapita,
    };

    try {
      const data = {};
      if (employmentTypeMode === 'compare') {
        // PRD V1.9 §3.3: two-point mode's tree view also needs the "全部"
        // (combined) numbers alongside Formal/Contract; trend mode's chart
        // only ever plots the Formal/Contract lines, so skip that extra call there.
        const calls = {
          Formal: apiPost('/api/category-trend', { ...baseParams, employment_type: 'Formal' }),
          Contract: apiPost('/api/category-trend', { ...baseParams, employment_type: 'Contract' }),
        };
        if (pageMode === 'compare') calls.all = apiPost('/api/category-trend', { ...baseParams, employment_type: null });
        data.Formal = await calls.Formal;
        data.Contract = await calls.Contract;
        if (calls.all) data.all = await calls.all;
      } else {
        const employment_type = employmentTypeMode === 'all' ? null : employmentTypeMode;
        data.all = await apiPost('/api/category-trend', { ...baseParams, employment_type });
      }

      const categoryMeta = categories.map((v) => metaCategories.find((c) => c.value === v)).filter(Boolean);
      catTrendCache = { employmentTypeMode, perCapita, data };
      catTrendCacheMeta = categoryMeta;

      if (pageMode === 'trend') {
        renderCatTrendChartAndTable(catTrendCache, categoryMeta);
      } else {
        renderCatCompareTable(catTrendCache, categoryMeta, start, end);
      }
    } catch (e) {
      errEl.textContent = e.message;
    }
  });

  document.getElementById('catCompareQueryBtn').addEventListener('click', async () => {
    const rows = await apiPost('/api/category-compare', {
      category: document.getElementById('catCompareCategory').value,
      month: document.getElementById('catCompareMonth').value,
      entity: document.getElementById('catCompareEntity').value || null,
    });
    document.querySelector('#catCompareTable tbody').innerHTML = rows
      .map(
        (r) =>
          `<tr><td>${r.department || '(未标注部门)'}</td><td>${fmtInt(r.headcount)}</td><td>${fmtMoney(r.total)}</td><td>${fmtMoney(r.avg)}</td><td>${r.pct_of_hr_cost.toFixed(1)}%</td></tr>`
      )
      .join('');
  });

  document.getElementById('compQueryBtn').addEventListener('click', async () => {
    const r = await apiPost('/api/composition', {
      month: document.getElementById('compMonth').value,
      department: document.getElementById('compDept').value || null,
      entity: document.getElementById('compEntity').value || null,
    });
    renderComposition(r);
  });
}

function renderComposition(r) {
  const el = document.getElementById('compResult');
  if (!r.categories.length || !r.hr_cost) {
    el.innerHTML = '<div class="muted">没有查到数据</div>';
    return;
  }
  const rowsHtml = r.categories
    .map(
      (c) => `
      <tr>
        <td>${c.label}</td>
        <td>${fmtMoney(c.total)}</td>
        <td style="width:40%;">
          <div style="background:var(--bg);border-radius:4px;overflow:hidden;height:14px;">
            <div style="width:${Math.min(c.pct, 100).toFixed(1)}%;background:#2f6fed;height:100%;"></div>
          </div>
        </td>
        <td>${c.pct.toFixed(1)}%</td>
      </tr>`
    )
    .join('');
  el.innerHTML = `
    <div class="stat" style="max-width:260px;margin-bottom:12px;"><div class="label">HR Cost 合计</div><div class="value">${fmtMoney(r.hr_cost)}</div></div>
    <table>
      <thead><tr><th>类目</th><th>金额 (₦)</th><th>占比</th><th></th></tr></thead>
      <tbody>${rowsHtml}</tbody>
    </table>
  `;
}

const pctStr = (p) => (p === null || p === undefined ? '' : ` (${p.toFixed(1)}%)`);

function flatItemLabel(item) {
  if (item.key !== 'headcount') return item.label;
  const net = (item.joiners_count || 0) - (item.leavers_count || 0);
  const direction = net > 0 ? `净增${net}人` : net < 0 ? `净减${Math.abs(net)}人` : '净变化0人';
  return `人数变化：${direction}（新入职${item.joiners_count}人+${fmtMoney(item.joiners_cost)}，离职${item.leavers_count}人-${fmtMoney(item.leavers_cost)}）`;
}

function renderAttribution(r) {
  const el = document.getElementById('attrResult');
  const movers = (list, sign) =>
    list.map((m) => `<li>${m.name || '(未知)'}（${m.job_grade || '-'}）: ${sign}${fmtMoney(Math.abs(m.hr_cost))}</li>`).join('');

  const items = r.flat_items || [];
  const flatRows = items
    .map(
      (item, idx) =>
        `<tr><td>${idx + 1}</td><td>${flatItemLabel(item)}</td><td>${item.amount >= 0 ? '+' : ''}${fmtMoney(item.amount)}</td><td>${pctStr(item.pct)}</td></tr>`
    )
    .join('');
  const itemsSum = items.reduce((s, item) => s + item.amount, 0);

  const labelRows = (r.behavior_labels || [])
    .map(
      (l) =>
        `<tr><td>${l.label}</td><td>正式工 ${l.count_formal} / 合同工 ${l.count_contract}</td><td>${l.amount >= 0 ? '+' : ''}${fmtMoney(l.amount)}${pctStr(l.pct_of_net_change)}</td></tr>`
    )
    .join('');

  el.innerHTML = `
    <div class="summary-grid">
      <div class="stat"><div class="label">${r.prev_month} 总成本</div><div class="value">${fmtMoney(r.prev_total)}</div></div>
      <div class="stat"><div class="label">${r.cur_month} 总成本</div><div class="value">${fmtMoney(r.cur_total)}</div></div>
      <div class="stat"><div class="label">净变化</div><div class="value">${r.net_change >= 0 ? '+' : ''}${fmtMoney(r.net_change)}</div></div>
      <div class="stat"><div class="label">校验</div><div class="value">${r.reconciled ? '✓ 吻合' : '✗ 不吻合，需排查'}</div></div>
    </div>

    <h4 style="margin-top:16px;">归因拆解（按贡献金额绝对值从大到小排序）</h4>
    <table>
      <thead><tr><th>#</th><th>归因项</th><th>金额</th><th>占净变化</th></tr></thead>
      <tbody>${flatRows}</tbody>
    </table>
    <div class="muted" style="margin-top:6px;">校验：以上${items.length}项相加 = ${fmtMoney(itemsSum)}（${r.reconciled ? '✓ 与净变化吻合' : '✗ 与净变化不吻合，需排查'}）</div>

    ${r.anomalies && r.anomalies.length ? `<ul class="issue-list severe" style="margin-top:12px;">${r.anomalies.map((a) => `<li>⚠️ ${a}</li>`).join('')}</ul>` : ''}

    <h4 style="margin-top:20px;">按变动性质分类的补充说明（一人可能同时命中多个标签，人数/金额不能跨行相加；以上面的归因拆解为准，这里仅作叙事参考）</h4>
    <table>
      <thead><tr><th>标签</th><th>人数</th><th>涉及成本</th></tr></thead>
      <tbody>${labelRows}</tbody>
    </table>

    <div class="row" style="margin-top:12px;">
      <div>
        <strong>成本涨幅最大：</strong>
        <ul>${movers(r.top_increases, '+')}</ul>
      </div>
      <div>
        <strong>成本降幅最大：</strong>
        <ul>${movers(r.top_decreases, '-')}</ul>
      </div>
    </div>
    ${Object.keys(r.leaver_reasons || {}).length ? `<div><strong>离职原因分布：</strong> ${Object.entries(r.leaver_reasons).map(([k, v]) => `${k} × ${v}`).join('，')}</div>` : ''}
  `;
}

// ---------- chat tab ----------
function appendChatMsg(role, text) {
  const log = document.getElementById('chatLog');
  const div = document.createElement('div');
  div.className = `chat-msg ${role}`;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function initChatTab() {
  const send = async () => {
    const input = document.getElementById('chatInput');
    const question = input.value.trim();
    if (!question) return;
    appendChatMsg('user', question);
    input.value = '';
    const thinking = appendChatMsg('assistant', '思考中…');
    try {
      const resp = await apiPost('/api/chat', { question });
      thinking.textContent = resp.answer;
    } catch (e) {
      thinking.textContent = '出错了: ' + e.message;
    }
  };
  document.getElementById('chatSendBtn').addEventListener('click', send);
  document.getElementById('chatInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
}

// ---------- permissions tab (admin only) ----------
let entityDepartmentMap = {};

async function loadUserList() {
  const users = await apiJson('/api/auth/users');
  const select = document.getElementById('permUserSelect');
  const current = select.value;
  select.innerHTML = users.map((u) => `<option value="${u.id}">${u.username}（${u.role}）</option>`).join('');
  if (users.some((u) => String(u.id) === current)) select.value = current;

  document.getElementById('userListTable').innerHTML = users
    .map(
      (u) => `
      <tr>
        <td>${u.username}</td>
        <td>${u.role === 'admin' ? '管理员' : '只读'}</td>
        <td><span class="badge ${u.is_active ? 'confirmed' : 'rejected'}">${u.is_active ? '启用' : '已禁用'}</span></td>
        <td>
          <button class="secondary" style="padding:2px 8px;font-size:12px;" onclick="resetUserPassword(${u.id}, '${u.username}')">重置密码</button>
          <button class="${u.is_active ? 'danger' : 'secondary'}" style="padding:2px 8px;font-size:12px;margin-left:4px;" onclick="toggleUserActive(${u.id}, ${!u.is_active}, '${u.username}')">${u.is_active ? '禁用' : '启用'}</button>
        </td>
      </tr>`
    )
    .join('');
  return users;
}

async function resetUserPassword(userId, username) {
  const newPassword = prompt(`为账号「${username}」设置新密码：`);
  if (!newPassword) return;
  try {
    await apiPost(`/api/auth/users/${userId}/reset-password`, { new_password: newPassword });
    alert('密码已重置');
  } catch (e) {
    alert('重置失败：' + e.message);
  }
}

async function toggleUserActive(userId, nextActive, username) {
  if (!nextActive && !confirm(`确定要禁用账号「${username}」吗？禁用后该账号无法登录（历史记录会保留）。`)) return;
  try {
    await apiPost(`/api/auth/users/${userId}/active`, { is_active: nextActive });
    await loadUserList();
  } catch (e) {
    alert('操作失败：' + e.message);
  }
}

async function loadEntityDepartments() {
  entityDepartmentMap = await apiJson('/api/auth/entity-departments');
  renderPermScopeChecklist();
}

function renderPermScopeChecklist() {
  const entities = Object.keys(entityDepartmentMap);
  const container = document.getElementById('permScopeChecklist');
  if (entities.length === 0) {
    container.innerHTML = '<div class="muted">还没有任何已入库的部门/实体数据，先上传并确认一个月份的数据再来分配权限。</div>';
    return;
  }
  container.innerHTML = entities
    .map((entity) => {
      const depts = entityDepartmentMap[entity] || [];
      return `
      <div class="scope-entity-block">
        <label><input type="checkbox" class="entity-check" data-entity="${entity}"> 整个实体：${entity}</label>
        <div class="scope-dept-list">
          ${depts
            .map((d) => `<label class="dept-label" data-entity="${entity}"><input type="checkbox" class="dept-check" data-entity="${entity}" data-dept="${d}"> ${d}</label>`)
            .join('')}
        </div>
      </div>`;
    })
    .join('');

  container.querySelectorAll('.entity-check').forEach((cb) => {
    cb.addEventListener('change', () => {
      const entity = cb.dataset.entity;
      container.querySelectorAll(`.dept-check[data-entity="${CSS.escape(entity)}"]`).forEach((deptCb) => {
        deptCb.disabled = cb.checked;
        if (cb.checked) deptCb.checked = false;
        deptCb.closest('label').classList.toggle('disabled', cb.checked);
      });
    });
  });
}

async function loadCurrentPermissions() {
  const userId = document.getElementById('permUserSelect').value;
  if (!userId) {
    document.getElementById('permCurrentList').innerHTML = '';
    return;
  }
  const includeRevoked = document.getElementById('permShowRevoked').checked;
  const grants = await apiJson(`/api/auth/users/${userId}/permissions?include_revoked=${includeRevoked}`);
  const typeLabel = { entity: '整体实体', entity_department: '实体+部门' };
  document.getElementById('permCurrentList').innerHTML = grants.length
    ? grants
        .map(
          (g) => `
      <tr${g.is_active ? '' : ' style="opacity:0.55;"'}>
        <td>${typeLabel[g.scope_type] || g.scope_type}</td>
        <td>${g.entity}</td>
        <td>${g.department1 || '<span class="muted">（全部）</span>'}</td>
        <td>${g.is_active ? '<span class="badge confirmed">生效中</span>' : '<span class="badge rejected">已撤销</span>'}</td>
        <td class="muted" style="font-size:12px;">
          ${g.granted_by || '-'} · ${new Date(g.granted_time).toLocaleString('zh-CN')}
          ${g.revoked_by ? `<br>撤销：${g.revoked_by} · ${new Date(g.revoked_time).toLocaleString('zh-CN')}` : ''}
        </td>
        <td>${g.is_active ? `<button class="danger" style="padding:2px 8px;font-size:12px;" onclick="revokePermission(${userId}, ${g.id})">撤销</button>` : ''}</td>
      </tr>`
        )
        .join('')
    : '<tr><td colspan="6" class="muted">暂无授权（该账号目前看不到任何数据）</td></tr>';
}

async function revokePermission(userId, grantId) {
  if (!confirm('确定要撤销这条授权规则吗？')) return;
  await apiFetch(`/api/auth/users/${userId}/permissions/${grantId}`, { method: 'DELETE' });
  await loadCurrentPermissions();
}

async function loadOperationLog() {
  const logs = await apiJson('/api/auth/operation-log');
  const typeLabel = { upload: '上传', correct: '修正', delete: '删除' };
  document.getElementById('opLogList').innerHTML = logs.length
    ? logs
        .map(
          (l) => `
      <div class="upload-list-item">
        <span>${new Date(l.operation_time).toLocaleString('zh-CN')} · ${l.operator} · ${typeLabel[l.operation_type] || l.operation_type}${l.target_month ? ' · ' + l.target_month : ''}</span>
        <span class="muted">${l.detail || ''}</span>
      </div>`
        )
        .join('')
    : '<div class="muted">暂无操作记录</div>';
}

async function loadDownloadLog() {
  const logs = await apiJson('/api/auth/download-log');
  document.getElementById('downloadLogList').innerHTML = logs.length
    ? logs
        .map(
          (l) => `
      <div class="upload-list-item">
        <span>${new Date(l.download_time).toLocaleString('zh-CN')} · ${l.username} · ${l.entity_scope || '-'} / ${l.department_scope || '-'} · ${l.month_range_start} 至 ${l.month_range_end}${l.salary_types ? ' · ' + l.salary_types.split(',').map((t) => SALARY_TYPE_LABEL[t] || t).join('+') : ''}</span>
        <span class="muted">${fmtInt(l.row_count)} 条记录</span>
      </div>`
        )
        .join('')
    : '<div class="muted">暂无下载记录</div>';
}

function initPermissionsTab() {
  if (currentUserRole !== 'admin') return;

  document.getElementById('createUserBtn').addEventListener('click', async () => {
    const errEl = document.getElementById('createUserError');
    errEl.textContent = '';
    try {
      await apiPost('/api/auth/users', {
        username: document.getElementById('newUserUsername').value.trim(),
        password: document.getElementById('newUserPassword').value,
        role: document.getElementById('newUserRole').value,
      });
      document.getElementById('newUserUsername').value = '';
      document.getElementById('newUserPassword').value = '';
      await loadUserList();
    } catch (e) {
      errEl.textContent = e.message;
    }
  });

  document.getElementById('permUserSelect').addEventListener('change', loadCurrentPermissions);
  document.getElementById('permShowRevoked').addEventListener('change', loadCurrentPermissions);

  document.getElementById('grantPermBtn').addEventListener('click', async () => {
    const userId = document.getElementById('permUserSelect').value;
    const errEl = document.getElementById('grantPermError');
    errEl.textContent = '';
    if (!userId) return;

    const container = document.getElementById('permScopeChecklist');
    const grants = [];
    container.querySelectorAll('.entity-check:checked').forEach((cb) => {
      grants.push({ scope_type: 'entity', entity: cb.dataset.entity });
    });
    container.querySelectorAll('.dept-check:checked').forEach((cb) => {
      grants.push({ scope_type: 'entity_department', entity: cb.dataset.entity, department1: cb.dataset.dept });
    });

    if (grants.length === 0) {
      errEl.textContent = '请至少勾选一个实体或部门';
      return;
    }

    try {
      for (const payload of grants) {
        await apiPost(`/api/auth/users/${userId}/permissions`, payload);
      }
      container.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
        cb.checked = false;
        cb.disabled = false;
        cb.closest('label').classList.remove('disabled');
      });
      await loadCurrentPermissions();
    } catch (e) {
      errEl.textContent = '授权失败：' + e.message;
    }
  });

  document.querySelector('.tab-btn[data-tab="permissions"]').addEventListener('click', async () => {
    await loadUserList();
    await loadEntityDepartments();
    await loadCurrentPermissions();
    await loadOperationLog();
    await loadDownloadLog();
  });

  loadUserList();
  loadEntityDepartments();
}

(async function main() {
  await initShell();
  initUploadTab();
  initTrendTab();
  initCategoryTab();
  initExportTab();
  initChatTab();
  initPermissionsTab();
  await populateMeta();
})();
