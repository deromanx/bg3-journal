#!/usr/bin/env python3
"""llm.py — 所有 gen/count 腳本共用的 LLM 呼叫入口。

模式由環境變數 BG3_LLM 決定（update_all.sh 會設定）：

- claude（預設）：不呼叫任何外部 API。
    先查 data/llm/answers/{key}.txt，有就當作模型回應直接回傳；
    沒有就把 prompt 寫進 data/llm/pending/{key}.prompt.txt，回傳 returncode=4。
    由 Claude Code session 內依 `python3 llm_queue.py list` 讀待辦、把答案寫到
    answers/ 後重跑 pipeline。答案以 prompt 雜湊為 key：日誌內容被回頭修改時
    prompt 改變、自動產生新待辦，不會誤用舊答案。
- gemini：原本的 `gemini -p`（備援；需 GEMINI_API_KEY，用 zsh -ic 執行）。

回傳值模擬 subprocess.CompletedProcess（returncode / stdout / stderr），
各腳本原本的錯誤處理與 JSON 解析完全不用改。
"""

import hashlib
import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

LLM_DIR = Path(__file__).parent / "data" / "llm"
PENDING = LLM_DIR / "pending"
ANSWERS = LLM_DIR / "answers"

PENDING_RC = 4


def mode() -> str:
    m = os.environ.get("BG3_LLM", "claude").strip().lower()
    return m if m in ("claude", "gemini") else "claude"


def _sha(s: str, n: int = 8) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def _key(task: str, ident, prompt: str) -> str:
    ident = re.sub(r"[^\w一-鿿-]", "_", str(ident))
    return f"{task}__{ident}__{_sha(prompt)}"


def run(prompt: str, *, task: str, ident, text: str = None,
        timeout: int = 600, env: dict = None):
    """呼叫 LLM。

    task : 任務名（檔名用，例：analyze、praised、story）
    ident: 這次呼叫的對象（集數 id 或角色名）
    text : prompt 內嵌的日誌原文；claude 模式會把它抽成獨立檔（同內容去重），
           待辦 prompt 只留指向該檔的標記，避免同一集原文重複讀十次。
    """
    if mode() == "gemini":
        return subprocess.run(["gemini", "-p", prompt], capture_output=True,
                              text=True, timeout=timeout, env=env)

    key = _key(task, ident, prompt)
    ans = ANSWERS / f"{key}.txt"
    pend = PENDING / f"{key}.prompt.txt"
    if ans.exists():
        if pend.exists():
            pend.unlink()
        return SimpleNamespace(returncode=0, stdout=ans.read_text("utf-8"), stderr="")

    PENDING.mkdir(parents=True, exist_ok=True)
    ANSWERS.mkdir(parents=True, exist_ok=True)
    body = prompt
    if text and text in prompt:
        # 截斷版（如前 3000 字）若是既有全文檔的開頭，就指向全文檔，免得同集讀兩份
        full = next((f for f in PENDING.glob(f"text__{ident}__*.txt")
                     if f.read_text("utf-8").startswith(text)), None)
        if full and len(full.read_text("utf-8")) > len(text):
            marker = f"〔日誌原文見 {full.name} 的前 {len(text)} 字〕"
        else:
            tf = full or PENDING / f"text__{ident}__{_sha(text)}.txt"
            if not tf.exists():
                tf.write_text(text, "utf-8")
            marker = f"〔日誌原文見 {tf.name}（{len(text)} 字）〕"
        body = prompt.replace(text, marker)
    header = (f"# task={task} ident={ident}\n"
              f"# 答案寫到：{ans}\n"
              f"# 內容＝模型應回傳的原始文字（照下方格式要求，通常是純 JSON）\n\n")
    pend.write_text(header + body, "utf-8")
    return SimpleNamespace(returncode=PENDING_RC, stdout="",
                           stderr=f"⏸ 等待 Claude 作答：{pend.name}")


def pending() -> list:
    """尚未作答的待辦（已有答案的順手清掉）。"""
    if not PENDING.exists():
        return []
    out = []
    for p in sorted(PENDING.glob("*.prompt.txt")):
        if (ANSWERS / p.name.replace(".prompt.txt", ".txt")).exists():
            p.unlink()
        else:
            out.append(p)
    return out
