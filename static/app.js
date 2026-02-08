const statusPill = document.getElementById('status-pill');
const runBtn = document.getElementById('run-btn');
const timeline = document.getElementById('timeline');
const agentContainer = document.getElementById('agents');
const downloadFinal = document.getElementById('download-final');
const downloadWorkpaper = document.getElementById('download-workpaper');
const reportFileInput = document.getElementById('report-file');
const uploadStatusEl = document.getElementById('upload-status');
const hasKey = document.body.dataset.hasKey === 'true';

const riskLevelEl = document.getElementById('risk-level');
const acceptedPointsEl = document.getElementById('accepted-points');
const rejectedPointsEl = document.getElementById('rejected-points');
const suggestionsEl = document.getElementById('suggestions');
const rationaleEl = document.getElementById('rationale');
const uncertaintyEl = document.getElementById('uncertainty');
const evidenceListEl = document.getElementById('evidence-list');
const externalSearchEl = document.getElementById('external-search');
const workpaperOutputEl = document.getElementById('workpaper-output');
const collectOutputEl = document.getElementById('collect-output');
const baseOutputEl = document.getElementById('base-output');
const agentOutputEl = document.getElementById('agent-output');
const defenseOutputEl = document.getElementById('defense-output');
const finalOutputEl = document.getElementById('final-output');
const stepPanels = document.querySelectorAll('#step-outputs details');
const traceSegments = document.querySelectorAll('#trace-bar .trace-segment');
const reportCardEl = document.querySelector('.report-row .card.report');
const summaryCards = document.querySelectorAll('.report-row .summary-card');
const nodeMetaEls = {
  collect: document.getElementById('node-meta-collect'),
  base: document.getElementById('node-meta-base'),
  agents: document.getElementById('node-meta-agents'),
  defense: document.getElementById('node-meta-defense'),
  judge: document.getElementById('node-meta-judge'),
};

