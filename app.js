/* ============================================================
   BG3 冒險日誌 v5 — 前端邏輯
   功能：日誌閱讀 / 統計儀表板 / 里程碑時間軸 / 本集戰報
   ============================================================ */

let sessions      = [];
let milestones    = [];
let awards        = {};
let charStats     = { characters: [] };
let roastStats    = { matrix: [], highlights: [] };
let storyData     = { chapters: [] };
let currentId     = null;
let currentView   = 'journal';
let _ignoreHash   = false;

// ── 載入 ──────────────────────────────────────────────────
Promise.all([
  fetch('data/sessions.json').then(r => r.json()),
  fetch('data/milestones.json').then(r => r.json()).catch(() => []),
  fetch('data/awards.json').then(r => r.json()).catch(() => ({})),
  fetch('data/character-stats.json', { cache: 'no-store' }).then(r => r.json()).catch(() => ({ characters: [] })),
  fetch('data/roast-stats.json').then(r => r.json()).catch(() => ({ matrix: [], highlights: [] })),
  fetch('data/story.json').then(r => r.json()).catch(() => ({ chapters: [] })),
])
.then(([sessionsData, milestonesData, awardsData, charStatsData, roastData, storyJson]) => {
  sessions   = sessionsData;
  milestones = milestonesData;
  awards     = awardsData;
  charStats  = charStatsData;
  roastStats = roastData;
  storyData  = storyJson;
  renderSidebar();
  restoreFromHash();
})
.catch(() => {
  document.getElementById('session-list').innerHTML =
    '<li style="padding:20px 16px;font-size:12px;color:rgba(201,168,76,0.3);text-align:center">' +
    '⚠ 無法載入日誌<br><br>' +
    '<small>請執行 python3 extract.py<br>再用 HTTP 伺服器開啟</small></li>';
});

// ── Hash 路由 ──────────────────────────────────────────────
function _setHash(h) {
  if (location.hash === h) return;
  _ignoreHash = true;
  location.hash = h;
}

const ALL_VIEWS = ['journal', 'characters', 'stats', 'milestones', 'story'];

function hideAllViews() {
  document.getElementById('welcome').classList.add('hidden');
  document.getElementById('session-view').classList.add('hidden');
  document.getElementById('characters-view').classList.add('hidden');
  document.getElementById('stats-view').classList.add('hidden');
  document.getElementById('milestones-view').classList.add('hidden');
  document.getElementById('story-view').classList.add('hidden');
  document.getElementById('hero-band').classList.add('hidden');
}

function goHome() {
  currentId = null;
  currentView = 'journal';
  _setHash('#home');
  document.querySelectorAll('.stab').forEach(b => b.classList.toggle('active', b.dataset.view === 'journal'));
  hideAllViews();
  document.getElementById('welcome').classList.remove('hidden');
  document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
  const journalNav = document.getElementById('journal-nav');
  if (journalNav) journalNav.classList.remove('hidden-nav');
}

function restoreFromHash() {
  const h = location.hash;
  if (/^#s\d+$/.test(h)) {
    const id = parseInt(h.slice(2));
    if (sessions.find(s => s.id === id)) { loadSession(id); return; }
  }
  if (h === '#characters') { showView('characters'); return; }
  if (h === '#stats')      { showView('stats');      return; }
  if (h === '#milestones') { showView('milestones'); return; }
  if (h === '#story')      { showView('story');      return; }
  if (h === '#home')       { goHome(); return; }
  // 預設：載入最新集
  const first = sessions.slice().reverse().find(s => !s.placeholder) || sessions[sessions.length - 1];
  if (first) loadSession(first.id);
}

// ── 視圖切換 ──────────────────────────────────────────────
function showView(view) {
  currentView = view;
  document.querySelectorAll('.stab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === view);
  });
  hideAllViews();
  const isJournal = view === 'journal';
  const showWelcome = isJournal && currentId === null;
  if (!showWelcome) document.getElementById('hero-band').classList.remove('hidden');
  if (showWelcome) document.getElementById('welcome').classList.remove('hidden');
  if (isJournal && currentId !== null) {
    document.getElementById('session-view').classList.remove('hidden');
  }
  if (view === 'characters') document.getElementById('characters-view').classList.remove('hidden');
  if (view === 'stats')      document.getElementById('stats-view').classList.remove('hidden');
  if (view === 'milestones') document.getElementById('milestones-view').classList.remove('hidden');
  if (view === 'story')      document.getElementById('story-view').classList.remove('hidden');

  // 章節列表只在日誌分頁顯示，故事目錄只在故事分頁顯示
  const journalNav = document.getElementById('journal-nav');
  if (journalNav) journalNav.classList.toggle('hidden-nav', view !== 'journal');
  const storyNav = document.getElementById('story-nav');
  if (storyNav) storyNav.classList.toggle('hidden-nav', view !== 'story');

  if (view === 'characters') { _setHash('#characters'); renderCharacters(); }
  if (view === 'stats')      { _setHash('#stats');      renderStats(); }
  if (view === 'milestones') { _setHash('#milestones'); renderMilestones(); }
  if (view === 'story')      { _setHash('#story');      renderStory(); renderStoryNav(); }
  if (view === 'journal')    { _setHash(currentId ? '#s' + currentId : '#home'); }
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
  _setHash('#s' + id);

  // 切回日誌視圖
  currentView = 'journal';
  document.querySelectorAll('.stab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === 'journal');
  });
  hideAllViews();
  document.getElementById('hero-band').classList.remove('hidden');

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

  const prog = document.getElementById('footer-progress');
  if (prog) prog.innerHTML = `${idx + 1}<span class="fp-sep"> / </span>${sessions.length}`;

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
  initKeyboard();
  initBackToTop();
  window.addEventListener('hashchange', () => {
    if (_ignoreHash) { _ignoreHash = false; return; }
    restoreFromHash();
  });
});

