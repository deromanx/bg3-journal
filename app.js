/* ============================================================
   BG3 冒險日誌 v5 — 前端邏輯
   功能：日誌閱讀 / 統計儀表板 / 里程碑時間軸 / 本集戰報
   ============================================================ */

let sessions      = [];
let milestones    = [];
let awards        = {};
let charStats     = { characters: [] };
let currentId     = null;
let currentView   = 'journal';

// ── 載入 ──────────────────────────────────────────────────
Promise.all([
  fetch('data/sessions.json').then(r => r.json()),
  fetch('data/milestones.json').then(r => r.json()).catch(() => []),
  fetch('data/awards.json').then(r => r.json()).catch(() => ({})),
  fetch('data/character-stats.json').then(r => r.json()).catch(() => ({ characters: [] })),
])
.then(([sessionsData, milestonesData, awardsData, charStatsData]) => {
  sessions   = sessionsData;
  milestones = milestonesData;
  awards     = awardsData;
  charStats  = charStatsData;
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
function computeBaseStats() {
  const completed = sessions.filter(s => !s.placeholder && s.content.length > 0);
  if (!completed.length) return null;
  const first = completed[0];
  const last  = completed[completed.length - 1];
  const weeks = Math.round(
    (new Date(last.date) - new Date(first.date)) / (7 * 24 * 60 * 60 * 1000)
  );
  return { count: completed.length, weeks };
}

function renderStats() {
  const inner = document.getElementById('stats-inner');
  const base  = computeBaseStats();
  if (!base) { inner.innerHTML = '<p class="empty-note">尚無資料</p>'; return; }

  const chars = charStats.characters || [];

  // 死亡卡（依死亡次數降序）
  const byDeaths = chars.slice().sort((a, b) => b.deaths - a.deaths);
  const maxDeaths = Math.max(...byDeaths.map(c => c.deaths), 1);

  const deathCards = byDeaths.map(c => {
    const intensity = c.deaths === 0 ? '' : c.deaths === maxDeaths ? ' dc-max' : c.deaths >= maxDeaths * 0.6 ? ' dc-high' : '';
    return `
      <div class="death-card${intensity}">
        <div class="dc-name-wrap">
          <span class="dc-char">${esc(c.char)}</span>
          <span class="dc-player">${esc(c.player)}</span>
        </div>
        <div class="dc-skull">☠</div>
        <div class="dc-count">${c.deaths}</div>
        <div class="dc-unit">次陣亡</div>
      </div>`;
  }).join('');

  // 決鬥排行（依勝率排序）
  const withDuels = chars.filter(c => (c.duels.wins + c.duels.losses) > 0)
    .slice().sort((a, b) => {
      const ra = a.duels.wins / (a.duels.wins + a.duels.losses);
      const rb = b.duels.wins / (b.duels.wins + b.duels.losses);
      return rb - ra || b.duels.wins - a.duels.wins;
    });

  const duelRows = withDuels.map((c, rank) => {
    const total = c.duels.wins + c.duels.losses;
    const pct   = total ? Math.round(c.duels.wins / total * 100) : 0;
    const medal = rank === 0 ? '🥇' : rank === 1 ? '🥈' : rank === 2 ? '🥉' : '';
    return `
      <div class="duel-row">
        <div class="dr-rank">${medal || (rank + 1)}</div>
        <div class="dr-name">
          <span class="dr-char">${esc(c.char)}</span>
          <span class="dr-player">${esc(c.player)}</span>
        </div>
        <div class="dr-record">
          <span class="dr-w">${c.duels.wins}勝</span>
          <span class="dr-l">${c.duels.losses}敗</span>
        </div>
        <div class="dr-bar-wrap">
          <div class="dr-bar" style="width:${pct}%"></div>
        </div>
        <div class="dr-pct">${pct}%</div>
      </div>`;
  }).join('');

  inner.innerHTML = `
    <div class="sub-header">
      <div class="sub-rule"><span class="rule-line"></span><span class="sub-title">冒 險 統 計</span><span class="rule-line"></span></div>
    </div>

    <div class="hero-stats-row">
      <div class="hero-stat">
        <div class="hero-icon">⚔</div>
        <div class="hero-num">${base.count}</div>
        <div class="hero-label">場冒險</div>
      </div>
      <div class="hero-sep">✦</div>
      <div class="hero-stat">
        <div class="hero-icon">🧭</div>
        <div class="hero-num">${base.weeks}</div>
        <div class="hero-label">冒險週數</div>
      </div>
    </div>

    <div class="stats-section">
      <div class="stats-section-title">各角色死亡次數</div>
      <div class="death-grid">${deathCards}</div>
    </div>

    ${duelRows ? `
    <div class="stats-section">
      <div class="stats-section-title">決鬥戰績排行</div>
      <div class="duel-board">${duelRows}</div>
      <p class="duel-note">* 僅計 PvP 決鬥；資料維護於 data/character-stats.json</p>
    </div>` : ''}`;
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
