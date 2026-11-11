(async () => {
  await window.magpie.ready;
  const destination = window.magpie.service || "http://127.0.0.1:3496/";
  window.location.replace(destination);
})().catch(error => { document.getElementById("status").textContent = error.message; });
