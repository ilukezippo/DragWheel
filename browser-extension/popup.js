const api = typeof browser !== "undefined" ? browser : chrome;
const status = document.getElementById("status");

api.runtime.sendMessage({ type: "ping" }, (r) => {
  if (r && r.ok) {
    status.textContent = "Connected to DragWheel " + (r.version || "");
  } else {
    status.className = "bad";
    status.innerHTML = 'DragWheel isn\'t found on this PC. <a href="https://ilukezippo.github.io/DragWheel/#browser" target="_blank">Get DragWheel 1.2.3 or newer</a>, open it once, then try again.';
  }
});

document.getElementById("play").addEventListener("click", () => {
  api.runtime.sendMessage({ type: "float-tab" }, (r) => {
    if (r && r.ok) window.close();
    else { status.className = "bad"; status.textContent = (r && r.error) || "Couldn't play this page."; }
  });
});