function initBackToTop() {
  const btn = document.getElementById('back-to-top');
  if (!btn) return;
  document.getElementById('content').addEventListener('scroll', function() {
    btn.classList.toggle('visible', this.scrollTop > 400);
  });
}

function scrollToTop() {
  document.getElementById('content').scrollTo({ top: 0, behavior: 'smooth' });
}

// ── 鍵盤導航 ──────────────────────────────────────────────
function initKeyboard() {
  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'ArrowLeft'  && currentView === 'journal' && currentId !== null) {
      e.preventDefault(); navigateSession(-1);
    }
    if (e.key === 'ArrowRight' && currentView === 'journal' && currentId !== null) {
      e.preventDefault(); navigateSession(1);
    }
    const scrollEl = document.querySelector('#session-view:not(.hidden)') ||
                     document.querySelector('.content-scroll:not(.hidden)');
    if (scrollEl) {
      if (e.key === 'j') scrollEl.scrollBy({ top:  100, behavior: 'smooth' });
      if (e.key === 'k') scrollEl.scrollBy({ top: -100, behavior: 'smooth' });
    }
  });
}

// ── Tooltip 系統 ──────────────────────────────────────────
function initTooltip() {
  if (window.matchMedia('(hover: none)').matches) return; // 觸控裝置不啟用
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
          <img src="data/images/avatars/${esc(c.char)}.webp" alt="" onerror="this.style.display='none'">
        </div>
        <div class="dc-name-wrap">
          <span class="dc-char">${esc(c.char)}</span>
          <span class="dc-player">${esc(c.player)}</span>
        </div>
        <div class="dc-skull">☠</div>
        <div class="dc-count">${c.deaths}</div>
        <div class="dc-unit">次陣亡</div>
        ${c.downed != null ? `<div class="dc-downed">${c.downed} 次倒地</div>` : ''}
        ${c.death_narrative ? `<p class="dc-narrative">${esc(c.death_narrative)}</p>` : ''}
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
    const baseTip = `${c.duels.wins}勝 ${c.duels.losses}敗${draws ? ` ${draws}平` : ''}，勝率 ${pct}%`;
    const duelTip = c.duels.detail ? `${c.duels.detail}\n\n${baseTip}` : baseTip;
    return `
      <div class="duel-row" data-tip="${esc(duelTip)}">
        <div class="dr-av av-${esc(c.char)}">
          <img src="data/images/avatars/${esc(c.char)}.webp" alt="" onerror="this.style.display='none'">
        </div>
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
          <div class="dr-bar" style="width:0" data-w="${pct}%"></div>
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
        <img src="data/images/avatars/${esc(c.char)}.webp" alt="" onerror="this.style.display='none'">
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
          <img src="data/images/avatars/${esc(rowC.char)}.webp" alt="" onerror="this.style.display='none'">
        </div>
        <div class="mm-rnames">
          <span class="mm-rchar">${esc(rowC.char)}</span>
          <span class="mm-rplayer">${esc(rowC.player)}</span>
        </div>
      </th>${cells}</tr>`;
  }).join('');

  const matchupGrid = matchupData.length ? `
      <div class="stats-section-title" style="margin-top:1.5rem">對戰組合戰績</div>
      <div class="matchup-note-row">↓ 列 = 攻方視角 &nbsp;·&nbsp; 格內：<span class="mm-w-ex">勝</span> / <span class="mm-l-ex">敗</span> &nbsp;·&nbsp; hover 查看詳情</div>
      <div class="matchup-wrap">
        <table class="matchup-matrix">
          <thead><tr><th class="mm-corner">vs</th>${mmHeaders}</tr></thead>
          <tbody>${mmRows}</tbody>
        </table>
      </div>
      <p class="duel-note">* 源自日誌表格記錄；部分場次數據可能略有出入</p>` : '';

  const ffSection = renderFriendlyFire();

  inner.innerHTML = `
    <div class="sub-header">
      <div class="sub-rule"><span class="rule-line"></span><span class="sub-title">冒 險 統 計</span><span class="rule-line"></span></div>
    </div>

    <div class="hero-stats-row">
      <div class="hero-stat">
        <div class="hero-icon">⚔</div>
        <div class="hero-num" data-count="${base.count}">0</div>
        <div class="hero-label">場冒險</div>
      </div>
      <div class="hero-sep">✦</div>
      <div class="hero-stat">
        <div class="hero-icon">🧭</div>
        <div class="hero-num" data-count="${base.weeks}">0</div>
        <div class="hero-label">冒險週數</div>
      </div>
    </div>

    <div class="stat-group">
      <div class="stat-group-title">☠ 死亡紀錄</div>
      <div class="stats-section">
        <div class="stats-section-title">各角色死亡次數</div>
        <div class="death-grid">${deathCards}</div>
      </div>
      ${ffSection}
    </div>

    ${duelRows ? `
    <div class="stat-group">
      <div class="stat-group-title">⚔ 決鬥統計</div>
      <div class="stats-section">
        <div class="stats-section-title">決鬥戰績排行</div>
        <div class="duel-board">${duelRows}</div>
      </div>
      ${matchupData.length ? `<div class="stats-section">${renderMatchupSplits(matchupData)}${matchupGrid}</div>` : ''}
    </div>` : ''}

    <div class="stat-group">
      <div class="stat-group-title">💬 靠北統計</div>
      ${renderRoastSection()}
    </div>`;

  requestAnimationFrame(() => initStatsAnimations(inner));
}

