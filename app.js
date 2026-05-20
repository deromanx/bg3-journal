/* ============================================================
   BG3 冒險日誌 v3 — 前端邏輯
   sessions.json 格式：content 為結構化 item 陣列
   ============================================================ */

let sessions = [];
let currentId = null;

// ── 載入 ──────────────────────────────────────────────────
fetch('data/sessions.json')
  .then(r => r.json())
  .then(data => {
    sessions = data;
    renderSidebar();
    // 預設載入最新的非占位集數
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

// ── 側欄（最新集在最上方）──────────────────────────────────
function renderSidebar() {
  const list = document.getElementById('session-list');
  list.innerHTML = sessions.slice().reverse().map(s => {
    const imgCount = s.content?.filter(i => i.t === 'img').length ?? 0;
    const imgLabel = imgCount > 0 ? `<div class="item-imgs">📷 ${imgCount} 張</div>` : '';
    return `
    <li class="session-item${s.placeholder ? ' placeholder' : ''}"
        data-id="${s.id}"
        onclick="loadSession(${s.id})"
        title="${esc(s.title)}">
      <div class="item-chapter">${esc(s.chapter)}</div>
      <div class="item-date">${s.date?.replace(/-/g, '.') ?? ''}</div>
      <div class="item-title">${esc(s.title)}</div>
      ${imgLabel}
    </li>`;
  }).join('');
}

// ── 載入場次 ──────────────────────────────────────────────
function loadSession(id) {
  const session = sessions.find(s => s.id === id);
  if (!session) return;
  currentId = id;

  document.querySelectorAll('.session-item').forEach(el => {
    el.classList.toggle('active', +el.dataset.id === id);
  });
  document.querySelector('.session-item.active')?.scrollIntoView({ block: 'nearest' });

  document.getElementById('welcome').classList.add('hidden');
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

  const idx = sessions.findIndex(s => s.id === id);
  document.getElementById('prev-btn').disabled = idx <= 0;
  document.getElementById('next-btn').disabled = idx >= sessions.length - 1;

  if (window.innerWidth <= 720) {
    document.getElementById('sidebar').classList.remove('open');
  }
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

// ── 結構化內容渲染 ────────────────────────────────────────
function renderContent(items) {
  if (!items?.length) return '<p style="text-align:center;opacity:.4">尚無內容</p>';

  return items.map((item, i) => {
    switch (item.t) {
      case 'img':
        return `<figure class="session-img">
          <img src="${esc(item.v)}" alt="" loading="lazy">
        </figure>`;

      case 'h1':
        // 在第一個 h1 之前不插入分隔符；其後每個插入裝飾奇幻飾條
        const ornament = i > 0
          ? `<div class="section-ornament"><span>◆</span></div>`
          : '';
        return `${ornament}<h2 class="section-h1">${renderInline(item.v)}</h2>`;

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
