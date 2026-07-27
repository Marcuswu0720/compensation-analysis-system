const fmtMoney = (n) => '₦' + Number(n || 0).toLocaleString('en-NG', { maximumFractionDigits: 2 });
const fmtInt = (n) => Number(n || 0).toLocaleString('en-NG');
const fmtDateTime = (d) => new Date(d).toLocaleString(currentLang() === 'en' ? 'en-US' : 'zh-CN');
const SALARY_TYPE_LABEL = () => ({ base: t('salary_type.base'), bonus: t('salary_type.bonus'), backpay: t('salary_type.backpay') });
// Mirrors backend compute/categories.py's COMPOSITION_REAL_FIELDS - the only
// categories a 补发批次 upload can be tagged with (see routers/upload.py's
// validation). Kept as a plain list here rather than derived from
// metaCategories since it's a fixed subset, not "every category that page
// happens to expose".
const BACKPAY_CATEGORY_KEYS = ['basic_salary_actual', 'performance_bonus', 'commission_bonus', 'overtime_amount', 'other_income', 'employer_statutory_cost'];
const STATUS_LABEL = () => ({
  pending_review: t('upload.status.pending_review'),
  confirmed: t('upload.status.confirmed'),
  rejected: t('upload.status.rejected'),
  superseded: t('upload.status.superseded'),
});

let currentBatchId = null;
let trendChart = null;
let currentUserRole = null;
let metaCategories = []; // [{value, label}] - cached from /api/meta, see populateMeta()