// ══════════════════════════════════════════════════════════
// 統計頁動畫
// ══════════════════════════════════════════════════════════
function initStatsAnimations(container) {
  // 數字 count-up 和頂部英雄區：立即觸發
  container.querySelectorAll('.hero-num[data-count]').forEach(el => {
    countUp(el, parseInt(el.dataset.count), 800);
  });

  // 死亡卡 / 友軍卡 stagger fade-in：立即觸發
  container.querySelectorAll('.death-card, .ff-card').forEach((el, i) => {
    el.style.animationDelay = `${i * 55}ms`;
    el.classList.add('si-fade-in');
  });

  // bar 動畫：IntersectionObserver，滾動到該 stat-group 才觸發
  const scrollRoot = container.closest('.content-scroll') || null;
  const observer = new IntersectionObserver((entries, obs) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      entry.target.querySelectorAll('[data-w]').forEach(el => {
        el.style.setProperty('--bar-w', el.dataset.w);
        el.classList.add('bar-anim');
      });
      obs.unobserve(entry.target);
    });
  }, { root: scrollRoot, threshold: 0.15 });

  container.querySelectorAll('.stat-group, .stats-section').forEach(g => {
    observer.observe(g);
  });
}

function countUp(el, target, duration) {
  const start = performance.now();
  function step(now) {
    const t = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = Math.round(eased * target);
    if (t < 1) requestAnimationFrame(step);
  }
  el.textContent = '0';
  requestAnimationFrame(step);
}

// ══════════════════════════════════════════════════════════
// 友軍傷害榜
// ══════════════════════════════════════════════════════════
function renderFriendlyFire() {
  const ff = charStats.friendly_fire;
  if (!ff?.incidents?.length) return '';
  const incidents = ff.incidents.map(inc => `
    <div class="ff-card">
      <div class="ff-actors">
        <div class="ff-actor">
          <div class="ff-av av-${esc(inc.perp)}">
            <img src="data/images/avatars/${esc(inc.perp)}.webp" alt="" onerror="this.style.display='none'">
          </div>
          <span class="ff-name ff-perp">${esc(inc.perp)}</span>
          <span class="ff-role">兇手</span>
        </div>
        <div class="ff-arrow">→</div>
        <div class="ff-actor">
          <div class="ff-av av-${esc(inc.victim)}">
            <img src="data/images/avatars/${esc(inc.victim)}.webp" alt="" onerror="this.style.display='none'">
          </div>
          <span class="ff-name ff-victim">${esc(inc.victim)}</span>
          <span class="ff-role">受害者</span>
        </div>
      </div>
      <div class="ff-meta">
        <span class="ff-chapter">${esc(inc.chapter)}</span>
        <span class="ff-method">${esc(inc.method)}</span>
      </div>
      <p class="ff-desc">${esc(inc.desc)}</p>
    </div>`).join('');
  return `
    <div class="stats-section">
      <div class="stats-section-title">友軍傷害榜</div>
      <p class="ff-summary">${esc(ff.summary)}</p>
      <div class="ff-list">${incidents}</div>
    </div>`;
}

// ══════════════════════════════════════════════════════════
// 對戰勝率一覽（split bars）
// ══════════════════════════════════════════════════════════
function renderMatchupSplits(matchupData) {
  if (!matchupData.length) return '';
  const pairs = matchupData.map(m => {
    const [ca, cb] = m.chars;
    const [wa, wb] = m.wins;
    const d = m.draws || 0;
    const decisive = wa + wb;
    const pctA = decisive ? (wa / decisive * 100).toFixed(1) : 50;
    const avA = `<div class="msp-av av-${esc(ca)}"><img src="data/images/avatars/${esc(ca)}.webp" alt="" onerror="this.style.display='none'"></div>`;
    const avB = `<div class="msp-av av-${esc(cb)}"><img src="data/images/avatars/${esc(cb)}.webp" alt="" onerror="this.style.display='none'"></div>`;
    const pctB = (100 - pctA).toFixed(1);
    return `
      <div class="msp-row">
        <div class="msp-av-group">${avA}<span class="msp-name msp-a">${esc(ca)}</span></div>
        <div class="msp-pct msp-pct-a">${pctA}%</div>
        <div class="msp-bar-wrap"><div class="msp-fill" style="width:0" data-w="${pctA}%"></div></div>
        <div class="msp-pct msp-pct-b">${pctB}%</div>
        <div class="msp-av-group msp-bside"><span class="msp-name msp-b">${esc(cb)}</span>${avB}</div>
        <div class="msp-score">${wa}–${wb}${d > 0 ? ` (${d}平)` : ''}</div>
      </div>`;
  }).join('');
  return `
      <div class="stats-section-title">對戰勝率一覽</div>
      <div class="msp-board">${pairs}</div>
      <p class="duel-note">綠色條 = 左方勝場比例；底色 = 右方勝場</p>`;
}

// ══════════════════════════════════════════════════════════
// 靠北語錄大全
// ══════════════════════════════════════════════════════════
const asArr = v => Array.isArray(v) ? v : [v];

