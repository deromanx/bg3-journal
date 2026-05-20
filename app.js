/* ============================================================
   BG3 冒險日誌 v5 — 前端邏輯
   功能：日誌閱讀 / 統計儀表板 / 里程碑時間軸 / 本集戰報
   ============================================================ */

let sessions   = [];
let milestones = [];
let awards     = {};
let currentId  = null;
let currentView = 'journal';

// ── 載入 ──────────────────────────────────────────────────
Promise.all([
  fetch('data/sessions.json').then(r => r.json()),
  fetch('data/milestones.json').then(r => r.json()).catch(() => []),
  fetch('data/awards.json').then(r => r.json()).catch(() => ({})),
])
.then(([sessionsData, milestonesData, awardsData]) => {
  sessions   = sessionsData;
  milestones = milestonesData;
  awards     = awardsData;
  renderSidebar();
  const first = sessions.slice().reverse().find(s => !s.placeholder)
                || sessions[sessions.length - 1];
  if (first) loadSession(first.id);
})
.catch(() => {
  document.getElementById('session-list').innerHTML =
    '<li style="padding:20px 16px;font-size:12px;color:rgba(201,168,76,0.3);text-align:center">' +
    '⚠ 無法載入日誌<br><br>' +
    '<small>請執行 python3 extract.py<br>再用 HTTP 伺服器開啟</small></li>';
});

// ── 視圖切換 ──────────────────────────────────────────────
function showView(view) {
  currentView = view;
  document.querySelectorAll('.stab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === view);
  });
  const isJournal = view === 'journal';
  document.getElementById('welcome').classList.toggle('hidden',
    !isJournal || currentId !== null);
  document.getElementById('session-view').classList.toggle('hidden',
    !isJournal || currentId === null);
  document.getElementById('stats-view').classList.toggle('hidden', view !== 'stats');
  document.getElementById('milestones-view').classList.toggle('hidden', view !== 'milestones');

  if (view === 'stats')      renderStats();
  if (view === 'milestones') renderMilestones();
}

// ── 側欄（最新集在最上方）──────────────────────────────────
function renderSidebar() {
  const list = document.getElementById('session-list');
  list.innerHTML = sessions.slice().reverse().map(s => `
    <li class="session-item${s.placeholder ? ' placeholder' : ''}"
        data-id="${s.id}"
        onclick="loadSession(${s.id})"
        title="${esc(s.title)}">
      <div class="item-chapter">${esc(s.chapter)}</div>
      <div class="item-date">${s.date?.replace(/-/g, '.') ?? ''}</div>
      <div class="item-title">${esc(s.title)}</div>
    </li>`
  ).join('');
}

// ── 載入場次 ──────────────────────────────────────────────
function loadSession(id) {
  const session = sessions.find(s => s.id === id);
  if (!session) return;
  currentId = id;

  // 切回日誌視圖
  currentView = 'journal';
  document.querySelectorAll('.stab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === 'journal');
  });
  document.getElementById('stats-view').classList.add('hidden');
  document.getElementById('milestones-view').classList.add('hidden');
  document.getElementById('welcome').classList.add('hidden');

  document.querySelectorAll('.session-item').forEach(el => {
    el.classList.toggle('active', +el.dataset.id === id);
  });
  document.querySelector('.session-item.active')?.scrollIntoView({ block: 'nearest' });

  const view = document.getElementById('session-view');
  view.classList.add('hidden');
  requestAnimationFrame(() => {
    view.classList.remove('hidden');
    view.scrollTop = 0;
    updateProgress();
  });

  document.getElementById('header-chapter').textContent = session.chapter;
  document.getElementById('header-title').textContent   = session.title;
  document.getElementById('header-date').textContent    = session.dateDisplay ?? '';

  const body = document.getElementById('session-body');
  body.innerHTML = session.placeholder
    ? '<p style="text-align:center;color:var(--ink-light);opacity:.4;margin-top:80px;font-style:italic">✦ 本集日誌尚待記錄… ✦</p>'
    : renderContent(session.content);

  renderAwardCard(id);

  const idx = sessions.findIndex(s => s.id === id);
  document.getElementById('prev-btn').disabled = idx <= 0;
  document.getElementById('next-btn').disabled = idx >= sessions.length - 1;

  if (window.innerWidth <= 720) {
    document.getElementById('sidebar').classList.remove('open');
  }
}