// ---------- shell: tabs + whoami ----------
async function initShell() {
  try {
    const me = await apiJson('/api/auth/me');
    currentUserRole = me.role;
    document.getElementById('whoami').textContent = `${me.username}（${me.role === 'admin' ? t('common.admin') : t('common.viewer')}）`;
  } catch (e) {
    return;
  }
  mountLangSwitch(document.getElementById('langSwitchHost'));
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

// batch.category is one of BACKPAY_CATEGORY_KEYS (or null) - looked up
// against the cached /api/meta category list so the label follows the
// current UI language the same way every other category label does.
function backpayCategoryLabel(value) {
  if (!value) return '';
  const cat = metaCategories.find((c) => c.value === value);
  return cat ? categoryLabel(cat) : value;
}

function renderBatch(batch) {
  currentBatchId = batch.id;
  const card = document.getElementById('reviewCard');
  card.style.display = 'block';
  document.getElementById('reviewMonth').textContent = `${batch.month}（${batch.original_filename}）`;
  const salaryTypeLabel = SALARY_TYPE_LABEL()[batch.salary_type] || batch.salary_type;
  document.getElementById('reviewSalaryType').textContent = batch.category
    ? `${salaryTypeLabel} · ${backpayCategoryLabel(batch.category)}`
    : salaryTypeLabel;

  const s = batch.summary;
  if (batch.salary_type === 'base') {
    const deltaText = s.headcount_delta === null || s.headcount_delta === undefined
      ? t('upload.stat.no_prior_month')
      : (s.headcount_delta >= 0 ? `+${s.headcount_delta}` : s.headcount_delta);
    document.getElementById('reviewSummary').innerHTML = `
      <div class="stat"><div class="label">${t('upload.stat.headcount_total')}</div><div class="value">${fmtInt(s.headcount_total)}</div></div>
      <div class="stat"><div class="label">${t('upload.stat.headcount_delta')}</div><div class="value">${deltaText}</div></div>
      <div class="stat"><div class="label">${t('upload.stat.total_hr_cost')}</div><div class="value">${fmtMoney(s.total_hr_cost)}</div></div>
      <div class="stat"><div class="label">${t('upload.stat.resigned_this_month')}</div><div class="value">${fmtInt(s.headcount_resigned_this_month)}</div></div>
    `;
  } else {
    document.getElementById('reviewSummary').innerHTML = `
      <div class="stat"><div class="label">${t('upload.stat.row_count')}</div><div class="value">${fmtInt(s.row_count)}</div></div>
      <div class="stat"><div class="label">${t('upload.stat.matched_count')}</div><div class="value">${fmtInt(s.matched_count)}</div></div>
      <div class="stat"><div class="label">${t('upload.stat.unmatched_count')}</div><div class="value">${fmtInt(s.unmatched_count)}</div></div>
      <div class="stat"><div class="label">${t('upload.stat.total_amount')}</div><div class="value">${fmtMoney(s.total_amount)}</div></div>
    `;
  }

  const issuesEl = document.getElementById('reviewIssues');
  if (batch.issues.length === 0) {
    issuesEl.innerHTML = `<li style="background:rgba(30,158,99,0.12);border-color:rgba(30,158,99,0.3);">${t('upload.no_issues')}</li>`;
  } else {
    issuesEl.innerHTML = batch.issues
      .map((i) => `<li class="${issueSeverity(i)}"><strong>[${i.issue_type}]</strong> ${i.issue_detail}</li>`)
      .join('');
  }

  const busy = batch.status !== 'pending_review';
  document.getElementById('confirmBtn').disabled = busy;
  document.getElementById('rejectBtn').disabled = busy;
  document.getElementById('confirmBtn').textContent = batch.status === 'confirmed' ? t('upload.confirmed') : t('upload.confirm');
  document.getElementById('reconciliationExportBtn').style.display = batch.salary_type === 'base' ? '' : 'none';
}

async function loadUploadHistory() {
  const statusFilter = document.getElementById('historyStatusFilter')?.value || '';
  const qs = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : '';
  const list = await apiJson(`/api/upload${qs}`);
  const el = document.getElementById('uploadHistory');
  if (list.length === 0) {
    el.innerHTML = `<div class="muted">${t('upload.no_history')}</div>`;
    return;
  }
  const isAdmin = currentUserRole === 'admin';
  const salaryTypeLabel = SALARY_TYPE_LABEL();
  const statusLabel = STATUS_LABEL();
  el.innerHTML = list
    .map(
      (b) => `
      <div class="upload-list-item">
        <span>${b.month} · ${salaryTypeLabel[b.salary_type] || b.salary_type}${b.category ? ' (' + backpayCategoryLabel(b.category) + ')' : ''} · ${b.original_filename} · ${t('upload.uploaded_by')} ${b.uploaded_by} · ${fmtDateTime(b.uploaded_at)}</span>
        <span>
          <span class="badge ${b.status}">${statusLabel[b.status] || b.status}</span>
          ${isAdmin && b.status === 'pending_review' ? `
            <button class="secondary" style="padding:2px 8px;font-size:12px;margin-left:6px;" onclick="reopenBatch(${b.id})">${t('upload.action.view')}</button>
          ` : ''}
          ${isAdmin && b.status === 'confirmed' ? `
            <button class="secondary" style="padding:2px 8px;font-size:12px;margin-left:6px;" onclick="reassignBatchMonth(${b.id}, '${b.month}')">${t('upload.action.reassign_month')}</button>
            <button class="danger" style="padding:2px 8px;font-size:12px;margin-left:4px;" onclick="deleteBatch(${b.id}, '${b.month}')">${t('upload.action.delete')}</button>
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
    alert(t('upload.open_batch_failed') + e.message);
  }
}

async function reassignBatchMonth(batchId, currentMonth) {
  const newMonth = prompt(t('upload.reassign_prompt', { month: currentMonth }), currentMonth);
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
    alert(t('upload.reassign_failed') + e.message);
  }
}

async function deleteBatch(batchId, month) {
  if (!confirm(t('upload.delete_confirm', { month }))) return;
  try {
    await apiJson(`/api/upload/${batchId}`, { method: 'DELETE' });
    await loadUploadHistory();
    await populateMeta();
  } catch (e) {
    alert(t('upload.delete_failed') + e.message);
  }
}

