/**
 * Card spotlight effect — follows the mouse cursor over .card-spotlight elements.
 * Loaded as an external script for CSP compliance (no inline scripts needed).
 */
document.addEventListener("mousemove", function (e) {
  var t = e.target;
  while (t && t !== document) {
    if (t.classList && t.classList.contains("card-spotlight")) {
      var r = t.getBoundingClientRect();
      t.style.setProperty("--spotlight-x", e.clientX - r.left + "px");
      t.style.setProperty("--spotlight-y", e.clientY - r.top + "px");
      return;
    }
    t = t.parentElement;
  }
});
