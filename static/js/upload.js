// upload helper (used by upload.html if preferred)
async function uploadFile(file, token) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/upload', { method: 'POST', headers: { 'Authorization': 'Bearer ' + token }, body: fd });
  return res.json();
}