let _roastFilter = new Set();

function clearRoastFilter() {
  _roastFilter.clear();
  document.querySelectorAll('.rq-filter-btn').forEach(btn => btn.classList.remove('active'));
  const clearBtn = document.getElementById('rq-clear-btn');
  if (clearBtn) clearBtn.classList.add('hidden');
  const quotes = roastStats.quotes || roastStats.highlights || [];
  const countEl = document.getElementById('rq-count');
  if (countEl) countEl.textContent = quotes.length;
  const grid = document.getElementById('rq-grid');
  const chars = charStats.characters || [];
  if (grid) grid.innerHTML = quotes.slice().sort((a, b) => b.session - a.session).map(q => renderRoastCard(q, chars)).join('');
}

function filterRoastQuotes(charName) {
  if (_roastFilter.has(charName)) {
    _roastFilter.delete(charName);
  } else {
    _roastFilter.add(charName);
  }
  const chars = charStats.characters || [];

  // 更新篩選按鈕狀態
  document.querySelectorAll('.rq-filter-btn').forEach(btn => {
    btn.classList.toggle('active', _roastFilter.has(btn.dataset.char));
  });

  const clearBtn = document.getElementById('rq-clear-btn');
  if (clearBtn) clearBtn.classList.toggle('hidden', _roastFilter.size === 0);

  // 篩選顯示卡片（交集：所有選取角色都須出現在 from 或 to）
  const quotes = roastStats.quotes || roastStats.highlights || [];
  const filtered = _roastFilter.size === 0
    ? quotes
    : quotes.filter(q => {
        const all = [...asArr(q.from), ...asArr(q.to)];
        return [..._roastFilter].every(c => all.includes(c));
      });

  const countEl = document.getElementById('rq-count');
  if (countEl) countEl.textContent = filtered.length;

  const grid = document.getElementById('rq-grid');
  if (!grid) return;
  grid.innerHTML = filtered.slice().sort((a, b) => b.session - a.session).map(q => renderRoastCard(q, chars)).join('');
}

function renderRoastCard(q, chars) {
  const src = char => `data/images/avatars/${esc(char)}.webp`;
  const avatar = char => `<div class="rq-av av-${esc(char)}" data-tip="${esc(char)}">
          <img src="${src(char)}" alt="" onerror="this.style.display='none'">
        </div>`;
  const froms = asArr(q.from);
  const tos   = asArr(q.to);
  const sRef  = sessions.find(s => s.id === q.session);
  const cardTip = sRef ? `第 ${q.session} 集《${sRef.title}》` : `S${q.session}`;
  return `
    <div class="roast-quote-card" data-tip="${esc(cardTip)}">
      <div class="rq-actors">
        <div class="rq-av-group">${froms.map(avatar).join('')}</div>
        <span class="rq-arrow">→</span>
        <div class="rq-av-group">${tos.map(avatar).join('')}</div>
      </div>
      <div class="rq-body">
        <span class="rq-ep">S${q.session}</span>
        <span class="rq-text">${esc(q.desc)}</span>
      </div>
    </div>`;
}