function initUploadTab() {
  if (currentUserRole !== 'admin') return; // viewers never touch the upload router - see routers/upload.py's require_admin

  const salaryTypeSelect = document.getElementById('uploadSalaryType');
  const backpayCategoryWrap = document.getElementById('uploadBackpayCategoryWrap');
  const backpayCategoryHint = document.getElementById('uploadBackpayCategoryHint');
  const syncBackpayCategoryVisibility = () => {
    const isBackpay = salaryTypeSelect.value === 'backpay';
    backpayCategoryWrap.style.display = isBackpay ? '' : 'none';
    backpayCategoryHint.style.display = isBackpay ? '' : 'none';
    if (!isBackpay) document.getElementById('uploadBackpayCategory').value = '';
  };
  salaryTypeSelect.addEventListener('change', syncBackpayCategoryVisibility);
  syncBackpayCategoryVisibility();

  document.getElementById('uploadBtn').addEventListener('click', async () => {
    const month = document.getElementById('uploadMonth').value;
    const salaryType = salaryTypeSelect.value;
    const category = salaryType === 'backpay' ? document.getElementById('uploadBackpayCategory').value : '';
    const fileInput = document.getElementById('uploadFile');
    const errEl = document.getElementById('uploadError');
    errEl.textContent = '';
    if (!month || !fileInput.files[0]) {
      errEl.textContent = t('upload.please_select');
      return;
    }
    const form = new FormData();
    form.append('file', fileInput.files[0]);
    try {
      const categoryParam = category ? `&category=${encodeURIComponent(category)}` : '';
      const batch = await apiJson(
        `/api/upload?month=${encodeURIComponent(month)}&salary_type=${encodeURIComponent(salaryType)}${categoryParam}`,
        { method: 'POST', body: form }
      );
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
      await downloadBlob(`/api/upload/${currentBatchId}/reconciliation-export`, {}, currentLang() === 'en' ? 'reconciliation.xlsx' : '分部门核对.xlsx');
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
    el.innerHTML = (withEmpty ? `<option value="">${t('common.all')}</option>` : '') + values.map((v) => `<option value="${v}">${v}</option>`).join('');
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
    el.innerHTML = meta.categories.map((c) => `<option value="${c.value}">${categoryLabel(c)}</option>`).join('');
    if (meta.categories.some((c) => c.value === current)) el.value = current;
  };
  fillCategorySelect('catCompareCategory');
  renderCatTrendCategoryChecklist(meta.categories);

  const backpayCategorySelect = document.getElementById('uploadBackpayCategory');
  const backpayCurrent = backpayCategorySelect.value;
  const backpayOptions = meta.categories.filter((c) => BACKPAY_CATEGORY_KEYS.includes(c.value));
  backpayCategorySelect.innerHTML =
    `<option value="" data-i18n="upload.backpay_category.none">${t('upload.backpay_category.none')}</option>` +
    backpayOptions.map((c) => `<option value="${c.value}">${categoryLabel(c)}</option>`).join('');
  if (backpayOptions.some((c) => c.value === backpayCurrent)) backpayCategorySelect.value = backpayCurrent;

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
    throw new Error(data.detail || `Request failed (${resp.status})`);
  }
  const disposition = resp.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename\*=UTF-8''([^;]+)/);
  const filename = match ? decodeURIComponent(match[1]) : fallbackFilename || (currentLang() === 'en' ? 'export.xlsx' : '导出.xlsx');
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
      errEl.textContent = t('export.please_select_type');
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
      await downloadPost('/api/export/detail', payload, currentLang() === 'en' ? 'salary_detail_export.xlsx' : '薪酬明细导出.xlsx');
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
        { label: t('trend.chart.hr_cost'), data: costData, borderColor: '#2f6fed', backgroundColor: 'rgba(47,111,237,0.15)', yAxisID: 'y', tension: 0.25 },
        { label: t('trend.chart.headcount'), data: headcountData, borderColor: '#1e9e63', backgroundColor: 'rgba(30,158,99,0.15)', yAxisID: 'y1', tension: 0.25 },
      ],
    },
    options: {
      scales: {
        y: { position: 'left', title: { display: true, text: 'HR Cost (₦)' } },
        y1: { position: 'right', title: { display: true, text: t('trend.chart.headcount') }, grid: { drawOnChartArea: false } },
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
          errEl.textContent = t('trend.compare_order_error');
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
    .map((c) => `<label style="font-weight:normal;display:inline-flex;align-items:center;gap:4px;"><input type="checkbox" value="${c.value}"> ${categoryLabel(c)}</label>`)
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

function currentCatShowMedian() {
  return currentCatStatBasis() === 'per_capita' && document.getElementById('catShowMedian').checked;
}

function currentCatEmploymentTypeMode() {
  return document.getElementById('catTrendEmploymentType').value; // 'all' | 'Formal' | 'Contract' | 'compare'
}

function updateCatStatBasisVisibility() {
  document.getElementById('catShowMedianWrap').style.display = currentCatStatBasis() === 'per_capita' ? 'inline-flex' : 'none';
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
      { key: 'Formal', label: t('cat.employment_type.formal_short'), rows: cache.data.Formal || [], dashed: false },
      { key: 'Contract', label: t('cat.employment_type.contract_short'), rows: cache.data.Contract || [], dashed: true },
    ];
  }
  const label = cache.employmentTypeMode === 'Formal' ? t('cat.employment_type.formal_suffix') : cache.employmentTypeMode === 'Contract' ? t('cat.employment_type.contract_suffix') : '';
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
  if (isNew) return t('cat.new');
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
}

