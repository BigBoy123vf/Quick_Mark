/* Manual map location picker: click/drag a pin or search an address, no GPS involved. */
(function () {
  "use strict";

  // Raw paths, not static_v()-templated: this is a plain .js file with no Jinja processing.
  var LEAFLET_JS_URL = "/static/js/vendor/leaflet.js";
  var LEAFLET_CSS_URL = "/static/css/vendor/leaflet.css";
  var NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search";
  var FALLBACK_CENTRE = [5.1053, -1.2466]; // Cape Coast, Ghana
  var FALLBACK_ZOOM = 16;
  var PICKED_ZOOM = 17;
  var SEARCH_MIN_INTERVAL_MS = 1100; // Nominatim's usage policy: at most ~1 request/second.

  var leafletLoadPromise = null;
  var mapInstance = null;
  var pinMarker = null;
  var radiusCircle = null;
  var pickedPoint = null;
  var lastConfirmCallback = null;
  var elementFocusedBeforeOpen = null;
  var lastSearchRequestTime = 0;
  var scanRadiusMetres = null;

  function byId(elementId) {
    return document.getElementById(elementId);
  }

  function loadStylesheet(href) {
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    document.head.appendChild(link);
  }

  function loadLeaflet() {
    if (leafletLoadPromise) {
      return leafletLoadPromise;
    }
    leafletLoadPromise = new Promise(function (resolve, reject) {
      if (window.L) {
        resolve(window.L);
        return;
      }
      loadStylesheet(LEAFLET_CSS_URL);
      var script = document.createElement("script");
      script.src = LEAFLET_JS_URL;
      script.onload = function () { resolve(window.L); };
      script.onerror = function () { reject(new Error("Couldn't load the map library.")); };
      document.head.appendChild(script);
    });
    return leafletLoadPromise;
  }

  function pinIcon() {
    return window.L.divIcon({
      className: "location-picker-pin-wrap",
      html: '<span class="location-picker-pin"></span>',
      iconSize: [18, 18],
      iconAnchor: [9, 18],
    });
  }

  function setConfirmEnabled(enabled) {
    byId("location-picker-confirm-btn").disabled = !enabled;
  }

  function setPoint(latlng, recentre) {
    pickedPoint = { lat: latlng.lat, lng: latlng.lng };
    if (!pinMarker) {
      pinMarker = window.L.marker(latlng, { draggable: true, icon: pinIcon() }).addTo(mapInstance);
      pinMarker.on("drag", function (event) { setPoint(event.target.getLatLng(), false); });
      radiusCircle = window.L.circle(latlng, {
        radius: scanRadiusMetres,
        color: "#2563eb",
        weight: 2,
        fillColor: "#2563eb",
        fillOpacity: 0.12,
      }).addTo(mapInstance);
    } else {
      pinMarker.setLatLng(latlng);
      radiusCircle.setLatLng(latlng);
    }
    setConfirmEnabled(true);
    if (recentre) {
      mapInstance.setView(latlng, PICKED_ZOOM);
    }
  }

  function initMap(initialPoint) {
    var centre = initialPoint ? [initialPoint.latitude, initialPoint.longitude] : FALLBACK_CENTRE;
    var zoom = initialPoint ? PICKED_ZOOM : FALLBACK_ZOOM;
    mapInstance = window.L.map("location-picker-map").setView(centre, zoom);
    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(mapInstance);
    mapInstance.on("click", function (event) { setPoint(event.latlng, false); });
    if (initialPoint) {
      setPoint({ lat: initialPoint.latitude, lng: initialPoint.longitude }, false);
    }
  }

  function destroyMap() {
    if (mapInstance) {
      mapInstance.remove();
      mapInstance = null;
    }
    pinMarker = null;
    radiusCircle = null;
    pickedPoint = null;
  }

  function setSearchStatus(message) {
    var statusElement = byId("location-picker-search-status");
    statusElement.textContent = message || "";
    statusElement.hidden = !message;
  }

  function renderSearchResults(results) {
    var resultsList = byId("location-picker-search-results");
    resultsList.textContent = "";
    resultsList.hidden = results.length === 0;
    results.forEach(function (result) {
      var item = document.createElement("li");
      var button = document.createElement("button");
      button.type = "button";
      button.className = "location-picker-result-btn";
      button.textContent = result.display_name;
      button.addEventListener("click", function () {
        setPoint({ lat: parseFloat(result.lat), lng: parseFloat(result.lon) }, true);
        resultsList.hidden = true;
        setSearchStatus("");
      });
      item.appendChild(button);
      resultsList.appendChild(item);
    });
  }

  function runSearch(query) {
    var now = Date.now();
    var waitMs = Math.max(0, SEARCH_MIN_INTERVAL_MS - (now - lastSearchRequestTime));
    setSearchStatus("Searching…");
    setTimeout(function () {
      lastSearchRequestTime = Date.now();
      var url = NOMINATIM_SEARCH_URL + "?format=json&limit=6&q=" + encodeURIComponent(query);
      fetch(url, { headers: { Accept: "application/json" } })
        .then(function (response) { return response.json(); })
        .then(function (results) {
          if (results.length === 0) {
            setSearchStatus("No matches. Try a different search.");
          } else {
            setSearchStatus("");
          }
          renderSearchResults(results);
        })
        .catch(function () {
          setSearchStatus("Search failed. Check your connection and try again.");
        });
    }, waitMs);
  }

  function focusableElements() {
    var sheet = byId("location-picker-sheet") || document.querySelector(".location-picker-sheet");
    return sheet.querySelectorAll('button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex="-1"])');
  }

  function trapTab(event) {
    if (event.key !== "Tab") {
      return;
    }
    var elements = focusableElements();
    if (elements.length === 0) {
      return;
    }
    var first = elements[0];
    var last = elements[elements.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function onKeydown(event) {
    if (event.key === "Escape") {
      closeLocationPicker();
    } else {
      trapTab(event);
    }
  }

  function showError(message) {
    var errorElement = byId("location-picker-error");
    errorElement.textContent = message;
    errorElement.hidden = !message;
  }

  function openLocationPicker(onConfirm, initialPoint, radiusMetres) {
    lastConfirmCallback = onConfirm;
    scanRadiusMetres = radiusMetres || 200; // Falls back to the app-wide default classroom radius.
    elementFocusedBeforeOpen = document.activeElement;
    var backdrop = byId("location-picker-backdrop");
    backdrop.hidden = false;
    document.addEventListener("keydown", onKeydown);
    setConfirmEnabled(false);
    showError("");
    setSearchStatus("");
    byId("location-picker-search-results").hidden = true;
    byId("location-picker-search-input").value = "";
    byId("location-picker-map-status").textContent = "Loading map…";

    loadLeaflet()
      .then(function () {
        byId("location-picker-map-status").textContent = "";
        initMap(initialPoint || null);
        byId("location-picker-search-input").focus();
      })
      .catch(function (error) {
        byId("location-picker-map-status").textContent = error.message;
      });
  }

  function closeLocationPicker() {
    var backdrop = byId("location-picker-backdrop");
    backdrop.hidden = true;
    document.removeEventListener("keydown", onKeydown);
    destroyMap();
    if (elementFocusedBeforeOpen && elementFocusedBeforeOpen.focus) {
      elementFocusedBeforeOpen.focus();
    }
  }

  function confirmLocationPicker() {
    if (!pickedPoint) {
      return;
    }
    var callback = lastConfirmCallback;
    var coordinates = { latitude: pickedPoint.lat, longitude: pickedPoint.lng };
    closeLocationPicker();
    if (callback) {
      callback(coordinates);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var backdrop = byId("location-picker-backdrop");
    if (!backdrop) {
      return; // This page doesn't include the picker partial.
    }
    byId("location-picker-close-btn").addEventListener("click", closeLocationPicker);
    byId("location-picker-cancel-btn").addEventListener("click", closeLocationPicker);
    byId("location-picker-confirm-btn").addEventListener("click", confirmLocationPicker);
    backdrop.addEventListener("click", function (event) {
      if (event.target === backdrop) {
        closeLocationPicker();
      }
    });
    byId("location-picker-search-form").addEventListener("submit", function (event) {
      event.preventDefault();
      var query = byId("location-picker-search-input").value.trim();
      if (query) {
        runSearch(query);
      }
    });
  });

  window.openLocationPicker = openLocationPicker;
})();