function renderRoastQuotes() {
  const quotes = roastStats.quotes || roastStats.highlights || [];
  if (!quotes.length) return '';
  const chars = charStats.characters || [];

  const filterBtns = chars.map(c => `
    <button class="rq-filter-btn" data-char="${esc(c.char)}"
            onclick="filterRoastQuotes('${esc(c.char)}')"
            data-tip="${esc(c.char)}">
      <div class="rq-fav av-${esc(c.char)}">
        <img src="data/images/avatars/${esc(c.char)}.webp" alt="" onerror="this.style.display='none'">
      </div>
      <span class="rq-fname">${esc(c.char)}</span>
    </button>`).join('');

  const cards = quotes.slice().sort((a, b) => b.session - a.session).map(q => renderRoastCard(q, chars)).join('');

  return `
    <div class="stats-section">
      <div class="stats-section-title">📜 靠北語錄大全</div>
      <div class="rq-filter-row">
        <span class="rq-filter-label">篩選角色：</span>
        ${filterBtns}
        <button id="rq-clear-btn" class="rq-clear-btn hidden" onclick="clearRoastFilter()">✕ 清空</button>
        <span class="rq-total">共 <strong id="rq-count">${quotes.length}</strong> 條</span>
      </div>
      <div class="roast-quotes-grid" id="rq-grid">${cards}</div>
    </div>`;
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
    const topSenders = roastStats.matrix
      .filter(r => r.to === name).sort((a, b) => b.count - a.count).slice(0, 3)
      .map(r => `${r.from} ${r.count} 次`).join('　');
    const rbTip = topSenders ? `靠北發起者：${topSenders}` : `被靠北 ${received[name]} 次`;
    return `
      <div class="rb-row${crown}" data-tip="${esc(rbTip)}">
        <div class="rb-avatar av-${name}">
          <img src="data/images/avatars/${esc(name)}.webp" alt="" onerror="this.style.display='none'">
        </div>
        <div class="rb-info">
          <div class="rb-name">${esc(name)}<span class="rb-player">${esc(c?.player || '')}</span></div>
          <div class="rb-bar-track">
            <div class="rb-bar-fill" style="width:0" data-w="${pct}%"></div>
          </div>
        </div>
        <div class="rb-count">${received[name]}<span class="rb-unit">次</span></div>
      </div>`;
  }).join('');

  // 主動靠北排序 & mini badges
  const byInit = charNames.slice().sort((a, b) => initiated[b] - initiated[a]);
  const initBadges = byInit.map((name, i) => {
    const c = chars.find(x => x.char === name);
    const pct = Math.round(initiated[name] / maxInit * 100);
    const crown = i === 0 ? ' rb-crown' : '';
    const topTargets = roastStats.matrix
      .filter(r => r.from === name).sort((a, b) => b.count - a.count).slice(0, 3)
      .map(r => `${r.to} ${r.count} 次`).join('　');
    const ibTip = topTargets ? `主要靠北對象：${topTargets}` : `靠北 ${initiated[name]} 次`;
    return `
      <div class="ib-row${crown}" data-tip="${esc(ibTip)}">
        <div class="ib-avatar av-${name}">
          <img src="data/images/avatars/${esc(name)}.webp" alt="" onerror="this.style.display='none'">
        </div>
        <div class="ib-info">
          <div class="ib-name">${esc(name)}<span class="ib-player">${esc(c?.player || '')}</span></div>
          <div class="ib-bar-track"><div class="ib-bar-fill" style="width:0" data-w="${pct}%"></div></div>
        </div>
        <div class="ib-count">${initiated[name]}<span class="ib-unit">次</span></div>
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
        <img src="data/images/avatars/${esc(n)}.webp" alt="" onerror="this.style.display='none'">
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
          <img src="data/images/avatars/${esc(rowN)}.webp" alt="" onerror="this.style.display='none'">
        </div>
        <span class="rh-hname">${esc(rowN)}</span>
      </th>${cells}</tr>`;
  }).join('');


  return `
    <div class="stats-section">
      <div class="stats-section-title">互相靠北排行</div>
      <div class="roast-meta">全 ${sessions.filter(s => !s.placeholder && s.content && s.content.length > 0).length} 集共計 <strong>${roastStats.total || 0}</strong> 次記錄在案的靠北事件</div>

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
    </div>

    ${renderRoastQuotes()}`;
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
  const typeLabel = {
    start:       '起 點',
    boss:        '首領戰',
    location:    '地 點',
    achievement: '成 就',
    death:       '陣 亡',
    item:        '物 品',
    custom:      '特殊事件',
  };

  inner.innerHTML = `
    <div class="sub-header">
      <div class="sub-rule"><span class="rule-line"></span><span class="sub-title">里 程 碑</span><span class="rule-line"></span></div>
    </div>

    <div class="timeline">
      ${milestones.length
        ? milestones.map(m => {
            const sRef = m.session_id ? sessions.find(s => s.id === m.session_id) : null;
            const msTip = sRef
              ? `第 ${m.session_id} 集《${sRef.title}》${m.date ? '\n' + m.date.replace(/-/g,'.') : ''}`
              : (m.date || '');
            return `
          <div class="ms-item"${msTip ? ` data-tip="${esc(msTip)}"` : ''}>
            <div class="ms-dot ms-dot-${m.type || 'custom'}">${m.icon || '✦'}</div>
            <div class="ms-content">
              <div class="ms-meta">
                <span class="ms-badge ms-badge-${m.type || 'custom'}">${typeLabel[m.type] || '特殊事件'}</span>
                <span class="ms-date">${(m.date || '').replace(/-/g, '.')}</span>
              </div>
              <div class="ms-title">${esc(m.title || '')}</div>
              ${m.desc ? `<div class="ms-desc">${esc(m.desc)}</div>` : ''}
              ${m.session_id
                ? `<button class="ms-link" onclick="loadSession(${m.session_id})">前往本集 →</button>`
                : ''}
            </div>
          </div>`;
          }).join('')
        : '<p class="empty-note">尚無里程碑。請在 data/milestones.json 新增記錄。</p>'
      }
    </div>`;
}

// ══════════════════════════════════════════════════════════
// 角色頁面
// ══════════════════════════════════════════════════════════
let _selectedChar = null;

// ── 雷達圖 ────────────────────────────────────────────────────
const RADAR_DIMS = [
  { key: '嘴砲力', label: '嘴砲力', unit: '次', desc: '主動靠北次數' },
  { key: '破壞力', label: '破壞力', unit: '次', desc: '關鍵戰鬥貢獻次數' },
  { key: '抗揍力', label: '抗揍力', unit: '',   desc: '陣亡×3＋倒地×1（越低越高）' },
  { key: '決鬥力', label: '決鬥力', unit: '%',  desc: '決鬥勝率' },
  { key: '搞事力', label: '搞事力', unit: '次', desc: '被靠北次數' },
];

function buildRadarScores(allChars) {
  const matrix = roastStats.matrix || [];
  const raw = {};
  allChars.forEach(c => {
    const decisive = (c.duels?.wins || 0) + (c.duels?.losses || 0);
    const initiated = matrix.filter(r => r.from === c.char).reduce((s, r) => s + r.count, 0);
    const received  = matrix.filter(r => r.to   === c.char).reduce((s, r) => s + r.count, 0);
    raw[c.char] = {
      嘴砲力: initiated,
      破壞力: c.combat_contrib || c.praised || 0,
      抗揍力: (c.deaths || 0) * 3 + (c.downed || 0),  // 加權懲罰分（越低越好）
      決鬥力: decisive ? Math.round((c.duels.wins || 0) / decisive * 100) : 0,
      搞事力: received,
    };
  });
  // 各維度正規化到 0-100（決鬥力已是百分比；抗揍力反轉）
  const maxDowned = Math.max(...allChars.map(c => raw[c.char]['抗揍力']), 1);  // 加權懲罰最大值
  const norm = {};
  allChars.forEach(c => {
    norm[c.char] = {};
    RADAR_DIMS.forEach(d => {
      if (d.key === '決鬥力') {
        norm[c.char][d.key] = raw[c.char][d.key];
      } else if (d.key === '抗揍力') {
        // 倒地越少分越高
        norm[c.char][d.key] = Math.round((maxDowned - raw[c.char][d.key]) / maxDowned * 100);
      } else {
        const max = Math.max(...allChars.map(c2 => raw[c2.char][d.key]), 1);
        norm[c.char][d.key] = Math.round(raw[c.char][d.key] / max * 100);
      }
    });
  });
  return { raw, norm };
}