// ── 本集戰報 ──────────────────────────────────────────────
function renderAwardCard(sessionId) {
  const card  = document.getElementById('award-card');
  const award = awards[String(sessionId)];
  if (!award) { card.classList.add('hidden'); return; }

  const items = [
    award.mvp          ? `<div class="aw-item"><span class="aw-icon">🏆</span><span class="aw-key">MVP</span><span class="aw-val">${esc(award.mvp)}</span>${award.mvp_reason ? `<span class="aw-sub">${esc(award.mvp_reason)}</span>` : ''}</div>` : '',
    award.best_quote   ? `<div class="aw-item"><span class="aw-icon">💬</span><span class="aw-key">最佳金句</span><span class="aw-val aw-quote">「${esc(award.best_quote)}」</span></div>` : '',
    award.worst_moment ? `<div class="aw-item"><span class="aw-icon">💀</span><span class="aw-key">最慘時刻</span><span class="aw-val">${esc(award.worst_moment)}</span></div>` : '',
  ].filter(Boolean).join('');

  card.classList.remove('hidden');
  card.innerHTML = `
    <div class="award-card">
      <div class="award-label">✦ 本集戰報</div>
      <div class="award-body">${items}</div>
    </div>`;
}

// ── 閱讀進度條 ────────────────────────────────────────────
function updateProgress() {
  const view = document.getElementById('session-view');
  const bar  = document.getElementById('progress-bar');
  if (!view || !bar) return;
  const pct = view.scrollHeight <= view.clientHeight
    ? 100
    : (view.scrollTop / (view.scrollHeight - view.clientHeight)) * 100;
  bar.style.width = pct + '%';
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('session-view')
    ?.addEventListener('scroll', updateProgress);
});

// ── 前後集 ────────────────────────────────────────────────
function navigateSession(delta) {
  const idx  = sessions.findIndex(s => s.id === currentId);
  const next = sessions[idx + delta];
  if (next) loadSession(next.id);
}

// ── 手機側欄 ──────────────────────────────────────────────
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}

// ══════════════════════════════════════════════════════════
// 統計儀表板
// ══════════════════════════════════════════════════════════
function computeStats() {
  const completed = sessions.filter(s => !s.placeholder && s.content.length > 0);
  if (!completed.length) return null;

  const first = completed[0];
  const last  = completed[completed.length - 1];
  const weeks = Math.round(
    (new Date(last.date) - new Date(first.date)) / (7 * 24 * 60 * 60 * 1000)
  );

  const totalImgs  = sessions.reduce((n, s) => n + s.content.filter(i => i.t === 'img').length, 0);
  const totalParas = completed.reduce((n, s) => n + s.content.filter(i => i.t === 'p').length, 0);
  const totalAI    = completed.reduce((n, s) => n + s.content.filter(i => i.t === 'ai').length, 0);

  const richest = completed.reduce((a, b) =>
    a.content.filter(i => i.t === 'p').length >= b.content.filter(i => i.t === 'p').length ? a : b
  );
  const mostImgs = completed.reduce((a, b) =>
    a.content.filter(i => i.t === 'img').length >= b.content.filter(i => i.t === 'img').length ? a : b
  );

  // 角色出場次數（含玩家名＋角色名）
  const charDefs = [
    { label: '游尚傑（影心）',   terms: ['游尚傑', '影心', '依列蒙'] },
    { label: '林昱宇（阿斯代倫）', terms: ['林昱宇', '阿斯代倫', '阿斯'] },
    { label: '曹祐誠',           terms: ['曹祐誠', '曹'] },
    { label: '丁丁（卡拉克）',   terms: ['丁丁', '卡拉克'] },
    { label: '昱如（貓咕咕）',   terms: ['昱如', '貓咕咕'] },
  ];
  const allText = sessions
    .flatMap(s => s.content.filter(i => i.t !== 'img').map(i => i.v))
    .join(' ');

  const charMentions = charDefs.map(c => {
    let count = 0;
    c.terms.forEach(term => {
      let pos = 0;
      while ((pos = allText.indexOf(term, pos)) !== -1) { count++; pos += term.length; }
    });
    return { label: c.label, count };
  }).sort((a, b) => b.count - a.count);

  return {
    completedCount: completed.length,
    totalCount: sessions.length,
    placeholders: sessions.filter(s => s.placeholder).length,
    weeks, totalImgs, totalParas, totalAI,
    richest, mostImgs, charMentions,
    firstDisplay: first.dateDisplay,
    lastDisplay:  last.dateDisplay,
  };
}