const steps = ['collect', 'base', 'agents', 'defense', 'judge'];
const FRAUD_AGENTS = [
  { key: 'fraud_type_A', title: '虚构交易类收入舞弊' },
  { key: 'fraud_type_B', title: '净利润操纵舞弊' },
  { key: 'fraud_type_C', title: '会计操纵收入舞弊' },
  { key: 'fraud_type_D', title: '净资产舞弊' },
  { key: 'fraud_type_E', title: '资金占用舞弊' },
  { key: 'fraud_type_F', title: '特殊行业/业务模式' },
];
const renderCache = new Map();
let uploadedReportId = null;
let uploadedReportKey = null;

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatCell(value) {
  if (value === null || value === undefined) {
    return '<span class="table-empty">—</span>';
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return '<span class="table-empty">—</span>';
    return `<ul class="table-list">${value.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
  }
  if (typeof value === 'object') {
    return `<pre class="table-pre">${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
  }
  const text = String(value).trim();
  if (!text) return '<span class="table-empty">—</span>';
  return escapeHtml(text).replaceAll('\n', '<br/>');
}

function buildTable(headers, rows) {
  const thead = `<thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join('')}</tr></thead>`;
  const tbody = `<tbody>${rows
    .map((row) => `<tr>${row.map((value) => `<td>${formatCell(value)}</td>`).join('')}</tr>`)
    .join('')}</tbody>`;
  return `<div class="table-wrap"><table class="data-table">${thead}${tbody}</table></div>`;
}

function setStatus(text, colorClass = 'success') {
  statusPill.textContent = text;
  statusPill.style.color = colorClass === 'danger' ? '#ef4444' : '#22c55e';
}

function setHTMLIfChanged(element, html, cacheKey) {
  if (!element) return false;
  const prev = renderCache.get(cacheKey);
  if (prev === html) return false;

  const prevWrap = element.querySelector('.table-wrap');
  const prevScrollTop = prevWrap ? prevWrap.scrollTop : 0;
  const prevScrollLeft = prevWrap ? prevWrap.scrollLeft : 0;

  element.innerHTML = html;
  renderCache.set(cacheKey, html);

  const nextWrap = element.querySelector('.table-wrap');
  if (nextWrap) {
    nextWrap.scrollTop = prevScrollTop;
    nextWrap.scrollLeft = prevScrollLeft;
  }
  return true;
}

function flashUpdate(element) {
  if (!element) return;
  element.classList.remove('stream-update');
  // Force reflow to replay animation.
  void element.offsetWidth;
  element.classList.add('stream-update');
}

function setNodeMeta(step, text) {
  const el = nodeMetaEls[step];
  if (el) el.textContent = text;
}

function setTraceState(step, state) {
  const segment = document.querySelector(`#trace-bar .trace-segment[data-step="${step}"]`);
  if (!segment) return;
  segment.classList.remove('active', 'complete');
  if (state) {
    segment.classList.add(state);
  }
}

function syncSummaryCardHeights() {
  if (!reportCardEl || summaryCards.length === 0) return;

  if (window.matchMedia('(max-width: 1200px)').matches) {
    summaryCards.forEach((card) => card.style.removeProperty('height'));
    return;
  }

  summaryCards.forEach((card) => card.style.removeProperty('height'));
  const reportHeight = reportCardEl.getBoundingClientRect().height;
  if (!Number.isFinite(reportHeight) || reportHeight <= 0) return;

  const targetHeight = `${Math.round(reportHeight)}px`;
  summaryCards.forEach((card) => {
    card.style.height = targetHeight;
  });
}

function resetTimeline() {
  timeline.querySelectorAll('li').forEach((item) => {
    item.classList.remove('active', 'complete');
  });
  stepPanels.forEach((panel) => {
    panel.classList.remove('active', 'complete');
  });
  traceSegments.forEach((segment) => {
    segment.classList.remove('active', 'complete');
  });
  Object.keys(nodeMetaEls).forEach((step) => setNodeMeta(step, '等待中'));
  agentContainer.querySelectorAll('.agent').forEach((card) => {
    card.classList.remove('step-active');
  });
}

function activateStep(step) {
  if (document.body.dataset.activeStep === step) {
    setNodeMeta(step, '运行中');
    setTraceState(step, 'active');
    return;
  }

  timeline.querySelectorAll('li.active').forEach((item) => {
    if (item.dataset.step !== step) item.classList.remove('active');
  });
  stepPanels.forEach((panel) => {
    if (panel.dataset.step !== step) panel.classList.remove('active');
  });
  traceSegments.forEach((segment) => {
    if (segment.dataset.step !== step && !segment.classList.contains('complete')) {
      segment.classList.remove('active');
    }
  });

  const item = timeline.querySelector(`li[data-step="${step}"]`);
  if (item) {
    item.classList.add('active');
  }
  const panel = document.querySelector(`#step-outputs details[data-step="${step}"]`);
  if (panel) {
    panel.classList.add('active');
    if (!panel.open) panel.open = true;
  }
  setNodeMeta(step, '运行中');
  setTraceState(step, 'active');
  document.body.dataset.activeStep = step;

  agentContainer.querySelectorAll('.agent').forEach((card) => {
    card.classList.remove('step-active');
  });
  const currentGroup = step === 'collect' ? null : step;
  if (currentGroup) {
    agentContainer.querySelectorAll(`.agent[data-step-group="${currentGroup}"]`).forEach((card) => {
      card.classList.add('step-active');
    });
  }
}

function completeStep(step) {
  const item = timeline.querySelector(`li[data-step="${step}"]`);
  if (item) {
    item.classList.remove('active');
    item.classList.add('complete');
  }
  const panel = document.querySelector(`#step-outputs details[data-step="${step}"]`);
  if (panel) {
    panel.classList.remove('active');
    panel.classList.add('complete');
  }
  setNodeMeta(step, '已完成');
  setTraceState(step, 'complete');
  if (document.body.dataset.activeStep === step) {
    delete document.body.dataset.activeStep;
  }
}

function formatReactAttempts(report) {
  const attempts = Number(report?._react_attempts);
  if (!Number.isFinite(attempts) || attempts < 0) {
    return '自主调查0轮';
  }
  return `自主调查${Math.floor(attempts)}轮`;
}

function updateAgentCard(name, report) {
  const card = agentContainer.querySelector(`[data-agent="${name}"]`);
  if (!card) return;
  card.querySelector('.status').textContent = `风险等级：${report.risk_level}｜${formatReactAttempts(report)}`;
  const body = card.querySelector('.body');
  const points = (report.risk_points || []).slice(0, 3);
  body.innerHTML = points.map((p) => `<div>• ${p}</div>`).join('') || '—';
  flashUpdate(card);
}

function updateJudge(report) {
  const card = agentContainer.querySelector('[data-agent="judge"]');
  if (!card) return;
  card.querySelector('.status').textContent = `最终等级：${report.overall_risk_level}`;
  const body = card.querySelector('.body');
  body.innerHTML = report.rationale ? `<div>${report.rationale}</div>` : '—';
  flashUpdate(card);
}

function fillList(container, items, itemClass = '') {
  container.innerHTML = '';
  if (!items || items.length === 0) {
    container.innerHTML = '<li class="muted">—</li>';
    return;
  }
  items.forEach((item) => {
    const li = document.createElement('li');
    li.textContent = item;
    if (itemClass) {
      li.classList.add(itemClass);
    }
    container.appendChild(li);
  });
}

function fillEvidence(evidence) {
  if (!evidence || evidence.length === 0) {
    const changed = setHTMLIfChanged(evidenceListEl, '<div class="muted">暂无证据片段</div>', 'evidence:empty');
    if (changed) flashUpdate(evidenceListEl);
    requestAnimationFrame(syncSummaryCardHeights);
    return;
  }
  const rows = evidence.slice(0, 12).map((item, index) => [index + 1, item.quote || '—', item.source || '—']);
  const html = buildTable(['序号', '证据片段', '来源'], rows);
  const changed = setHTMLIfChanged(evidenceListEl, html, 'evidence:data');
  if (changed) flashUpdate(evidenceListEl);
  requestAnimationFrame(syncSummaryCardHeights);
}

function fillExternalSearch(results) {
  if (!results || results.length === 0) {
    const changed = setHTMLIfChanged(
      externalSearchEl,
      '<div class="muted">暂无外部检索结果</div>',
      'external:empty',
    );
    if (changed) flashUpdate(externalSearchEl);
    requestAnimationFrame(syncSummaryCardHeights);
    return;
  }
  const rows = results.slice(0, 12).map((item, index) => [
    index + 1,
    item.title || '未命名',
    item.content || '—',
    item.url || '—',
  ]);
  const html = buildTable(['序号', '标题', '摘要', '链接'], rows);
  const changed = setHTMLIfChanged(externalSearchEl, html, 'external:data');
  if (changed) flashUpdate(externalSearchEl);
  requestAnimationFrame(syncSummaryCardHeights);
}

function enableDownloads(finalReport, workpaper) {
  downloadFinal.disabled = false;
  downloadWorkpaper.disabled = false;

  downloadFinal.onclick = () => {
    const blob = new Blob([JSON.stringify(finalReport, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'final_report.json';
    link.click();
    URL.revokeObjectURL(url);
  };

  downloadWorkpaper.onclick = () => {
    const blob = new Blob([JSON.stringify(workpaper, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'workpaper.json';
    link.click();
    URL.revokeObjectURL(url);
  };
}

function renderWorkpaper(workpaper) {
  if (!workpaper) {
    const changed = setHTMLIfChanged(workpaperOutputEl, '—', 'workpaper:empty');
    if (changed) flashUpdate(workpaperOutputEl);
    return;
  }
  const sections = [
    ['公司概况', workpaper.company_profile],
    ['财务摘要', workpaper.financial_summary],
    ['风险披露', workpaper.risk_disclosures],
    ['重大事项', workpaper.major_events],
    ['治理信号', workpaper.governance_signals],
    ['行业可比', workpaper.industry_comparables],
    ['临时公告摘要', workpaper.announcements_summary],
    ['关联方/客户供应商摘要', workpaper.related_parties_summary],
    ['行业对标摘要', workpaper.industry_benchmark_summary],
    ['外部检索摘要', workpaper.external_search_summary],
    ['财务指标', workpaper.financial_metrics || '—'],
    ['指标缺失说明', workpaper.metrics_notes || []],
    ['虚构交易类线索', workpaper.fraud_type_A_block],
    ['净利润操纵线索', workpaper.fraud_type_B_block],
    ['会计操纵收入线索', workpaper.fraud_type_C_block],
    ['净资产舞弊线索', workpaper.fraud_type_D_block],
    ['资金占用线索', workpaper.fraud_type_E_block],
    ['特殊行业/业务模式线索', workpaper.fraud_type_F_block],
  ];
  const html = buildTable(['字段', '内容'], sections);
  const changed = setHTMLIfChanged(workpaperOutputEl, html, 'workpaper:data');
  if (changed) flashUpdate(workpaperOutputEl);
}

function renderCollectBreakdown(stepsData) {
  const rowStatus = (value, fallback = '处理中') => (value ? '已完成' : fallback);
  const rows = [
    ['文档解析与摘要', rowStatus(stepsData.collect_summary), stepsData.collect_summary || '等待抽取'],
    ['财务数据抽取', rowStatus(stepsData.collect_financial_data), stepsData.collect_financial_data || '等待抽取'],
    ['上下文构建', rowStatus(stepsData.collect_context_pack), stepsData.collect_context_pack || '等待构建'],
    ['公司主体识别', rowStatus(stepsData.collect_company_name, '等待识别'), stepsData.collect_company_name || '待识别'],
  ];
  const html = buildTable(['子步骤', '状态', '当前输出'], rows);
  const changed = setHTMLIfChanged(collectOutputEl, html, 'collect:data');
  if (changed) flashUpdate(collectOutputEl);
}

function renderFraudAgentsOutput(stepsData) {
  const rows = FRAUD_AGENTS.map(({ key, title }) => {
    const report = stepsData[key];
    if (!report) {
      return [title, '处理中', '—', '—', '—', '等待智能体返回'];
    }
    return [
      title,
      '已完成',
      report.risk_level || '—',
      report.confidence ?? '—',
      formatReactAttempts(report),
      report.risk_points || [],
    ];
  });
  return buildTable(['智能体', '状态', '风险等级', '置信度', '自主调查', '关键风险点'], rows);
}

function buildAgentHtml(title, report) {
  if (!report) {
    return buildTable(['字段', '内容'], [[title, '—']]);
  }
  const rows = [
    ['智能体', title],
    ['风险等级', report.risk_level || '—'],
    ['置信度', report.confidence ?? '—'],
    ['自主调查轮次', formatReactAttempts(report)],
    ['关键风险点', report.risk_points || []],
    ['关键证据', report.evidence || []],
    ['摘要', report.reasoning_summary || '—'],
  ];
  return buildTable(['字段', '内容'], rows);
}

function renderFinalReport(targetEl, report) {
  if (!report) {
    const changed = setHTMLIfChanged(targetEl, '—', 'final:empty');
    if (changed) flashUpdate(targetEl);
    return;
  }
  const rows = [
    ['总体风险', report.overall_risk_level || '—'],
    ['采纳点', report.accepted_points || []],
    ['驳回点', report.rejected_points || []],
    ['裁决依据', report.rationale || '—'],
  ];
  const html = buildTable(['字段', '内容'], rows);
  const changed = setHTMLIfChanged(targetEl, html, 'final:data');
  if (changed) flashUpdate(targetEl);
}

function resetOutputs() {
  renderCache.clear();
  riskLevelEl.textContent = '—';
  fillList(acceptedPointsEl, []);
  fillList(rejectedPointsEl, [], 'is-rejected');
  fillList(suggestionsEl, []);
  rationaleEl.textContent = '—';
  uncertaintyEl.textContent = '—';
  setHTMLIfChanged(evidenceListEl, '', 'evidence:data');
  setHTMLIfChanged(externalSearchEl, '', 'external:data');
  setHTMLIfChanged(collectOutputEl, '—', 'collect:empty');
  setHTMLIfChanged(workpaperOutputEl, '—', 'workpaper:empty');
  setHTMLIfChanged(baseOutputEl, '—', 'base:empty');
  setHTMLIfChanged(agentOutputEl, '—', 'agents:empty');
  setHTMLIfChanged(defenseOutputEl, '—', 'defense:empty');
  setHTMLIfChanged(finalOutputEl, '—', 'final:empty');
  agentContainer.querySelectorAll('.agent .status').forEach((el) => {
    el.textContent = '等待中';
  });
  agentContainer.querySelectorAll('.agent .body').forEach((el) => {
    el.textContent = '';
  });
  agentContainer.querySelectorAll('.agent').forEach((card) => {
    card.classList.remove('step-active');
  });
  delete document.body.dataset.activeStep;
  requestAnimationFrame(syncSummaryCardHeights);
}

function currentReportFileKey(file) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

async function uploadReportIfNeeded() {
  const file = reportFileInput?.files?.[0];
  if (!file) {
    uploadedReportId = null;
    uploadedReportKey = null;
    if (uploadStatusEl) uploadStatusEl.textContent = '未上传文件（可选）';
    return null;
  }

  const nextKey = currentReportFileKey(file);
  if (uploadedReportId && uploadedReportKey === nextKey) {
    return uploadedReportId;
  }

  if (uploadStatusEl) uploadStatusEl.textContent = '上传并解析中...';
  const formData = new FormData();
  formData.append('file', file);

  const resp = await fetch('/api/upload-report', {
    method: 'POST',
    body: formData,
  });
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.detail || '文件上传失败');
  }

  uploadedReportId = data.report_id;
  uploadedReportKey = nextKey;
  if (uploadStatusEl) {
    uploadStatusEl.textContent = `已上传：${data.filename}（${data.chars} 字）`;
  }
  return uploadedReportId;
}

async function runAnalysis() {
  resetTimeline();
  resetOutputs();
  setStatus('运行中');

  try {
    const payload = {
      provider: document.getElementById('provider').value,
      model: document.getElementById('model').value,
      base_url: document.getElementById('base_url').value,
      enable_defense: document.getElementById('enable_defense').checked,
    };

    const reportId = await uploadReportIfNeeded();
    if (reportId) {
      payload.uploaded_report_id = reportId;
    }

    activateStep(steps[0]);
    if (!payload.enable_defense) {
      const disabledDefenseHtml = buildTable(['字段', '内容'], [['辩护智能体', '已禁用']]);
      const changed = setHTMLIfChanged(defenseOutputEl, disabledDefenseHtml, 'defense:disabled');
      if (changed) flashUpdate(defenseOutputEl);
    }

    const resp = await fetch('/api/run?mode=async', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const error = await resp.json();
      throw new Error(error.detail || '请求失败');
    }

    const { run_id } = await resp.json();
    if (!run_id) {
      throw new Error('缺少运行ID');
    }

    let finished = false;
    activateStep('collect');
    const poll = async () => {
      if (finished) return;
      const statusResp = await fetch(`/api/status?run_id=${run_id}`);
      if (!statusResp.ok) {
        throw new Error('状态查询失败');
      }
      const data = await statusResp.json();
      const stepsData = data.step_outputs || {};
      renderCollectBreakdown(stepsData);
      const collectDone = Boolean(stepsData.workpaper);
      if (!collectDone) {
        activateStep('collect');
      }

      if (collectDone) {
        completeStep('collect');
        renderWorkpaper(stepsData.workpaper);
      }
      if (stepsData.base) {
        activateStep('base');
        completeStep('base');
        const baseHtml = buildAgentHtml('基础风险智能体', stepsData.base);
        const changed = setHTMLIfChanged(baseOutputEl, baseHtml, 'base:data');
        if (changed) flashUpdate(baseOutputEl);
        updateAgentCard('base', stepsData.base);
      } else if (collectDone) {
        activateStep('base');
      }

      const doneFraudAgents = FRAUD_AGENTS.filter(({ key }) => Boolean(stepsData[key])).length;
      if (doneFraudAgents > 0 || stepsData.base) {
        activateStep('agents');
      }
      if (stepsData.base) {
        const agentsHtml = renderFraudAgentsOutput(stepsData);
        const changed = setHTMLIfChanged(agentOutputEl, agentsHtml, 'agents:data');
        if (changed) flashUpdate(agentOutputEl);
      }
      if (doneFraudAgents === FRAUD_AGENTS.length) {
        completeStep('agents');
      }
      if (stepsData.fraud_type_A) updateAgentCard('fraud_type_A', stepsData.fraud_type_A);
      if (stepsData.fraud_type_B) updateAgentCard('fraud_type_B', stepsData.fraud_type_B);
      if (stepsData.fraud_type_C) updateAgentCard('fraud_type_C', stepsData.fraud_type_C);
      if (stepsData.fraud_type_D) updateAgentCard('fraud_type_D', stepsData.fraud_type_D);
      if (stepsData.fraud_type_E) updateAgentCard('fraud_type_E', stepsData.fraud_type_E);
      if (stepsData.fraud_type_F) updateAgentCard('fraud_type_F', stepsData.fraud_type_F);

      if (!payload.enable_defense && doneFraudAgents === FRAUD_AGENTS.length) {
        completeStep('defense');
      }
      if (payload.enable_defense && doneFraudAgents === FRAUD_AGENTS.length && !stepsData.defense) {
        activateStep('defense');
      }
      if (stepsData.defense) {
        activateStep('defense');
        completeStep('defense');
        const defenseHtml = buildAgentHtml('辩护分析智能体', stepsData.defense);
        const changed = setHTMLIfChanged(defenseOutputEl, defenseHtml, 'defense:data');
        if (changed) flashUpdate(defenseOutputEl);
        updateAgentCard('defense', stepsData.defense);
      }
      if ((stepsData.defense || !payload.enable_defense) && !stepsData.final) {
        activateStep('judge');
      }
      if (stepsData.final) {
        activateStep('judge');
        completeStep('judge');
        renderFinalReport(finalOutputEl, stepsData.final);
        updateJudge(stepsData.final);
      }

      if (data.final_report) {
        riskLevelEl.textContent = data.final_report?.overall_risk_level || '—';
        fillList(acceptedPointsEl, data.final_report?.accepted_points);
        fillList(rejectedPointsEl, data.final_report?.rejected_points, 'is-rejected');
        fillList(suggestionsEl, data.final_report?.suggestions);
        rationaleEl.textContent = data.final_report?.rationale || '—';
        uncertaintyEl.textContent = data.final_report?.uncertainty || '—';
      }

      if (data.workpaper?.evidence) {
        fillEvidence(data.workpaper.evidence);
        enableDownloads(data.final_report || stepsData.final, data.workpaper);
      }

      const externalResults = [
        ...(stepsData.base?._external_search || []),
        ...(stepsData.fraud_type_A?._external_search || []),
        ...(stepsData.fraud_type_B?._external_search || []),
        ...(stepsData.fraud_type_C?._external_search || []),
        ...(stepsData.fraud_type_D?._external_search || []),
        ...(stepsData.fraud_type_E?._external_search || []),
        ...(stepsData.fraud_type_F?._external_search || []),
        ...(stepsData.defense?._external_search || []),
      ];
      if (externalResults.length > 0) {
        fillExternalSearch(externalResults);
      }

      requestAnimationFrame(syncSummaryCardHeights);

      if (data.status === 'completed') {
        finished = true;
        setStatus('分析完成');
      }
      if (data.status === 'failed') {
        finished = true;
        throw new Error(data.error || '分析失败');
      }
    };

    const pollInterval = setInterval(() => {
      poll().catch((err) => {
        clearInterval(pollInterval);
        resetTimeline();
        resetOutputs();
        setStatus('失败', 'danger');
        alert(err.message);
      });
      if (finished) {
        clearInterval(pollInterval);
      }
    }, 1200);
  } catch (err) {
    resetTimeline();
    resetOutputs();
    setStatus('失败', 'danger');
    console.error(err);
    alert(err.message);
  }
}

window.addEventListener('resize', syncSummaryCardHeights);
if ('ResizeObserver' in window && reportCardEl) {
  const reportHeightObserver = new ResizeObserver(() => syncSummaryCardHeights());
  reportHeightObserver.observe(reportCardEl);
}
requestAnimationFrame(syncSummaryCardHeights);

if (!hasKey) {
  runBtn.disabled = true;
  runBtn.textContent = '请先配置 API Key';
  setStatus('未配置');
} else {
  if (reportFileInput && uploadStatusEl) {
    reportFileInput.addEventListener('change', () => {
      uploadedReportId = null;
      uploadedReportKey = null;
      const file = reportFileInput.files?.[0];
      uploadStatusEl.textContent = file
        ? `已选择：${file.name}（点击运行后上传）`
        : '未上传文件（可选）';
    });
  }
  runBtn.addEventListener('click', runAnalysis);
}
