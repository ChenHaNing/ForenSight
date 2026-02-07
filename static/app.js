const statusPill = document.getElementById('status-pill');
const runBtn = document.getElementById('run-btn');
const timeline = document.getElementById('timeline');
const agentContainer = document.getElementById('agents');
const downloadFinal = document.getElementById('download-final');
const downloadWorkpaper = document.getElementById('download-workpaper');
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
const baseOutputEl = document.getElementById('base-output');
const agentOutputEl = document.getElementById('agent-output');
const defenseOutputEl = document.getElementById('defense-output');
const finalOutputEl = document.getElementById('final-output');

const steps = ['collect', 'base', 'agents', 'defense', 'judge'];

function setStatus(text, colorClass = 'success') {
  statusPill.textContent = text;
  statusPill.style.color = colorClass === 'danger' ? '#ef4444' : '#22c55e';
}

function resetTimeline() {
  timeline.querySelectorAll('li').forEach((item) => {
    item.classList.remove('active', 'complete');
  });
}

function activateStep(step) {
  const item = timeline.querySelector(`li[data-step="${step}"]`);
  if (item) {
    item.classList.add('active');
  }
}

function completeStep(step) {
  const item = timeline.querySelector(`li[data-step="${step}"]`);
  if (item) {
    item.classList.remove('active');
    item.classList.add('complete');
  }
}

function updateAgentCard(name, report) {
  const card = agentContainer.querySelector(`[data-agent="${name}"]`);
  if (!card) return;
  card.querySelector('.status').textContent = `风险等级：${report.risk_level}`;
  const body = card.querySelector('.body');
  const points = (report.risk_points || []).slice(0, 3);
  body.innerHTML = points.map((p) => `<div>• ${p}</div>`).join('') || '—';
}

function updateJudge(report) {
  const card = agentContainer.querySelector('[data-agent="judge"]');
  if (!card) return;
  card.querySelector('.status').textContent = `最终等级：${report.overall_risk_level}`;
  const body = card.querySelector('.body');
  body.innerHTML = report.rationale ? `<div>${report.rationale}</div>` : '—';
}

function fillList(container, items) {
  container.innerHTML = '';
  if (!items || items.length === 0) {
    container.innerHTML = '<li class="muted">—</li>';
    return;
  }
  items.forEach((item) => {
    const li = document.createElement('li');
    li.textContent = item;
    container.appendChild(li);
  });
}

function fillEvidence(evidence) {
  evidenceListEl.innerHTML = '';
  if (!evidence || evidence.length === 0) {
    evidenceListEl.innerHTML = '<div class="muted">暂无证据片段</div>';
    return;
  }
  evidence.slice(0, 8).forEach((item) => {
    const div = document.createElement('div');
    div.className = 'evidence-item';
    div.innerHTML = `<div>${item.quote}</div><div class="muted">来源：${item.source}</div>`;
    evidenceListEl.appendChild(div);
  });
}

function fillExternalSearch(results) {
  externalSearchEl.innerHTML = '';
  if (!results || results.length === 0) {
    externalSearchEl.innerHTML = '<div class="muted">暂无外部检索结果</div>';
    return;
  }
  results.slice(0, 8).forEach((item) => {
    const div = document.createElement('div');
    div.className = 'evidence-item';
    const title = item.title || '未命名';
    const snippet = item.content || '';
    const url = item.url || '';
    div.innerHTML = `<div><strong>${title}</strong></div><div>${snippet}</div><div class="muted">${url}</div>`;
    externalSearchEl.appendChild(div);
  });
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
    workpaperOutputEl.textContent = '—';
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
    [
      '财务指标',
      workpaper.financial_metrics
        ? Object.entries(workpaper.financial_metrics)
            .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
            .join('<br/>')
        : '—',
    ],
    ['指标缺失说明', (workpaper.metrics_notes || []).join('; ') || '—'],
    ['虚构交易类线索', workpaper.fraud_type_A_block],
    ['净利润操纵线索', workpaper.fraud_type_B_block],
    ['会计操纵收入线索', workpaper.fraud_type_C_block],
    ['净资产舞弊线索', workpaper.fraud_type_D_block],
    ['资金占用线索', workpaper.fraud_type_E_block],
    ['特殊行业/业务模式线索', workpaper.fraud_type_F_block],
  ];
  workpaperOutputEl.innerHTML = sections
    .map(([title, value]) => `<div><strong>${title}</strong><div>${value || '—'}</div></div>`)
    .join('');
}

function buildAgentHtml(title, report) {
  if (!report) {
    return `<div><strong>${title}</strong><div>—</div></div>`;
  }
  const points = (report.risk_points || []).slice(0, 4).map((p) => `<li>${p}</li>`).join('');
  return `
    <div>
      <strong>${title}</strong>
      <div class="muted">风险等级：${report.risk_level || '—'}</div>
      <div><strong>关键风险点</strong><ul>${points || '<li>—</li>'}</ul></div>
      <div><strong>摘要</strong>：${report.reasoning_summary || '—'}</div>
    </div>
  `;
}

