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

  // Build relative path to the other language
  var otherPath;
  if (isZh) {
    otherPath = path.replace("/zh/", "/en/");
  } else if (isEn) {
    otherPath = path.replace("/en/", "/zh/");
  } else {
    // At root or unknown — default to /en/
    otherPath = "/en/";
  }

  var currentLabel = isZh ? "中文" : "EN";
  var otherLabel = isZh ? "EN" : "中文";
  var currentPath = isZh ? "/zh/" : "/en/";

  var widget = document.createElement("span");
  widget.className = "lang-toggle";
  widget.innerHTML =
    '<a href="' + currentPath + '" class="active">' + currentLabel + "</a>" +
    '<a href="' + otherPath + '">' + otherLabel + "</a>";

  sidebarBrand.appendChild(widget);
});