function renderRadarSvg(scores) {
  const cx = 148, cy = 148, r = 108;
  const n = RADAR_DIMS.length;
  const angles = RADAR_DIMS.map((_, i) => -Math.PI / 2 + i * 2 * Math.PI / n);

  const pt = (val, idx) => {
    const a = angles[idx];
    const d = r * val / 100;
    return [cx + d * Math.cos(a), cy + d * Math.sin(a)];
  };

  // 網格
  const grid = [20, 40, 60, 80, 100].map(pct => {
    const pts = angles.map((a, i) => pt(pct, i).join(',')).join(' ');
    return `<polygon points="${pts}" fill="none" stroke="rgba(80,45,15,0.12)" stroke-width="1"/>`;
  }).join('');

  // 軸線
  const axes = angles.map((a, i) => {
    const [x, y] = pt(100, i);
    return `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="rgba(80,45,15,0.18)" stroke-width="1"/>`;
  }).join('');

  // 資料多邊形
  const dataPts = scores.map((v, i) => pt(v, i).join(',')).join(' ');
  const poly = `<polygon points="${dataPts}" fill="rgba(122,21,21,0.12)" stroke="rgba(122,21,21,0.75)" stroke-width="2" stroke-linejoin="round"/>`;

  // 節點
  const dots = scores.map((v, i) => {
    const [x, y] = pt(v, i);
    return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.2" fill="var(--crimson)" opacity="0.9"/>`;
  }).join('');

  // 標籤
  const labels = RADAR_DIMS.map((d, i) => {
    const [x, y] = pt(128, i);
    const anchor = x < cx - 6 ? 'end' : x > cx + 6 ? 'start' : 'middle';
    const dy = y < cy - 6 ? '-0.3em' : y > cy + 6 ? '1em' : '0.35em';
    return `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="${anchor}" dy="${dy}"
      font-size="10.5" fill="rgba(60,35,10,0.75)" font-family="Noto Sans TC, sans-serif" font-weight="500">${d.label}</text>`;
  }).join('');

  return `<svg viewBox="0 0 296 296" width="280" height="280" style="overflow:visible">${grid}${axes}${poly}${dots}${labels}</svg>`;
}

function renderRadarSection(c, allChars) {
  const { raw, norm } = buildRadarScores(allChars);
  const scores = RADAR_DIMS.map(d => norm[c.char][d.key]);
  const rawVals = raw[c.char];
  const svg = renderRadarSvg(scores);
  const statRows = RADAR_DIMS.map(d => {
    let display;
    if (d.key === '抗揍力') {
      display = `陣亡${c.deaths || 0} 倒地${c.downed || 0}`;
    } else {
      display = `${rawVals[d.key]}${d.unit}`;
    }
    return `
    <div class="radar-stat">
      <span class="radar-stat-label">${d.label}</span>
      <span class="radar-stat-val">${display}</span>
      <span class="radar-stat-desc">${d.desc}</span>
    </div>`;
  }).join('');
  return `
    <div class="cp-section">
      <div class="cp-section-title">🕸 角色特質</div>
      <div class="radar-wrap">
        <div class="radar-svg-box">${svg}</div>
        <div class="radar-stats">${statRows}</div>
      </div>
    </div>`;
}

let _charSwipeX = null, _charSwipeY = null, _charSwipeDir = null, _charSwipeDx = 0;

function initCharSwipe() {
  const view = document.getElementById('characters-view');
  if (!view || view.dataset.swipe) return;
  view.dataset.swipe = '1';

  view.addEventListener('touchstart', e => {
    _charSwipeX = e.touches[0].clientX;
    _charSwipeY = e.touches[0].clientY;
    _charSwipeDir = null;
    _charSwipeDx = 0;
    const inner = document.getElementById('characters-inner');
    if (inner) inner.style.transition = 'none';
  }, { passive: true });

  view.addEventListener('touchmove', e => {
    if (_charSwipeX === null) return;
    const dx = e.touches[0].clientX - _charSwipeX;
    const dy = e.touches[0].clientY - _charSwipeY;
    if (_charSwipeDir === null) {
      if (Math.abs(dx) > Math.abs(dy) + 5) _charSwipeDir = 'h';
      else if (Math.abs(dy) > Math.abs(dx) + 5) { _charSwipeX = null; return; }
      else return;
    }
    if (_charSwipeDir !== 'h') return;
    _charSwipeDx = dx;
    const inner = document.getElementById('characters-inner');
    if (inner) inner.style.transform = `translateX(${dx}px)`;
  }, { passive: true });

  view.addEventListener('touchend', () => {
    if (_charSwipeX === null) return;
    const dx = _charSwipeDx;
    _charSwipeX = null;
    const inner = document.getElementById('characters-inner');
    const chars = charStats.characters || [];
    const idx = chars.findIndex(c => c.char === _selectedChar);
    const canNext = dx < -50 && idx < chars.length - 1;
    const canPrev = dx >  50 && idx > 0;

    if (!canNext && !canPrev) {
      // 回彈
      if (inner) { inner.style.transition = 'transform 0.28s ease'; inner.style.transform = 'translateX(0)'; }
      return;
    }
    // 滑出
    const slideOut = dx < 0 ? '-110%' : '110%';
    if (inner) { inner.style.transition = 'transform 0.25s ease'; inner.style.transform = `translateX(${slideOut})`; }
    setTimeout(() => {
      const newChar = canNext ? chars[idx + 1].char : chars[idx - 1].char;
      renderCharacters(newChar);
      // 新內容從反方向滑入
      const slideIn = dx < 0 ? '110%' : '-110%';
      const ni = document.getElementById('characters-inner');
      if (ni) {
        ni.style.transition = 'none';
        ni.style.transform = `translateX(${slideIn})`;
        requestAnimationFrame(() => requestAnimationFrame(() => {
          ni.style.transition = 'transform 0.28s ease';
          ni.style.transform = 'translateX(0)';
        }));
      }
    }, 240);
  });
}