function renderStats() {
  const inner = document.getElementById('stats-inner');
  const s = computeStats();
  if (!s) { inner.innerHTML = '<p class="empty-note">尚無資料</p>'; return; }

  const maxMentions = Math.max(...s.charMentions.map(c => c.count), 1);

  inner.innerHTML = `
    <div class="sub-header">
      <div class="sub-rule"><span class="rule-line"></span><span class="sub-title">冒 險 統 計</span><span class="rule-line"></span></div>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-num">${s.completedCount}</div>
        <div class="stat-label">已記錄集數</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">${s.weeks}</div>
        <div class="stat-label">冒險週數</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">${s.totalImgs}</div>
        <div class="stat-label">珍貴插圖</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">${s.totalParas}</div>
        <div class="stat-label">故事段落</div>
      </div>
    </div>

    <div class="stats-section">
      <div class="stats-section-title">角色出場次數</div>
      ${s.charMentions.map(c => `
        <div class="char-row">
          <div class="char-name">${c.label}</div>
          <div class="char-bar-wrap">
            <div class="char-bar" style="width:${Math.round(c.count / maxMentions * 100)}%"></div>
          </div>
          <div class="char-count">${c.count}</div>
        </div>`).join('')}
    </div>

    <div class="stats-section">
      <div class="stats-section-title">集數亮點</div>
      <div class="hl-grid">
        <div class="hl-card" onclick="loadSession(${s.richest.id})">
          <div class="hl-badge">文字最豐富</div>
          <div class="hl-chapter">${s.richest.chapter}</div>
          <div class="hl-title">${esc(s.richest.title)}</div>
          <div class="hl-link">閱讀本集 →</div>
        </div>
        <div class="hl-card" onclick="loadSession(${s.mostImgs.id})">
          <div class="hl-badge">插圖最多</div>
          <div class="hl-chapter">${s.mostImgs.chapter}</div>
          <div class="hl-title">${esc(s.mostImgs.title)}</div>
          <div class="hl-detail">${s.mostImgs.content.filter(i => i.t === 'img').length} 張插圖</div>
          <div class="hl-link">閱讀本集 →</div>
        </div>
        ${s.totalAI > 0 ? `
        <div class="hl-card no-click">
          <div class="hl-badge">AI 點評</div>
          <div class="hl-chapter" style="font-size:2rem">${s.totalAI}</div>
          <div class="hl-title">則 AI 點評</div>
        </div>` : ''}
      </div>
    </div>

    <div class="stats-footer">
      ${s.firstDisplay} ── ${s.lastDisplay}
    </div>`;
}

// ══════════════════════════════════════════════════════════
// 里程碑時間軸
// ══════════════════════════════════════════════════════════
function renderMilestones() {
  const inner = document.getElementById('milestones-inner');

  const typeColor = {
    start:       '#8b1a1a',
    boss:        '#5a0d0d',
    location:    '#1a3c60',
    achievement: '#3e5c20',
    death:       '#2a2a2a',
    item:        '#5c3a10',
    custom:      '#3e1f5c',
  };

  inner.innerHTML = `
    <div class="sub-header">
      <div class="sub-rule"><span class="rule-line"></span><span class="sub-title">里 程 碑</span><span class="rule-line"></span></div>
      <p class="sub-note">在 data/milestones.json 新增或編輯里程碑</p>
    </div>

    <div class="timeline">
      ${milestones.length
        ? milestones.map(m => `
          <div class="ms-item">
            <div class="ms-dot" style="color:${typeColor[m.type] || typeColor.custom}">${m.icon || '✦'}</div>
            <div class="ms-content">
              <div class="ms-date">${(m.date || '').replace(/-/g, '.')}</div>
              <div class="ms-title">${esc(m.title || '')}</div>
              ${m.desc ? `<div class="ms-desc">${esc(m.desc)}</div>` : ''}
              ${m.session_id
                ? `<button class="ms-link" onclick="loadSession(${m.session_id})">前往本集 →</button>`
                : ''}
            </div>
          </div>`).join('')
        : '<p class="empty-note">尚無里程碑。請在 data/milestones.json 新增記錄。</p>'
      }
    </div>`;
}

// ── 結構化內容渲染 ────────────────────────────────────────
function renderContent(items) {
  if (!items?.length) return '<p style="text-align:center;opacity:.4">尚無內容</p>';

  return items.map((item, i) => {
    switch (item.t) {
      case 'img':
        return `<figure class="session-img">
          <img src="${esc(item.v)}" alt="" loading="lazy">
        </figure>`;

      case 'h1': {
        const ornament = i > 0
          ? `<div class="section-ornament"><span>◆</span></div>`
          : '';
        return `${ornament}<h2 class="section-h1">${renderInline(item.v)}</h2>`;
      }

      case 'h2':
        return `<h3 class="section-h2">${renderInline(item.v)}</h3>`;

      case 'ai':
        return `<div class="ai-note">${renderInline(item.v)}</div>`;

      case 'p':
      default:
        return `<p>${renderInline(item.v)}</p>`;
    }
  }).join('\n');
}

// ── 行內格式 ──────────────────────────────────────────────
function renderInline(text) {
  let s = esc(text);
  s = s.replace(/「([^」]*)」/g, '<span class="dialogue">「$1」</span>');
  return s;
}

function esc(s) {
  return (s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
