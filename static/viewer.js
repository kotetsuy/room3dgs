// room3dgs ビューアのオーバーレイ配線（3DGS 描画は splat-viewer.js が担当）
(() => {
  const params = new URLSearchParams(location.search);
  const setId = params.get("set");
  const dl = document.getElementById("download");
  const title = document.getElementById("title");
  const message = document.getElementById("message");

  if (!setId) {
    if (message) message.innerText = "set が指定されていません（/viewer?set=<id>）";
    if (dl) dl.style.display = "none";
    return;
  }

  // .ply ダウンロードリンク
  if (dl) dl.href = `/api/sets/${setId}/scene.ply`;

  // タイトルにセット名を表示
  fetch("/api/sets")
    .then((r) => r.json())
    .then((data) => {
      const s = (data.sets || []).find((x) => x.id === setId);
      if (s && title) {
        title.textContent = s.name + (s.num_gaussians ? `（${s.num_gaussians.toLocaleString()} ガウシアン）` : "");
        document.title = `room3dgs — ${s.name}`;
      }
    })
    .catch(() => {});
})();