function renderCatTrendChartAndTable(cache, categoryMeta) {
  const { perCapita } = cache;
  const showMedian = perCapita && currentCatShowMedian();
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
        label: `${categoryLabel(c)}${s.label}`,
        data: plotData,
        borderColor: color,
        backgroundColor: color + '26',
        borderDash: s.dashed ? [6, 4] : [],
        tension: 0.25,
        spanGaps: true,
      });
    });
    // Median line is opt-in (a checkbox next to 统计口径, off by default) -
    // charted as a same-color dashed line when there's only one series so
    // it doesn't collide with the solid/dashed = Formal/Contract distinction
    // compare mode already uses.
    if (showMedian && series.length === 1) {
      const byMonth = rowsByMonthPerSeries[0];
      const raw = months.map((m) => (byMonth[m] ? statValue(byMonth[m], c.value, 'median') : null));
      const baseline = raw.find((v) => v !== null) ?? 0;
      const plotData = view === 'pct' ? raw.map((v) => (v === null ? null : pctChange(baseline, v).pct)) : raw;
      datasets.push({
        label: `${categoryLabel(c)} ${t('cat.median')}`,
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
    options: { scales: { y: { title: { display: true, text: view === 'pct' ? t('cat.chart.pct_axis') : (perCapita ? t('cat.chart.per_capita_axis') : t('cat.chart.amount_axis')) } } } },
  });

  const headCells = [t('cat.table.month')];
  series.forEach((s) => headCells.push(`${t('cat.headcount_prefix')}${s.label}`));
  categoryMeta.forEach((c) => {
    series.forEach((s) => {
      if (perCapita) {
        headCells.push(`${categoryLabel(c)}${s.label} ${t('cat.stat_basis.per_capita')}`);
        if (showMedian) headCells.push(`${categoryLabel(c)}${s.label} ${t('cat.median')}`);
      } else {
        headCells.push(`${categoryLabel(c)}${s.label}`);
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
            cells.push(perCapita && showMedian ? '<td>-</td><td>-</td>' : '<td>-</td>');
            return;
          }
          if (perCapita) {
            cells.push(`<td>${fmtMoney(statValue(row, c.value, 'per_capita'))}</td>`);
            if (showMedian) cells.push(`<td>${fmtMoney(statValue(row, c.value, 'median'))}</td>`);
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
  const showMedian = perCapita && currentCatShowMedian();
  if (employmentTypeMode === 'compare') {
    renderCatCompareTree(cache, categoryMeta, startMonth, endMonth);
    return;
  }
  document.getElementById('catCompareTreeView').innerHTML = '';

  const rows = data.all || [];
  const startRow = rows.find((r) => r.month === startMonth);
  const endRow = rows.find((r) => r.month === endMonth);

  const headCells = perCapita
    ? showMedian
      ? [t('cat.table.category'), t('cat.table.statistic'), t('cat.table.start_month'), t('cat.table.end_month'), t('cat.table.diff'), t('cat.table.pct_change')]
      : [t('cat.table.category'), t('cat.table.per_capita_start'), t('cat.table.per_capita_end'), t('cat.table.diff_amount'), t('cat.table.pct_change')]
    : [t('cat.table.category'), t('cat.table.start_month_amount'), t('cat.table.end_month_amount'), t('cat.table.diff_amount'), t('cat.table.pct_change')];
  document.getElementById('catCompareTwoPointHead').innerHTML = `<tr>${headCells.map((h) => `<th>${h}</th>`).join('')}</tr>`;

  const bodyRows = [];
  categoryMeta.forEach((c) => {
    if (!startRow || !endRow) {
      bodyRows.push(`<tr><td>${categoryLabel(c)}</td><td colspan="${headCells.length - 1}" class="muted">${t('cat.no_data_in_range')}</td></tr>`);
      return;
    }
    if (perCapita) {
      const meanStart = statValue(startRow, c.value, 'per_capita');
      const meanEnd = statValue(endRow, c.value, 'per_capita');
      if (!showMedian) {
        bodyRows.push(
          `<tr><td>${categoryLabel(c)}</td><td>${fmtMoney(meanStart)}</td><td>${fmtMoney(meanEnd)}</td><td>${fmtSignedMoney(meanEnd - meanStart)}</td><td>${pctChangeLabel(meanStart, meanEnd)}</td></tr>`
        );
        return;
      }
      const medStart = statValue(startRow, c.value, 'median');
      const medEnd = statValue(endRow, c.value, 'median');
      bodyRows.push(
        `<tr><td rowspan="2">${categoryLabel(c)}</td><td>${t('cat.per_capita_mean')}</td><td>${fmtMoney(meanStart)}</td><td>${fmtMoney(meanEnd)}</td><td>${fmtSignedMoney(meanEnd - meanStart)}</td><td>${pctChangeLabel(meanStart, meanEnd)}</td></tr>`
      );
      bodyRows.push(`<tr><td>${t('cat.median')}</td><td>${fmtMoney(medStart)}</td><td>${fmtMoney(medEnd)}</td><td>${fmtSignedMoney(medEnd - medStart)}</td><td>${pctChangeLabel(medStart, medEnd)}</td></tr>`);
    } else {
      const startVal = statValue(startRow, c.value, 'categories');
      const endVal = statValue(endRow, c.value, 'categories');
      bodyRows.push(`<tr><td>${categoryLabel(c)}</td><td>${fmtMoney(startVal)}</td><td>${fmtMoney(endVal)}</td><td>${fmtSignedMoney(endVal - startVal)}</td><td>${pctChangeLabel(startVal, endVal)}</td></tr>`);
    }
  });
  document.querySelector('#catCompareTwoPointTable tbody').innerHTML = bodyRows.join('');
}

// PRD V1.9 §3.3: 用工类型对比 + 两点比较模式展示"全部/正式工/合同工"三级
// 树形结构；人均模式下默认只展示均值，勾选"同时显示中位数"后才追加中位数
// 区块（用户明确要求默认不展示中位数，只作为一个可选开关）。
function renderCatCompareTree(cache, categoryMeta, startMonth, endMonth) {
  document.getElementById('catCompareTwoPointHead').innerHTML = '';
  document.querySelector('#catCompareTwoPointTable tbody').innerHTML = '';
  const { perCapita, data } = cache;
  const showMedian = perCapita && currentCatShowMedian();

  const pointsFor = (rows, catKey, statKey) => {
    if (!rows) return null;
    const startRow = rows.find((r) => r.month === startMonth);
    const endRow = rows.find((r) => r.month === endMonth);
    if (!startRow || !endRow) return null;
    return { start: statValue(startRow, catKey, statKey), end: statValue(endRow, catKey, statKey) };
  };

  const lineFor = (label, points) => {
    if (!points) return `${label}：${t('cat.no_data_in_range_retry')}`;
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
          <strong>${categoryLabel(c)}：</strong>
          <div>${lineFor(t('cat.employment_type.all'), all)}</div>
          <div style="padding-left:16px;">├─ ${lineFor(t('cat.employment_type.formal_short'), formal)}</div>
          <div style="padding-left:16px;">└─ ${lineFor(t('cat.employment_type.contract_short'), contract)}</div>
        </div>`;
      })
      .join('');

  document.getElementById('catCompareTreeView').innerHTML = perCapita
    ? showMedian
      ? `<h4>${t('cat.per_capita_mean')}</h4>${buildBlock('per_capita')}<h4 style="margin-top:16px;">${t('cat.per_capita_median')}</h4>${buildBlock('median')}`
      : `<h4>${t('cat.per_capita_mean')}</h4>${buildBlock('per_capita')}`
    : buildBlock('categories');
}

function rerenderCatTrendResult() {
  if (!catTrendCache) return;
  if (currentCatTrendMode() === 'trend') {
    renderCatTrendChartAndTable(catTrendCache, catTrendCacheMeta);
  } else {
    renderCatCompareTable(catTrendCache, catTrendCacheMeta, document.getElementById('catTrendStart').value, document.getElementById('catTrendEnd').value);
  }
}

function initCategoryTab() {
  document.querySelectorAll('input[name="catTrendMode"]').forEach((r) => r.addEventListener('change', updateCatTrendModeVisibility));
  document.querySelectorAll('input[name="catTrendView"]').forEach((r) => r.addEventListener('change', rerenderCatTrendResult));
  // Switching 统计口径 (total vs per_capita) needs a fresh /api/category-trend
  // call - unlike view/median, which just re-render already-fetched data -
  // so this only toggles the checkbox's visibility, not a re-render.
  document.querySelectorAll('input[name="catStatBasis"]').forEach((r) => r.addEventListener('change', updateCatStatBasisVisibility));
  document.getElementById('catShowMedian').addEventListener('change', rerenderCatTrendResult);
  updateCatTrendModeVisibility();
  updateCatStatBasisVisibility();

  document.getElementById('catTrendQueryBtn').addEventListener('click', async () => {
    const errEl = document.getElementById('catTrendError');
    errEl.textContent = '';
    const categories = selectedCatTrendCategories();
    if (categories.length === 0) {
      errEl.textContent = t('cat.please_select_category');
      return;
    }
    const start = document.getElementById('catTrendStart').value;
    const end = document.getElementById('catTrendEnd').value;
    const pageMode = currentCatTrendMode();
    if (pageMode === 'compare' && (!start || !end || start >= end)) {
      errEl.textContent = t('cat.compare_order_error');
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
          `<tr><td>${r.department || t('common.none')}</td><td>${fmtInt(r.headcount)}</td><td>${fmtMoney(r.total)}</td><td>${fmtMoney(r.avg)}</td><td>${r.pct_of_hr_cost.toFixed(1)}%</td></tr>`
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
    el.innerHTML = `<div class="muted">${t('common.no_data')}</div>`;
    return;
  }
  const rowsHtml = r.categories
    .map(
      (c) => `
      <tr>
        <td>${categoryLabel(c)}</td>
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
    <div class="stat" style="max-width:260px;margin-bottom:12px;"><div class="label">${t('cat.composition.total_hr_cost')}</div><div class="value">${fmtMoney(r.hr_cost)}</div></div>
    <table>
      <thead><tr><th>${t('cat.composition.table.category')}</th><th>${t('cat.composition.table.amount')}</th><th>${t('cat.composition.table.pct')}</th><th></th></tr></thead>
      <tbody>${rowsHtml}</tbody>
    </table>
  `;
}

const pctStr = (p) => (p === null || p === undefined ? '' : ` (${p.toFixed(1)}%)`);

function flatItemLabel(item) {
  if (item.key !== 'headcount') return item.label;
  const net = (item.joiners_count || 0) - (item.leavers_count || 0);
  const direction = net > 0 ? t('attr.net_increase', { n: net }) : net < 0 ? t('attr.net_decrease', { n: Math.abs(net) }) : t('attr.net_unchanged');
  return t('attr.headcount_change_prefix') + direction + t('attr.joiners_leavers', {
    joiners: item.joiners_count,
    joiners_cost: fmtMoney(item.joiners_cost),
    leavers: item.leavers_count,
    leavers_cost: fmtMoney(item.leavers_cost),
  });
}

function renderAttribution(r) {
  const el = document.getElementById('attrResult');
  const movers = (list, sign) =>
    list.map((m) => `<li>${m.name || t('common.unknown')}（${m.job_grade || '-'}）: ${sign}${fmtMoney(Math.abs(m.hr_cost))}</li>`).join('');

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
        `<tr><td>${l.label}</td><td>${t('attr.formal_contract_split', { formal: l.count_formal, contract: l.count_contract })}</td><td>${l.amount >= 0 ? '+' : ''}${fmtMoney(l.amount)}${pctStr(l.pct_of_net_change)}</td></tr>`
    )
    .join('');

  el.innerHTML = `
    <div class="summary-grid">
      <div class="stat"><div class="label">${r.prev_month} ${t('attr.prev_total')}</div><div class="value">${fmtMoney(r.prev_total)}</div></div>
      <div class="stat"><div class="label">${r.cur_month} ${t('attr.cur_total')}</div><div class="value">${fmtMoney(r.cur_total)}</div></div>
      <div class="stat"><div class="label">${t('attr.net_change')}</div><div class="value">${r.net_change >= 0 ? '+' : ''}${fmtMoney(r.net_change)}</div></div>
      <div class="stat"><div class="label">${t('attr.reconciled')}</div><div class="value">${r.reconciled ? t('attr.reconciled.ok') : t('attr.reconciled.fail')}</div></div>
    </div>

    <h4 style="margin-top:16px;">${t('attr.breakdown_title')}</h4>
    <table>
      <thead><tr><th>${t('attr.table.idx')}</th><th>${t('attr.table.item')}</th><th>${t('attr.table.amount')}</th><th>${t('attr.table.pct_of_net')}</th></tr></thead>
      <tbody>${flatRows}</tbody>
    </table>
    <div class="muted" style="margin-top:6px;">${t('attr.reconcile_note_prefix')}${items.length}${t('attr.reconcile_note_sum')}${fmtMoney(itemsSum)}${r.reconciled ? t('attr.reconcile_note_ok') : t('attr.reconcile_note_fail')}</div>

    ${r.anomalies && r.anomalies.length ? `<ul class="issue-list severe" style="margin-top:12px;">${r.anomalies.map((a) => `<li>⚠️ ${a}</li>`).join('')}</ul>` : ''}

    <h4 style="margin-top:20px;">${t('attr.behavior_title')}</h4>
    <table>
      <thead><tr><th>${t('attr.table.label')}</th><th>${t('attr.table.headcount')}</th><th>${t('attr.table.cost')}</th></tr></thead>
      <tbody>${labelRows}</tbody>
    </table>

    <div class="row" style="margin-top:12px;">
      <div>
        <strong>${t('attr.top_increases')}</strong>
        <ul>${movers(r.top_increases, '+')}</ul>
      </div>
      <div>
        <strong>${t('attr.top_decreases')}</strong>
        <ul>${movers(r.top_decreases, '-')}</ul>
      </div>
    </div>
    ${Object.keys(r.leaver_reasons || {}).length ? `<div><strong>${t('attr.leaver_reasons')}</strong> ${Object.entries(r.leaver_reasons).map(([k, v]) => `${k} × ${v}`).join('，')}</div>` : ''}
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
    const thinking = appendChatMsg('assistant', t('chat.thinking'));
    try {
      const resp = await apiPost('/api/chat', { question });
      thinking.textContent = resp.answer;
    } catch (e) {
      thinking.textContent = t('chat.error') + e.message;
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
        <td>${u.role === 'admin' ? t('common.admin') : t('common.viewer')}</td>
        <td><span class="badge ${u.is_active ? 'confirmed' : 'rejected'}">${u.is_active ? t('perm.status.active') : t('perm.status.disabled')}</span></td>
        <td>
          <button class="secondary" style="padding:2px 8px;font-size:12px;" onclick="resetUserPassword(${u.id}, '${u.username}')">${t('perm.action.reset_password')}</button>
          <button class="${u.is_active ? 'danger' : 'secondary'}" style="padding:2px 8px;font-size:12px;margin-left:4px;" onclick="toggleUserActive(${u.id}, ${!u.is_active}, '${u.username}')">${u.is_active ? t('perm.action.disable') : t('perm.action.enable')}</button>
        </td>
      </tr>`
    )
    .join('');
  return users;
}

async function resetUserPassword(userId, username) {
  const newPassword = prompt(t('perm.reset_password_prompt', { username }));
  if (!newPassword) return;
  try {
    await apiPost(`/api/auth/users/${userId}/reset-password`, { new_password: newPassword });
    alert(t('perm.reset_password_done'));
  } catch (e) {
    alert(t('perm.reset_password_failed') + e.message);
  }
}

async function toggleUserActive(userId, nextActive, username) {
  if (!nextActive && !confirm(t('perm.disable_confirm', { username }))) return;
  try {
    await apiPost(`/api/auth/users/${userId}/active`, { is_active: nextActive });
    await loadUserList();
  } catch (e) {
    alert(t('perm.action_failed') + e.message);
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
    container.innerHTML = `<div class="muted">${t('perm.no_scope_data')}</div>`;
    return;
  }
  container.innerHTML = entities
    .map((entity) => {
      const depts = entityDepartmentMap[entity] || [];
      return `
      <div class="scope-entity-block">
        <label><input type="checkbox" class="entity-check" data-entity="${entity}"> ${t('perm.whole_entity_prefix')}${entity}</label>
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
  const typeLabel = { entity: t('perm.type.entity'), entity_department: t('perm.type.entity_department') };
  document.getElementById('permCurrentList').innerHTML = grants.length
    ? grants
        .map(
          (g) => `
      <tr${g.is_active ? '' : ' style="opacity:0.55;"'}>
        <td>${typeLabel[g.scope_type] || g.scope_type}</td>
        <td>${g.entity}</td>
        <td>${g.department1 || `<span class="muted">（${t('common.all')}）</span>`}</td>
        <td>${g.is_active ? `<span class="badge confirmed">${t('perm.status.effective')}</span>` : `<span class="badge rejected">${t('perm.status.revoked')}</span>`}</td>
        <td class="muted" style="font-size:12px;">
          ${g.granted_by || '-'} · ${fmtDateTime(g.granted_time)}
          ${g.revoked_by ? `<br>${t('perm.revoked_prefix')}${g.revoked_by} · ${fmtDateTime(g.revoked_time)}` : ''}
        </td>
        <td>${g.is_active ? `<button class="danger" style="padding:2px 8px;font-size:12px;" onclick="revokePermission(${userId}, ${g.id})">${t('perm.action.revoke')}</button>` : ''}</td>
      </tr>`
        )
        .join('')
    : `<tr><td colspan="6" class="muted">${t('perm.no_grants')}</td></tr>`;
}

async function revokePermission(userId, grantId) {
  if (!confirm(t('perm.revoke_confirm'))) return;
  await apiFetch(`/api/auth/users/${userId}/permissions/${grantId}`, { method: 'DELETE' });
  await loadCurrentPermissions();
}

async function loadOperationLog() {
  const logs = await apiJson('/api/auth/operation-log');
  const typeLabel = { upload: t('perm.oplog.upload'), correct: t('perm.oplog.correct'), delete: t('perm.oplog.delete') };
  document.getElementById('opLogList').innerHTML = logs.length
    ? logs
        .map(
          (l) => `
      <div class="upload-list-item">
        <span>${fmtDateTime(l.operation_time)} · ${l.operator} · ${typeLabel[l.operation_type] || l.operation_type}${l.target_month ? ' · ' + l.target_month : ''}</span>
        <span class="muted">${l.detail || ''}</span>
      </div>`
        )
        .join('')
    : `<div class="muted">${t('perm.oplog.none')}</div>`;
}

async function loadDownloadLog() {
  const logs = await apiJson('/api/auth/download-log');
  const salaryTypeLabel = SALARY_TYPE_LABEL();
  document.getElementById('downloadLogList').innerHTML = logs.length
    ? logs
        .map(
          (l) => `
      <div class="upload-list-item">
        <span>${fmtDateTime(l.download_time)} · ${l.username} · ${l.entity_scope || '-'} / ${l.department_scope || '-'} · ${l.month_range_start} – ${l.month_range_end}${l.salary_types ? ' · ' + l.salary_types.split(',').map((st) => salaryTypeLabel[st] || st).join('+') : ''}</span>
        <span class="muted">${fmtInt(l.row_count)}${t('perm.downloadlog.row_count_suffix')}</span>
      </div>`
        )
        .join('')
    : `<div class="muted">${t('perm.downloadlog.none')}</div>`;
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
      errEl.textContent = t('perm.please_select_scope');
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
      errEl.textContent = t('perm.grant_failed') + e.message;
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