function renderCharacters(charName) {
  const inner = document.getElementById('characters-inner');
  const chars = charStats.characters || [];
  if (!chars.length) { inner.innerHTML = '<p class="empty-note">無角色資料</p>'; return; }

  if (!charName) charName = _selectedChar || chars[0].char;
  _selectedChar = charName;
  initCharSwipe();

  const portraitBtns = chars.map(c => `
    <button class="cp-portrait-btn${c.char === charName ? ' active' : ''}"
            onclick="renderCharacters('${c.char}')"
            data-tip="${esc(c.player)} · ${esc(c.class)}">
      <div class="cp-pav av-${esc(c.char)}">
        <img src="data/images/avatars/${esc(c.char)}.webp" alt="" onerror="this.style.display='none'">
      </div>
      <span class="cp-pname">${esc(c.char)}</span>
    </button>`).join('');

  const c = chars.find(x => x.char === charName) || chars[0];
  const decisive = (c.duels.wins || 0) + (c.duels.losses || 0);
  const pct = decisive ? Math.round(c.duels.wins / decisive * 100) : 0;

  const quotesHtml = (c.quotes || []).map(q => `
    <div class="cp-quote-card">
      <div class="cp-qmark">「</div>
      <blockquote class="cp-qtext">${esc(q.text)}</blockquote>
      <div class="cp-qsession">S${q.session}</div>
    </div>`).join('');

  const achieveHtml = (c.achievements || []).map(a => `
    <div class="cp-achieve">
      <div class="cp-a-icon">${a.icon}</div>
      <div class="cp-a-body">
        <div class="cp-a-name">${esc(a.name)}</div>
        <div class="cp-a-desc">${esc(a.desc)}</div>
      </div>
    </div>`).join('');

  inner.innerHTML = `
    <div class="sub-header">
      <div class="sub-rule"><span class="rule-line"></span><span class="sub-title">角 色 檔 案</span><span class="rule-line"></span></div>
    </div>

    <div class="cp-portrait-row">${portraitBtns}</div>

    <div class="cp-detail">
      <div class="cp-hero">
        <div class="cp-hero-av av-${esc(c.char)}">
          <img src="data/images/avatars/${esc(c.char)}.webp" alt="" onerror="this.style.display='none'">
        </div>
        <div class="cp-hero-info">
          <div class="cp-char-name">${esc(c.char)}</div>
          <div class="cp-class-pill">${esc(c.class)}</div>
          <div class="cp-player-name">${esc(c.player)} 飾演</div>
          <div class="cp-quick-stats">
            <span class="cp-qs-item"><span class="cp-qs-icon">☠</span>${c.deaths} 次陣亡</span>
            <span class="cp-qs-sep">·</span>
            <span class="cp-qs-item"><span class="cp-qs-icon">⚔</span>${c.duels.wins}勝${c.duels.losses}敗${c.duels.draws > 0 ? c.duels.draws + '平' : ''}</span>
            <span class="cp-qs-sep">·</span>
            <span class="cp-qs-item ${pct >= 50 ? 'cp-qs-win' : 'cp-qs-lose'}">${pct}%</span>
            <span class="cp-qs-sep">·</span>
            <span class="cp-qs-item"><span class="cp-qs-icon">🏆</span>${c.mvp_count || 0} 次 MVP</span>
          </div>
        </div>
      </div>

      ${renderRadarSection(c, chars)}

      ${c.ai_intro ? `
      <div class="cp-section">
        <div class="cp-section-title">✦ 角色摘要</div>
        <p class="cp-intro">${esc(c.ai_intro)}</p>
      </div>` : ''}

      ${c.quotes?.length ? `
      <div class="cp-section">
        <div class="cp-section-title">💬 名言錄</div>
        <div class="cp-quotes">${quotesHtml}</div>
      </div>` : ''}

      ${c.achievements?.length ? `
      <div class="cp-section">
        <div class="cp-section-title">🏆 成就</div>
        <div class="cp-achieves">${achieveHtml}</div>
      </div>` : ''}

      ${c.death_narrative ? `
      <div class="cp-section">
        <div class="cp-section-title">☠ 死亡紀錄</div>
        <p class="cp-narrative">${esc(c.death_narrative)}</p>
        ${(c.death_notes || []).length ? `
        <div class="cp-death-notes">
          ${c.death_notes.map(n => `<div class="cp-death-note">— ${esc(n)}</div>`).join('')}
        </div>` : ''}
      </div>` : ''}

      ${c.duels?.detail ? `
      <div class="cp-section">
        <div class="cp-section-title">⚔ 決鬥歷程</div>
        <p class="cp-duel-detail">${esc(c.duels.detail)}</p>
      </div>` : ''}
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

function makeQuoteWrap(speaker, content, attr) {
  return `<div class="quote-wrap">
    <div class="char-avatar av-${esc(speaker)}" aria-label="${esc(speaker)}" data-tip="${esc(speaker)}">
      <img src="data/images/avatars/${speaker}.webp" alt="" loading="lazy">
    </div>
    <blockquote class="char-quote">
      ${renderInline('「' + content + '」')}
      <cite class="dq-attr">—— ${esc(attr)}</cite>
    </blockquote>
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
      default: {
        // Pattern 1: 「...」——角色名
        const qm = item.v.match(/^「([\s\S]+?)」[—\-]{1,2}(.{1,12})$/);
        if (qm) {
          const speaker = resolveChar(qm[2].trim());
          if (speaker) {
            return makeQuoteWrap(speaker, qm[1], qm[2].trim());
          }
        }
        // Pattern 2: 角色[描述]：「...」
        const qm2 = item.v.match(/^([^「]{1,30})：「([\s\S]+?)」$/);
        if (qm2) {
          const speaker = resolveChar(qm2[1]);
          if (speaker) {
            return makeQuoteWrap(speaker, qm2[2], speaker);
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

// ══════════════════════════════════════════════════════════
// 故事分頁
// ══════════════════════════════════════════════════════════
let _storyScrollObserver = null;

function renderStoryNav() {
  const list = document.getElementById('story-chapter-list');
  if (!list) return;
  const chapters = (storyData.chapters || []).slice().sort((a, b) => a.session_id - b.session_id);
  const romanNumerals = ['I','II','III','IV','V','VI','VII','VIII','IX','X',
    'XI','XII','XIII','XIV','XV','XVI','XVII','XVIII','XIX','XX'];

  list.innerHTML = chapters.map((ch, i) => {
    const num = romanNumerals[i] || (i + 1);
    return `<li class="session-item" id="story-nav-${ch.session_id}"
        onclick="storyScrollTo(${ch.session_id})">
      <div class="item-chapter">第 ${num} 章</div>
      <div class="item-title">${esc(ch.title || '')}</div>
    </li>`;
  }).join('');

  // 重建 scroll-spy
  if (_storyScrollObserver) _storyScrollObserver.disconnect();
  const sv = document.getElementById('story-view');
  _storyScrollObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const sid = entry.target.dataset.sid;
        list.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
        const nav = document.getElementById('story-nav-' + sid);
        if (nav) {
          nav.classList.add('active');
          nav.scrollIntoView({ block: 'nearest' });
        }
      }
    });
  }, { root: sv, rootMargin: '-5% 0px -50% 0px', threshold: 0 });

  chapters.forEach(ch => {
    const el = document.getElementById('story-ch-' + ch.session_id);
    if (el) {
      el.dataset.sid = ch.session_id;
      _storyScrollObserver.observe(el);
    }
  });
}

