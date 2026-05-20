/* ============================================================
   BG3 冒險日誌 v5 — 前端邏輯
   功能：日誌閱讀 / 統計儀表板 / 里程碑時間軸 / 本集戰報
   ============================================================ */

let sessions      = [];
let milestones    = [];
let awards        = {};
let charStats     = { characters: [] };
let roastStats    = { matrix: [], highlights: [] };
let currentId     = null;
let currentView   = 'journal';

// ── 載入 ──────────────────────────────────────────────────
Promise.all([
  fetch('data/sessions.json').then(r => r.json()),
  fetch('data/milestones.json').then(r => r.json()).catch(() => []),
  fetch('data/awards.json').then(r => r.json()).catch(() => ({})),
  fetch('data/character-stats.json').then(r => r.json()).catch(() => ({ characters: [] })),
  fetch('data/roast-stats.json').then(r => r.json()).catch(() => ({ matrix: [], highlights: [] })),
])
.then(([sessionsData, milestonesData, awardsData, charStatsData, roastData]) => {
  sessions   = sessionsData;
  milestones = milestonesData;
  awards     = awardsData;
  charStats  = charStatsData;
  roastStats = roastData;
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
    const ov = document.getElementById('sidebar-overlay');
    if (ov) { ov.style.opacity = '0'; ov.style.display = 'none'; }
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
  initTooltip();
  initMatrixHover();
});

// ── Tooltip 系統 ──────────────────────────────────────────
function initTooltip() {
  const tip = document.createElement('div');
  tip.id = 'tooltip';
  document.body.appendChild(tip);
  let active = null;

  document.addEventListener('mouseover', e => {
    const el = e.target.closest('[data-tip]');
    if (!el || el === active) return;
    active = el;
    tip.innerHTML = el.dataset.tip.replace(/\n/g, '<br>');
    tip.classList.add('visible');
  });
  document.addEventListener('mousemove', e => {
    if (!active) return;
    const x = e.clientX + 14, y = e.clientY - 8;
    tip.style.left = Math.min(x, window.innerWidth  - tip.offsetWidth  - 12) + 'px';
    tip.style.top  = Math.min(y, window.innerHeight - tip.offsetHeight - 12) + 'px';
  });
  document.addEventListener('mouseout', e => {
    if (active && !active.contains(e.relatedTarget)) {
      active = null; tip.classList.remove('visible');
    }
  });
}

// ── 對戰矩陣 hover 行列高亮 ──────────────────────────────
function initMatrixHover() {
  document.addEventListener('mouseover', e => {
    const cell = e.target.closest('.mm-cell,.mm-empty,.mm-self');
    if (!cell) return;
    const tbl = cell.closest('.matchup-matrix');
    if (!tbl) return;
    const row = cell.parentElement;
    const colIdx = Array.from(row.cells).indexOf(cell);
    tbl.querySelectorAll('.mm-hdr').forEach((th, i) =>
      th.classList.toggle('mm-col-active', i === colIdx - 1));
    tbl.querySelectorAll('.mm-row-hdr').forEach(th =>
      th.classList.toggle('mm-row-active', th.parentElement === row));
    tbl.querySelectorAll('td').forEach(c => {
      const ci = Array.from(c.parentElement.cells).indexOf(c);
      c.classList.toggle('mm-same-row', c.parentElement === row && c !== cell);
      c.classList.toggle('mm-same-col', ci === colIdx && c !== cell);
    });
  });
  document.addEventListener('mouseout', e => {
    const cell = e.target.closest('.mm-cell,.mm-empty,.mm-self');
    if (!cell) return;
    const tbl = cell.closest('.matchup-matrix');
    if (!tbl || tbl.contains(e.relatedTarget)) return;
    tbl.querySelectorAll('.mm-hdr,.mm-row-hdr,td')
      .forEach(el => el.classList.remove('mm-col-active','mm-row-active','mm-same-row','mm-same-col'));
  });
}

// ── 前後集 ────────────────────────────────────────────────
function navigateSession(delta) {
  const idx  = sessions.findIndex(s => s.id === currentId);
  const next = sessions[idx + delta];
  if (next) loadSession(next.id);
}

