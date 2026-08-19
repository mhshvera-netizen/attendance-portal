// JNTUACEA Attendance Helper - content script
// Official portal pages lo mana extractor ni page context lo inject chestundi.
// (Page context lo inject cheyadam endukante: same-origin fetch kavali - portal
//  session cookies tho data read cheyadaniki.)
(function () {
  if (window.__jnExtLoaded) return;
  window.__jnExtLoaded = true;
  try {
    var s = document.createElement('script');
    s.src = chrome.runtime.getURL('extractor.js');
    s.onload = function () { this.remove(); };
    (document.head || document.documentElement).appendChild(s);
  } catch (e) {}
})();