function storyScrollTo(sid) {
  const t = document.getElementById('story-ch-' + sid);
  const sv = document.getElementById('story-view');
  if (t && sv) sv.scrollTo({ top: t.offsetTop - 24, behavior: 'smooth' });
  if (window.innerWidth < 768) toggleSidebar();
}

function renderStory() {
  const inner = document.getElementById('story-inner');
  if (!inner) return;

  const chapters = (storyData.chapters || []).slice().sort((a, b) => a.session_id - b.session_id);

  if (!chapters.length) {
    inner.innerHTML = `
      <div class="sub-header">
        <div class="sub-rule"><span class="rule-line"></span><span class="sub-title">瓦羅的故事集</span><span class="rule-line"></span></div>
      </div>
      <div class="story-empty">
        故事尚未生成。<br>新增集數後執行 <code>python3 update_stats.py</code> 即可自動產生。
      </div>`;
    return;
  }

  const romanNumerals = ['I','II','III','IV','V','VI','VII','VIII','IX','X',
    'XI','XII','XIII','XIV','XV','XVI','XVII','XVIII','XIX','XX'];

  inner.innerHTML = `
    <div class="sub-header">
      <div class="sub-rule"><span class="rule-line"></span><span class="sub-title">瓦羅的故事集</span><span class="rule-line"></span></div>
    </div>
    <div class="story-chapters">
      ${chapters.map((ch, i) => {
        const num = romanNumerals[i] || (i + 1);
        const paragraphs = (ch.text || '').split(/\n+/).filter(p => p.trim())
          .map(p => `<p class="story-para">${esc(p.trim())}</p>`).join('');
        return `
          ${i > 0 ? '<div class="story-sep">✦ ✦ ✦</div>' : ''}
          <div class="story-chapter" id="story-ch-${ch.session_id}">
            <div class="story-chapter-eyebrow">第 ${num} 章</div>
            <h2 class="story-chapter-title">${esc(ch.title || '')}</h2>
            <div class="story-body">${paragraphs}</div>
          </div>`;
      }).join('')}
    </div>`;
}