// ── 手機側欄 ──────────────────────────────────────────────
function toggleSidebar() {
  const sidebar  = document.getElementById('sidebar');
  const overlay  = document.getElementById('sidebar-overlay');
  const isOpen   = sidebar.classList.toggle('open');
  if (overlay) {
    overlay.style.display  = isOpen ? 'block' : 'none';
    // force reflow so opacity transition fires
    overlay.getBoundingClientRect();
    overlay.style.opacity  = isOpen ? '1' : '0';
  }
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
    const deathTip = c.deaths === 0 ? '尚未陣亡' : (c.death_notes || []).join('\n');
    return `
      <div class="death-card${intensity}" data-tip="${esc(deathTip)}">
        <div class="dc-avatar av-${esc(c.char)}">
          <img src="data/images/avatars/${esc(c.char)}.jpg" alt="" onerror="this.style.display='none'">
        </div>
        <div class="dc-name-wrap">
          <span class="dc-char">${esc(c.char)}</span>
          <span class="dc-player">${esc(c.player)}</span>
        </div>
        <div class="dc-skull">☠</div>
        <div class="dc-count">${c.deaths}</div>
        <div class="dc-unit">次陣亡</div>
      </div>`;
  }).join('');

  // 決鬥排行（依勝率排序，不含平手場次計算勝率）
  const withDuels = chars.filter(c => (c.duels.wins + c.duels.losses) > 0)
    .slice().sort((a, b) => {
      const ra = a.duels.wins / (a.duels.wins + a.duels.losses);
      const rb = b.duels.wins / (b.duels.wins + b.duels.losses);
      return rb - ra || b.duels.wins - a.duels.wins;
    });

  const duelRows = withDuels.map((c, rank) => {
    const draws = c.duels.draws || 0;
    const decisive = c.duels.wins + c.duels.losses;
    const total  = decisive + draws;
    const pct    = decisive ? Math.round(c.duels.wins / decisive * 100) : 0;
    const medal  = rank === 0 ? '🥇' : rank === 1 ? '🥈' : rank === 2 ? '🥉' : '';
    const duelTip = c.duels.detail || '';
    return `
      <div class="duel-row" data-tip="${esc(duelTip)}">
        <div class="dr-rank">${medal || (rank + 1)}</div>
        <div class="dr-name">
          <span class="dr-char">${esc(c.char)}</span>
          <span class="dr-player">${esc(c.player)}</span>
        </div>
        <div class="dr-record">
          <span class="dr-w">${c.duels.wins}勝</span>
          <span class="dr-l">${c.duels.losses}敗</span>
          ${draws > 0 ? `<span class="dr-d">${draws}平</span>` : ''}
          <span class="dr-total">${total}場</span>
        </div>
        <div class="dr-bar-wrap">
          <div class="dr-bar" style="width:${pct}%"></div>
        </div>
        <div class="dr-pct">${pct}%</div>
      </div>`;
  }).join('');

  // 對戰矩陣
  const matchupData = charStats.matchups || [];
  const mmMap = {};
  chars.forEach(a => { mmMap[a.char] = {}; chars.forEach(b => { mmMap[a.char][b.char] = null; }); });
  matchupData.forEach(m => {
    const [ca, cb] = m.chars;
    const [wa, wb] = m.wins;
    const d = m.draws || 0;
    mmMap[ca][cb] = { w: wa, l: wb, d };
    mmMap[cb][ca] = { w: wb, l: wa, d };
  });

  const mmHeaders = chars.map(c => `
    <th class="mm-hdr">
      <div class="mm-hav av-${esc(c.char)}">
        <img src="data/images/avatars/${esc(c.char)}.jpg" alt="" onerror="this.style.display='none'">
      </div>
      <span class="mm-hchar">${esc(c.char)}</span>
    </th>`).join('');

  const mmRows = chars.map(rowC => {
    const cells = chars.map(colC => {
      if (rowC.char === colC.char) return `<td class="mm-self"></td>`;
      const rec = mmMap[rowC.char]?.[colC.char];
      if (!rec) return `<td class="mm-empty" data-tip="${esc(rowC.char)} vs ${esc(colC.char)}&#10;無正式對戰記錄">—</td>`;
      const cls = rec.w > rec.l ? 'mm-win' : rec.l > rec.w ? 'mm-lose' : 'mm-even';
      const decisive = rec.w + rec.l;
      const pct = decisive ? Math.round(rec.w / decisive * 100) : 0;
      const tip = `${esc(rowC.char)} vs ${esc(colC.char)}&#10;${rec.w}勝 ${rec.l}敗${rec.d ? ` ${rec.d}平` : ''}&#10;勝率 ${pct}%（勝/決定局）`;
      return `<td class="mm-cell ${cls}" data-tip="${tip}">
        <span class="mm-w">${rec.w}</span><span class="mm-sep">/</span><span class="mm-l">${rec.l}</span>${rec.d > 0 ? `<span class="mm-d">${rec.d}平</span>` : ''}
      </td>`;
    }).join('');
    return `<tr>
      <th class="mm-row-hdr">
        <div class="mm-rav av-${esc(rowC.char)}">
          <img src="data/images/avatars/${esc(rowC.char)}.jpg" alt="" onerror="this.style.display='none'">
        </div>
        <div class="mm-rnames">
          <span class="mm-rchar">${esc(rowC.char)}</span>
          <span class="mm-rplayer">${esc(rowC.player)}</span>
        </div>
      </th>${cells}</tr>`;
  }).join('');

  const matchupGrid = matchupData.length ? `
    <div class="stats-section">
      <div class="stats-section-title">對戰組合戰績</div>
      <div class="matchup-note-row">↓ 列 = 攻方視角 &nbsp;·&nbsp; 格內：<span class="mm-w-ex">勝</span> / <span class="mm-l-ex">敗</span> &nbsp;·&nbsp; hover 查看詳情</div>
      <div class="matchup-wrap">
        <table class="matchup-matrix">
          <thead><tr><th class="mm-corner">vs</th>${mmHeaders}</tr></thead>
          <tbody>${mmRows}</tbody>
        </table>
      </div>
      <p class="duel-note">* 源自日誌表格記錄；部分場次數據可能略有出入</p>
    </div>` : '';

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
    </div>` : ''}

    ${matchupGrid}

    ${renderRoastSection()}`;
}

