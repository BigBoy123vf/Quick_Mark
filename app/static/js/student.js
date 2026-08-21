(function () {
  "use strict";

  window.applyTheme = function (isDark) {
    document.documentElement.classList.toggle("dark", isDark);
    document.body.classList.toggle("dark", isDark);
    try {
      localStorage.setItem("theme", isDark ? "dark" : "light");
    } catch (error) {}
    var themeColor = document.querySelector('meta[name="theme-color"]');
    if (themeColor) themeColor.setAttribute("content", isDark ? "#0d1117" : "#ffffff");
    document.querySelectorAll("[data-theme-toggle]").forEach(function (toggle) {
      toggle.setAttribute("aria-checked", isDark ? "true" : "false");
    });
  };

  // Apply persisted theme, then unhide (the flash guard hid the body for dark users).
  (function () {
    var isDark = false;
    try {
      isDark = localStorage.getItem("theme") === "dark";
    } catch (error) {}
    window.applyTheme(isDark);
    document.documentElement.classList.remove("__dark_pending");
  })();

  function closeAllDropdowns() {
    document.querySelectorAll(".settings-menu.open").forEach(function (panel) {
      panel.classList.remove("open");
      panel.setAttribute("aria-hidden", "true");
    });
    document.querySelectorAll("[data-dropdown-trigger]").forEach(function (trigger) {
      trigger.setAttribute("aria-expanded", "false");
    });
  }

  document.querySelectorAll("[data-dropdown-trigger]").forEach(function (trigger) {
    var panel = document.getElementById(trigger.getAttribute("aria-controls"));
    if (!panel) return;
    trigger.addEventListener("click", function (event) {
      event.stopPropagation();
      var willOpen = !panel.classList.contains("open");
      closeAllDropdowns();
      if (willOpen) {
        panel.classList.add("open");
        panel.setAttribute("aria-hidden", "false");
        trigger.setAttribute("aria-expanded", "true");
      }
    });
  });

  // Taps inside a panel (e.g. the theme switch) must not close it.
  document.querySelectorAll(".settings-menu").forEach(function (panel) {
    panel.addEventListener("click", function (event) {
      event.stopPropagation();
    });
  });

  document.querySelectorAll("[data-theme-toggle]").forEach(function (toggle) {
    toggle.addEventListener("click", function () {
      window.applyTheme(!document.documentElement.classList.contains("dark"));
    });
  });

  function closeModal(modal) {
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  }

  document.querySelectorAll("[data-modal-open]").forEach(function (trigger) {
    trigger.addEventListener("click", function () {
      var modal = document.getElementById(trigger.getAttribute("data-modal-open"));
      if (modal) {
        modal.classList.add("open");
        modal.setAttribute("aria-hidden", "false");
      }
    });
  });

  document.querySelectorAll("[data-modal-close]").forEach(function (button) {
    button.addEventListener("click", function () {
      closeModal(button.closest(".modal"));
    });
  });

  document.querySelectorAll(".modal").forEach(function (modal) {
    modal.addEventListener("click", function (event) {
      if (event.target === modal) closeModal(modal);
    });
  });

  document.addEventListener("click", closeAllDropdowns);
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    closeAllDropdowns();
    document.querySelectorAll(".modal.open").forEach(closeModal);
  });

  // Collapsible course sections persist their open/closed state.
  var COURSE_KEY = "histCourseState";
  function readCourseState() {
    try { return JSON.parse(localStorage.getItem(COURSE_KEY)) || {}; } catch (error) { return {}; }
  }
  function writeCourseState(state) {
    try { localStorage.setItem(COURSE_KEY, JSON.stringify(state)); } catch (error) {}
  }

  var courseState = readCourseState();
  document.querySelectorAll("[data-course]").forEach(function (toggle) {
    var key = toggle.getAttribute("data-course");
    var section = toggle.closest(".course-section");
    if (key in courseState) {
      section.classList.toggle("collapsed", !courseState[key]);
      toggle.setAttribute("aria-expanded", courseState[key] ? "true" : "false");
    }
    toggle.addEventListener("click", function () {
      var nowCollapsed = section.classList.toggle("collapsed");
      var isOpen = !nowCollapsed;
      toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
      courseState[key] = isOpen;
      writeCourseState(courseState);
    });
  });

  // Collapsible month sections persist their open/closed state.
  var MONTH_KEY = "histMonthState";
  function readMonthState() {
    try {
      return JSON.parse(localStorage.getItem(MONTH_KEY)) || {};
    } catch (error) {
      return {};
    }
  }
  function writeMonthState(state) {
    try {
      localStorage.setItem(MONTH_KEY, JSON.stringify(state));
    } catch (error) {}
  }

  var monthState = readMonthState();
  document.querySelectorAll("[data-month]").forEach(function (toggle) {
    var key = toggle.getAttribute("data-month");
    var section = toggle.closest(".month");
    if (key in monthState) {
      section.classList.toggle("collapsed", !monthState[key]);
      toggle.setAttribute("aria-expanded", monthState[key] ? "true" : "false");
    }
    toggle.addEventListener("click", function () {
      var nowCollapsed = section.classList.toggle("collapsed");
      var isOpen = !nowCollapsed;
      toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
      monthState[key] = isOpen;
      writeMonthState(monthState);
    });
  });

  // A page restored from the back/forward cache is a frozen snapshot — reload
  // so attendance marked since (e.g. a scan just done) shows without a manual refresh.
  window.addEventListener("pageshow", function (event) {
    if (event.persisted) window.location.reload();
  });
})();

