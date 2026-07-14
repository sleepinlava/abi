/**
 * ABI Docs — Language toggle widget.
 *
 * Injects a small language switcher next to the Furo sidebar brand
 * so readers can flip between English and Chinese versions.
 */
document.addEventListener("DOMContentLoaded", function () {
  var sidebarBrand = document.querySelector(".sidebar-brand");
  if (!sidebarBrand) return;

  // Determine current language from path
  var path = window.location.pathname;
  var isZh = path.indexOf("/zh/") !== -1;
  var isEn = path.indexOf("/en/") !== -1;

  var currentLabel = isZh ? "中文" : "EN";
  var otherLabel = isZh ? "EN" : "中文";
  // Language roots are relative to the current language directory. This works
  // both under GitHub Pages project paths (for example /abi/) and local builds,
  // and safely falls back when the current page has no translation.
  var currentPath = "./";
  var otherPath = isZh ? "../en/" : "../zh/";
  var pageName = path.split(isZh ? "/zh/" : "/en/")[1] || "";
  var translatedPath = otherPath + pageName;

  var widget = document.createElement("span");
  widget.className = "lang-toggle";
  widget.innerHTML =
    '<a href="' + currentPath + '" class="active" aria-current="page">' +
    currentLabel +
    "</a>" +
    '<a href="' + otherPath + '">' + otherLabel + "</a>";

  sidebarBrand.appendChild(widget);

  var otherLink = widget.lastElementChild;
  otherLink.addEventListener("click", function (event) {
    if (!pageName) return;
    event.preventDefault();
    fetch(translatedPath, { method: "HEAD" })
      .then(function (response) {
        window.location.href = response.ok ? translatedPath : otherPath;
      })
      .catch(function () {
        window.location.href = otherPath;
      });
  });
});
