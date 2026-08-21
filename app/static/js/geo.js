/* Shared geolocation capture: precise fix, one retry, honest error messages. */
(function () {
  "use strict";

  window.captureLocation = function (handlers) {
    var onFix = handlers.onFix;
    var onStatus = handlers.onStatus || function () {};
    var onFail = handlers.onFail || onStatus;

    if (!("geolocation" in navigator)) {
      onFail("This device can't share its location.");
      return;
    }
    if (!window.isSecureContext) {
      onFail("Location only works on a secure (https) connection — open the app via its https address.");
      return;
    }

    function fail(error) {
      if (error.code === error.PERMISSION_DENIED) {
        onFail("Location access is blocked for this site. Allow it in your browser settings, then try again.");
      } else if (error.code === error.POSITION_UNAVAILABLE) {
        onFail("Your device couldn't work out where it is. Check that location services are switched on for your browser, then try again.");
      } else {
        onFail("Timed out getting a location fix. Try again — it helps to be near a window.");
      }
    }

    function attempt(timeoutMs, retriesLeft) {
      navigator.geolocation.getCurrentPosition(
        function (position) { onFix(position.coords); },
        function (error) {
          if (retriesLeft <= 0) {
            fail(error);
          } else if (error.code === error.TIMEOUT) {
            onStatus("Still looking for a precise fix…");
            attempt(20000, retriesLeft - 1);
          } else if (error.code === error.POSITION_UNAVAILABLE) {
            // Right after permission is granted the OS location service is often
            // still warming up; a brief pause and second try usually succeeds.
            onStatus("Location service is starting up — retrying…");
            setTimeout(function () { attempt(20000, retriesLeft - 1); }, 2500);
          } else {
            fail(error);
          }
        },
        { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 30000 }
      );
    }

    attempt(15000, 1);
  };

  // Warm up the OS location service on page open, but only when the site is
  // already allowed — checking via the Permissions API never triggers a
  // prompt. Granted: a silent fix is cached, so the button click resolves
  // instantly. Not yet decided: no prompt until the click, where the ask
  // makes sense. Blocked: nothing fires; the click explains how to re-enable.
  if (
    "geolocation" in navigator &&
    window.isSecureContext &&
    navigator.permissions &&
    navigator.permissions.query
  ) {
    navigator.permissions
      .query({ name: "geolocation" })
      .then(function (status) {
        if (status.state === "granted") {
          navigator.geolocation.getCurrentPosition(
            function () {},
            function () {},
            { enableHighAccuracy: true, timeout: 20000, maximumAge: 30000 }
          );
        }
      })
      .catch(function () {});
  }
})();