(function () {
  function autoDismissFlash() {
    document.querySelectorAll('.flash').forEach(function (flash) {
      setTimeout(function () {
        flash.style.transition = 'opacity .4s';
        flash.style.opacity = '0';
        setTimeout(function () { flash.remove(); }, 420);
      }, 4000);
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoDismissFlash);
  } else {
    autoDismissFlash();
  }
})();

(function () {
  function escapeHtml(text) {
    return (text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function removeDevice(deviceId, isCurrent) {
    fetch('/devices/' + deviceId + '/delete', {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken() },
      credentials: 'same-origin'
    })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (data.success) {
          if (isCurrent) {
            window.location.reload();
          } else {
            loadDeviceList();
          }
        }
      });
  }

  function loadDeviceList() {
    var body = document.getElementById('device-list-body');
    var countLabel = document.getElementById('device-count-label');
    if (!body) return;

    body.innerHTML = '<div class="skeleton-card"></div><div class="skeleton-card"></div>';

    fetch('/devices')
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (countLabel) {
          countLabel.textContent = data.count + ' of ' + data.max + ' devices';
        }
        if (!data.devices.length) {
          body.innerHTML = '<p class="device-list__empty">No devices registered.</p>';
          return;
        }
        body.innerHTML = '';
        data.devices.forEach(function (device) {
          var card = document.createElement('div');
          card.className = 'device-card';
          card.innerHTML =
            '<div class="device-card__info">' +
              '<span class="device-card__name">' + escapeHtml(device.name) +
                (device.is_current ? ' <span class="device-badge">This device</span>' : '') +
              '</span>' +
              '<span class="device-card__meta">Added ' + escapeHtml(device.added || '—') + '</span>' +
            '</div>' +
            '<button class="btn btn--ghost btn--sm device-card__remove" ' +
              'data-id="' + device.id + '"' +
              (device.is_current ? ' data-current="1"' : '') +
            '>Remove</button>';
          body.appendChild(card);
        });
        body.querySelectorAll('.device-card__remove').forEach(function (removeButton) {
          removeButton.addEventListener('click', function () {
            removeDevice(removeButton.dataset.id, removeButton.dataset.current === '1');
          });
        });
      })
      .catch(function () {
        body.innerHTML = '<p class="device-list__empty">Failed to load devices.</p>';
      });
  }

  document.querySelectorAll('[data-modal-open="modal-devices"]').forEach(function (openButton) {
    openButton.addEventListener('click', loadDeviceList);
  });
})();