// ══════════════════════════════════════════════════════════
// 靠北統計區塊
// ══════════════════════════════════════════════════════════
function renderRoastSection() {
  if (!roastStats.matrix?.length) return '';
  const chars = charStats.characters || [];
  const charNames = chars.map(c => c.char);

  // 計算每人被靠北 & 主動靠北總數
  const received  = {};
  const initiated = {};
  charNames.forEach(n => { received[n] = 0; initiated[n] = 0; });
  roastStats.matrix.forEach(r => {
    if (initiated[r.from] !== undefined) initiated[r.from] += r.count;
    if (received[r.to]   !== undefined) received[r.to]   += r.count;
  });

  // 按被靠北排序
  const byReceived = charNames.slice().sort((a, b) => received[b] - received[a]);
  const maxReceived = Math.max(...byReceived.map(n => received[n]), 1);
  const maxInit     = Math.max(...charNames.map(n => initiated[n]), 1);

  // 被靠北 bar chart rows
  const receivedRows = byReceived.map((name, i) => {
    const c = chars.find(x => x.char === name);
    const pct = Math.round(received[name] / maxReceived * 100);
    const crown = i === 0 ? ' rb-crown' : '';
    return `
      <div class="rb-row${crown}">
        <div class="rb-avatar av-${name}">
          <img src="data/images/avatars/${esc(name)}.jpg" alt="" onerror="this.style.display='none'">
        </div>
        <div class="rb-info">
          <div class="rb-name">${esc(name)}<span class="rb-player">${esc(c?.player || '')}</span></div>
          <div class="rb-bar-track">
            <div class="rb-bar-fill" style="width:${pct}%"></div>
          </div>
        </div>
        <div class="rb-count">${received[name]}<span class="rb-unit">次</span></div>
      </div>`;
  }).join('');

  // 主動靠北排序 & mini badges
  const byInit = charNames.slice().sort((a, b) => initiated[b] - initiated[a]);
  const initBadges = byInit.map((name, i) => {
    const pct = Math.round(initiated[name] / maxInit * 100);
    return `
      <div class="ib-row">
        <div class="ib-rank">${i + 1}</div>
        <div class="ib-avatar av-${name}">
          <img src="data/images/avatars/${esc(name)}.jpg" alt="" onerror="this.style.display='none'">
        </div>
        <div class="ib-name">${esc(name)}</div>
        <div class="ib-bar-track"><div class="ib-bar-fill" style="width:${pct}%"></div></div>
        <div class="ib-count">${initiated[name]}</div>
      </div>`;
  }).join('');

  // 靠北熱力矩陣（5×5）
  const roastMap = {};
  charNames.forEach(a => { roastMap[a] = {}; charNames.forEach(b => { roastMap[a][b] = 0; }); });
  roastStats.matrix.forEach(r => { if (roastMap[r.from]?.[r.to] !== undefined) roastMap[r.from][r.to] = r.count; });
  const maxCell = Math.max(...roastStats.matrix.map(r => r.count), 1);

  const heatHeaders = charNames.map(n => `
    <th class="rh-hdr">
      <div class="rh-hav av-${esc(n)}">
        <img src="data/images/avatars/${esc(n)}.jpg" alt="" onerror="this.style.display='none'">
      </div>
      <span class="rh-hname">${esc(n)}</span>
    </th>`).join('');
  const heatRows = charNames.map(rowN => {
    const cells = charNames.map(colN => {
      if (rowN === colN) return `<td class="rh-self"></td>`;
      const v = roastMap[rowN][colN];
      const intensity = Math.round(v / maxCell * 100);
      const tip = `${esc(rowN)} → ${esc(colN)}&#10;靠北 ${v} 次`;
      return `<td class="rh-cell" style="--ri:${intensity}" data-tip="${tip}">${v}</td>`;
    }).join('');
    return `<tr>
      <th class="rh-row-hdr">
        <div class="rh-hav av-${esc(rowN)}">
          <img src="data/images/avatars/${esc(rowN)}.jpg" alt="" onerror="this.style.display='none'">
        </div>
        <span class="rh-hname">${esc(rowN)}</span>
      </th>${cells}</tr>`;
  }).join('');

  // 集數精華
  const highlights = (roastStats.highlights || []).map(h => `
    <div class="hl-item">
      <span class="hl-ep">S${h.session}</span>
      <span class="hl-desc">${esc(h.desc)}</span>
    </div>`).join('');

  return `
    <div class="stats-section">
      <div class="stats-section-title">互相靠北排行</div>
      <div class="roast-meta">全 18 集共計 <strong>${roastStats.total || 0}</strong> 次記錄在案的靠北事件</div>

      <div class="roast-columns">
        <div class="roast-col">
          <div class="roast-col-title">☠ 被靠北次數</div>
          <div class="rb-board">${receivedRows}</div>
        </div>
        <div class="roast-col">
          <div class="roast-col-title">💀 主動靠北次數</div>
          <div class="ib-board">${initBadges}</div>
        </div>
      </div>

      <div class="roast-col-title" style="margin-top:24px">🔥 靠北熱力圖（列 = 靠北者，欄 = 受害者）</div>
      <div class="heat-wrap">
        <table class="roast-heat">
          <thead><tr><th class="rh-corner"></th>${heatHeaders}</tr></thead>
          <tbody>${heatRows}</tbody>
        </table>
        <div class="heat-legend">
          <span class="hl-lo">少</span>
          <div class="hl-grad"></div>
          <span class="hl-hi">多</span>
        </div>
      </div>

      <div class="roast-col-title" style="margin-top:24px">📜 各集代表性靠北事件</div>
      <div class="highlights-list">${highlights}</div>
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

// ── 角色別名映射 ─────────────────────────────────────────
const CHAR_MAP = {
  '影心': '影心', '游尚傑': '影心',
  '阿斯代倫': '阿斯代倫', '林昱宇': '阿斯代倫',
  '曹': '曹', '曹祐誠': '曹',
  '卡拉克': '卡拉克', '丁丁': '卡拉克',
  '貓咕咕': '貓咕咕', '昱如': '貓咕咕',
};

function resolveChar(name) {
  for (const key of Object.keys(CHAR_MAP)) {
    if (name.includes(key)) return CHAR_MAP[key];
  }
  return null;
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
      default: {
        // Detect character quote: 「...」——角色名
        const qm = item.v.match(/^「([\s\S]+?)」[—\-]{1,2}(.{1,12})$/);
        if (qm) {
          const speaker = resolveChar(qm[2].trim());
          if (speaker) {
            return `<div class="quote-wrap">
              <div class="char-avatar av-${esc(speaker)}" aria-label="${esc(speaker)}" data-tip="${esc(speaker)}">
                <img src="data/images/avatars/${esc(speaker)}.jpg" alt="" loading="lazy">
              </div>
              <blockquote class="char-quote">
                「${esc(qm[1])}」
                <cite class="dq-attr">—— ${esc(qm[2].trim())}</cite>
              </blockquote>
            </div>`;
          }
        }
        return `<p>${renderInline(item.v)}</p>`;
      }
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
