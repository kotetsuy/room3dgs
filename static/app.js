// room3dgs アップロード＆セット管理（バニラ JS, CDN 非依存）
const $ = (s) => document.querySelector(s);
let picked = [];      // 選択中の File[]
let MAX_SETS = 3;
let pollTimers = {};  // set_id -> interval

const STATUS_LABEL = {
  none: "未生成", running: "生成中…", done: "生成済み", error: "エラー",
};

// ---------- 新規セット作成 ----------
const drop = $("#drop");
const fileInput = $("#files");
const saveBtn = $("#save-btn");

drop.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => setPicked([...fileInput.files]));

["dragenter", "dragover"].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("drag"); }));
drop.addEventListener("drop", (e) => {
  const fs = [...e.dataTransfer.files].filter((f) => f.type.startsWith("image/"));
  setPicked(fs);
});

function setPicked(files) {
  picked = files;
  $("#pick-count").textContent = files.length ? `${files.length} 枚を選択中` : "";
  saveBtn.disabled = files.length < 2 || !$("#set-name").value.trim();
}
$("#set-name").addEventListener("input", () => {
  saveBtn.disabled = picked.length < 2 || !$("#set-name").value.trim();
});

$("#new-set-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#new-set-msg");
  msg.className = "msg";
  if (picked.length < 2) { msg.textContent = "写真を2枚以上選んでください"; return; }

  const fd = new FormData();
  fd.append("name", $("#set-name").value.trim());
  picked.forEach((f) => fd.append("files", f));

  saveBtn.disabled = true;
  msg.textContent = "アップロード中…";
  try {
    const res = await fetch("/api/sets", { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    msg.className = "msg ok";
    msg.textContent = "保存しました";
    $("#new-set-form").reset();
    setPicked([]);
    await loadSets();
  } catch (err) {
    msg.className = "msg err";
    msg.textContent = "失敗: " + err.message;
  } finally {
    saveBtn.disabled = picked.length < 2;
  }
});

// ---------- 一覧描画 ----------
async function loadSets() {
  const res = await fetch("/api/sets");
  const data = await res.json();
  MAX_SETS = data.max;
  $("#set-count").textContent = `(${data.sets.length}/${MAX_SETS})`;
  saveBtn.disabled = data.sets.length >= MAX_SETS || picked.length < 2;

  const grid = $("#sets");
  grid.innerHTML = "";
  if (data.sets.length === 0) {
    grid.innerHTML = '<p class="empty">まだセットがありません。上から写真を追加してください。</p>';
    return;
  }
  for (const s of data.sets) grid.appendChild(renderCard(s));
}

function renderCard(s) {
  const card = document.createElement("div");
  card.className = "card";
  const thumb = s.images && s.images.length
    ? `/api/sets/${s.id}/thumb/${s.images[0]}` : "";
  const gauss = s.num_gaussians ? ` ・ ${s.num_gaussians.toLocaleString()} ガウシアン` : "";
  card.innerHTML = `
    <img class="thumb" src="${thumb}" alt="">
    <div class="body">
      <div class="name">${escapeHtml(s.name)}</div>
      <div class="meta">${s.num_images} 枚${gauss}</div>
      <div><span class="badge ${s.status}" data-badge>${STATUS_LABEL[s.status] || s.status}</span></div>
      <div class="msg" data-msg>${escapeHtml(s.status === "error" ? s.message : "")}</div>
      <div class="actions">
        <button class="secondary" data-recon ${s.status === "running" ? "disabled" : ""}>
          ${s.has_ply ? "再生成" : "3Dを作成"}
        </button>
        ${s.has_ply ? `<a href="/viewer?set=${s.id}">3Dを見る</a>` : ""}
        <button class="danger" data-del>削除</button>
      </div>
    </div>`;

  card.querySelector("[data-recon]").addEventListener("click", () => startRecon(s.id, card));
  card.querySelector("[data-del]").addEventListener("click", () => delSet(s.id, s.name));
  if (s.status === "running") pollStatus(s.id, card);
  return card;
}

// ---------- 再構成 ----------
async function startRecon(id, card) {
  const btn = card.querySelector("[data-recon]");
  btn.disabled = true;
  setBadge(card, "running", "生成中…");
  try {
    const res = await fetch(`/api/sets/${id}/reconstruct`, { method: "POST" });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    pollStatus(id, card);
  } catch (err) {
    setBadge(card, "error", "");
    card.querySelector("[data-msg]").textContent = "失敗: " + err.message;
    btn.disabled = false;
  }
}

function pollStatus(id, card) {
  clearInterval(pollTimers[id]);
  pollTimers[id] = setInterval(async () => {
    try {
      const res = await fetch(`/api/sets/${id}/status`);
      const st = await res.json();
      if (st.status === "running") {
        setBadge(card, "running", "生成中…");
        return;
      }
      clearInterval(pollTimers[id]);
      if (st.status === "error") {
        setBadge(card, "error", "");
        card.querySelector("[data-msg]").textContent = st.message || "エラー";
        card.querySelector("[data-recon]").disabled = false;
      } else {
        await loadSets(); // done → カード再描画（見るボタン出現）
      }
    } catch (_) { /* 継続 */ }
  }, 3000);
}

function setBadge(card, status, text) {
  const b = card.querySelector("[data-badge]");
  b.className = "badge " + status;
  b.textContent = text || (STATUS_LABEL[status] || status);
}

async function delSet(id, name) {
  if (!confirm(`セット「${name}」を削除しますか？（写真と .ply も消えます）`)) return;
  clearInterval(pollTimers[id]);
  await fetch(`/api/sets/${id}`, { method: "DELETE" });
  await loadSets();
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

loadSets();
