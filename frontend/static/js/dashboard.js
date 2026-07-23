const fmtMoney = (n) => '₦' + Number(n || 0).toLocaleString('en-NG', { maximumFractionDigits: 2 });
const fmtInt = (n) => Number(n || 0).toLocaleString('en-NG');
const SALARY_TYPE_LABEL = { base: '底薪批次', bonus: '奖金', backpay: '补发薪资' };
const STATUS_LABEL = { pending_review: '待确认', confirmed: '已入库', rejected: '已放弃', superseded: '已被替换' };

let currentBatchId = null;
let trendChart = null;
let currentUserRole = null;

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
}

// ---------- upload tab ----------
function issueSeverity(issueType) {
  return ['missing_field', 'unrecognized_sheet'].includes(issueType) ? 'severe' : '';
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
      .map((i) => `<li class="${issueSeverity(i.issue_type)}"><strong>[${i.issue_type}]</strong> ${i.issue_detail}</li>`)
      .join('');
  }

  const busy = batch.status !== 'pending_review';
  document.getElementById('confirmBtn').disabled = busy;
  document.getElementById('rejectBtn').disabled = busy;
  document.getElementById('confirmBtn').textContent = batch.status === 'confirmed' ? '已入库' : '确认无误，正式入库';
}

async function loadUploadHistory() {
  const list = await apiJson('/api/upload');
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
          ${isAdmin && b.status === 'confirmed' ? `
            <button class="secondary" style="padding:2px 8px;font-size:12px;margin-left:6px;" onclick="reassignBatchMonth(${b.id}, '${b.month}')">改月份</button>
            <button class="danger" style="padding:2px 8px;font-size:12px;margin-left:4px;" onclick="deleteBatch(${b.id}, '${b.month}')">删除</button>
          ` : ''}
        </span>
      </div>`
    )
    .join('');
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

  loadUploadHistory();
}

// ---------- meta (departments / entities / months) ----------
async function populateMeta() {
  const meta = await apiJson('/api/meta');
  const fillSelect = (id, values, withEmpty) => {
    const el = document.getElementById(id);
    const current = el.value;
    el.innerHTML = (withEmpty ? '<option value="">全部</option>' : '') + values.map((v) => `<option value="${v}">${v}</option>`).join('');
    if (values.includes(current)) el.value = current;
  };
  fillSelect('trendDept', meta.departments, true);
  fillSelect('trendEntity', meta.entities, true);
  fillSelect('attrDept', meta.departments, true);
  fillSelect('attrEntity', meta.entities, true);
  fillSelect('trendStart', meta.months, false);
  fillSelect('trendEnd', meta.months, false);
  fillSelect('attrPrev', meta.months, false);
  fillSelect('attrCur', meta.months, false);
  if (meta.months.length) {
    document.getElementById('trendStart').value = meta.months[0];
    document.getElementById('trendEnd').value = meta.months[meta.months.length - 1];
    if (meta.months.length >= 2) {
      document.getElementById('attrPrev').value = meta.months[meta.months.length - 2];
      document.getElementById('attrCur').value = meta.months[meta.months.length - 1];
    }
  }
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

function initTrendTab() {
  document.getElementById('trendQueryBtn').addEventListener('click', async () => {
    const rows = await apiPost('/api/trend', {
      department: document.getElementById('trendDept').value || null,
      entity: document.getElementById('trendEntity').value || null,
      start_month: document.getElementById('trendStart').value || null,
      end_month: document.getElementById('trendEnd').value || null,
    });
    renderTrend(rows);
  });

  document.getElementById('attrQueryBtn').addEventListener('click', async () => {
    const prev = document.getElementById('attrPrev').value;
    const cur = document.getElementById('attrCur').value;
    const resultEl = document.getElementById('attrResult');
    if (prev >= cur) {
      resultEl.innerHTML = '<div class="error">对比月份 A 必须早于 B</div>';
      return;
    }
    const r = await apiPost('/api/attribution', {
      department: document.getElementById('attrDept').value || null,
      entity: document.getElementById('attrEntity').value || null,
      prev_month: prev,
      cur_month: cur,
    });
    renderAttribution(r);
  });
}

function renderAttribution(r) {
  const el = document.getElementById('attrResult');
  const movers = (list, sign) =>
    list.map((m) => `<li>${m.name || '(未知)'}（${m.job_grade || '-'}）: ${sign}${fmtMoney(Math.abs(m.hr_cost))}</li>`).join('');

  el.innerHTML = `
    <div class="summary-grid">
      <div class="stat"><div class="label">${r.prev_month} 总成本</div><div class="value">${fmtMoney(r.prev_total)}</div></div>
      <div class="stat"><div class="label">${r.cur_month} 总成本</div><div class="value">${fmtMoney(r.cur_total)}</div></div>
      <div class="stat"><div class="label">净变化</div><div class="value">${r.net_change >= 0 ? '+' : ''}${fmtMoney(r.net_change)}</div></div>
      <div class="stat"><div class="label">校验</div><div class="value">${r.reconciled ? '✓ 吻合' : '✗ 不吻合，需排查'}</div></div>
    </div>
    <table>
      <thead><tr><th>归因项</th><th>人数</th><th>成本影响</th></tr></thead>
      <tbody>
        <tr><td>新入职</td><td>${r.joiners_count}</td><td>+${fmtMoney(r.joiners_cost)}</td></tr>
        <tr><td>离职</td><td>${r.leavers_count}</td><td>-${fmtMoney(r.leavers_cost)}</td></tr>
        <tr><td>留任员工变化</td><td>${r.stayers_count}</td><td>${r.stayers_delta >= 0 ? '+' : ''}${fmtMoney(r.stayers_delta)}</td></tr>
        ${r.unattributed_delta ? `<tr><td>其他调整（奖金/补发，无法关联到具体在职员工）</td><td>-</td><td>${r.unattributed_delta >= 0 ? '+' : ''}${fmtMoney(r.unattributed_delta)}</td></tr>` : ''}
      </tbody>
    </table>
    <div class="row" style="margin-top:12px;">
      <div>
        <strong>留任员工涨幅最大：</strong>
        <ul>${movers(r.top_increases, '+')}</ul>
      </div>
      <div>
        <strong>留任员工降幅最大：</strong>
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

(async function main() {
  await initShell();
  initUploadTab();
  initTrendTab();
  initChatTab();
  await populateMeta();
})();