function renderFinalReport(targetEl, report) {
  if (!report) {
    targetEl.textContent = '—';
    return;
  }
  const accepted = (report.accepted_points || []).slice(0, 3).map((p) => `<li>${p}</li>`).join('');
  const rejected = (report.rejected_points || []).slice(0, 3).map((p) => `<li>${p}</li>`).join('');
  targetEl.innerHTML = `
    <div><strong>总体风险</strong>：${report.overall_risk_level || '—'}</div>
    <div><strong>采纳点</strong><ul>${accepted || '<li>—</li>'}</ul></div>
    <div><strong>驳回点</strong><ul>${rejected || '<li>—</li>'}</ul></div>
    <div><strong>裁决依据</strong>：${report.rationale || '—'}</div>
  `;
}

function resetOutputs() {
  riskLevelEl.textContent = '—';
  fillList(acceptedPointsEl, []);
  fillList(rejectedPointsEl, []);
  fillList(suggestionsEl, []);
  rationaleEl.textContent = '—';
  uncertaintyEl.textContent = '—';
  evidenceListEl.innerHTML = '';
  externalSearchEl.innerHTML = '';
  workpaperOutputEl.textContent = '—';
  baseOutputEl.textContent = '—';
  agentOutputEl.textContent = '—';
  defenseOutputEl.textContent = '—';
  finalOutputEl.textContent = '—';
  agentContainer.querySelectorAll('.agent .status').forEach((el) => {
    el.textContent = '等待中';
  });
  agentContainer.querySelectorAll('.agent .body').forEach((el) => {
    el.textContent = '';
  });
}

async function runAnalysis() {
  resetTimeline();
  resetOutputs();
  setStatus('运行中');

  const payload = {
    provider: document.getElementById('provider').value,
    model: document.getElementById('model').value,
    base_url: document.getElementById('base_url').value,
    enable_defense: document.getElementById('enable_defense').checked,
    use_samples: document.getElementById('use_samples').checked,
  };

  activateStep(steps[0]);

  try {
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

      if (stepsData.workpaper) {
        completeStep('collect');
        renderWorkpaper(stepsData.workpaper);
      }
      if (stepsData.base) {
        completeStep('base');
        baseOutputEl.innerHTML = buildAgentHtml('基础风险智能体', stepsData.base);
        updateAgentCard('base', stepsData.base);
      }
      if (
        stepsData.fraud_type_A ||
        stepsData.fraud_type_B ||
        stepsData.fraud_type_C ||
        stepsData.fraud_type_D ||
        stepsData.fraud_type_E ||
        stepsData.fraud_type_F
      ) {
        completeStep('agents');
        agentOutputEl.innerHTML = [
          buildAgentHtml('虚构交易类收入舞弊', stepsData.fraud_type_A),
          buildAgentHtml('净利润操纵舞弊', stepsData.fraud_type_B),
          buildAgentHtml('会计操纵收入舞弊', stepsData.fraud_type_C),
          buildAgentHtml('净资产舞弊', stepsData.fraud_type_D),
          buildAgentHtml('资金占用舞弊', stepsData.fraud_type_E),
          buildAgentHtml('特殊行业/业务模式', stepsData.fraud_type_F),
        ].join('');
        if (stepsData.fraud_type_A) updateAgentCard('fraud_type_A', stepsData.fraud_type_A);
        if (stepsData.fraud_type_B) updateAgentCard('fraud_type_B', stepsData.fraud_type_B);
        if (stepsData.fraud_type_C) updateAgentCard('fraud_type_C', stepsData.fraud_type_C);
        if (stepsData.fraud_type_D) updateAgentCard('fraud_type_D', stepsData.fraud_type_D);
        if (stepsData.fraud_type_E) updateAgentCard('fraud_type_E', stepsData.fraud_type_E);
        if (stepsData.fraud_type_F) updateAgentCard('fraud_type_F', stepsData.fraud_type_F);
      }
      if (stepsData.defense) {
        completeStep('defense');
        defenseOutputEl.innerHTML = buildAgentHtml('辩护分析智能体', stepsData.defense);
        updateAgentCard('defense', stepsData.defense);
      }
      if (stepsData.final) {
        completeStep('judge');
        renderFinalReport(finalOutputEl, stepsData.final);
        updateJudge(stepsData.final);
      }

      if (data.final_report) {
        riskLevelEl.textContent = data.final_report?.overall_risk_level || '—';
        fillList(acceptedPointsEl, data.final_report?.accepted_points);
        fillList(rejectedPointsEl, data.final_report?.rejected_points);
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

if (!hasKey) {
  runBtn.disabled = true;
  runBtn.textContent = '请先配置 API Key';
  setStatus('未配置');
} else {
  runBtn.addEventListener('click', runAnalysis);
}
