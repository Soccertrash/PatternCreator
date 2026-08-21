/* Muster-Editor: Formularaufbau, Undo/Redo, Vorschau-Anbindung, Commit.
 * Vanilla JS - keine externen Bibliotheken, kein Build-Schritt.
 *
 * Einheiten: das PatternDoc rechnet in cm (Fusion-API), der Editor zeigt mm.
 * Umgerechnet wird ausschließlich in toUi()/fromUi().
 */
(function () {
  'use strict';

  var MAX_HISTORY = 100;
  var PREVIEW_DEBOUNCE = 150;
  var HISTORY_DEBOUNCE = 400;
  var STORAGE_KEY = 'patternCreator.lastUsed';

  var schema = null;
  var doc = null;
  var mode = 'create';
  var limits = { entity: 2000, preview: 5000 };

  var history = [];
  var historyIndex = -1;
  var suppressHistory = false;

  var requestSeq = 0;
  var appliedRequest = -1;
  var previewTimer = null;
  var historyTimer = null;
  var busy = false;
  var gotInit = false;
  var lastUsed = loadLastUsed();

  var preview = null;
  var el = {};

  /* Das Dropdown zeigt schon "Eigener Rahmen", das Doc aber noch nicht: ohne
     Kontur waere ``shape: custom`` ein Feldfehler. Erst nach erfolgreichem
     Einlesen wird die Form wirklich umgestellt. */
  var customPending = false;

  /* ------------------------------------------------------- Fusion-Brücke */

  function fusionReady() {
    return !!(window.adsk && typeof window.adsk.fusionSendData === 'function');
  }

  function sendToFusion(action, data) {
    try {
      if (fusionReady()) {
        window.adsk.fusionSendData(action, JSON.stringify(data || {}));
        return true;
      }
    } catch (e) {
      showGlobalError('Verbindung zu Fusion unterbrochen: ' + e);
    }
    return false;
  }

  /* Fusion injiziert ``window.adsk`` erst nach dem Laden der Seite - beim ersten
     Oeffnen der Palette oft nach ``DOMContentLoaded``. Ein einmalig gesendetes
     ``ready`` ginge dann verloren und der Editor blieb ohne Schema leer. Deshalb
     so lange wiederholen, bis ``init`` angekommen ist. */
  var READY_RETRY_MS = 150;
  var READY_TIMEOUT_MS = 15000;
  var readyWaited = 0;

  function sendReady() {
    if (gotInit) { return; }
    sendToFusion('ready', {});
    if (readyWaited >= READY_TIMEOUT_MS) {
      showGlobalError('Keine Verbindung zu Fusion - bitte den Editor schliessen '
                      + 'und erneut oeffnen.');
      return;
    }
    readyWaited += READY_RETRY_MS;
    window.setTimeout(sendReady, READY_RETRY_MS);
  }

  window.fusionJavaScriptHandler = {
    handle: function (action, data) {
      try {
        var payload = data ? JSON.parse(data) : {};
        if (action === 'init') { onInit(payload); }
        else if (action === 'preview') { onPreview(payload); }
        else if (action === 'busy') { setBusy(true, payload.message); }
        else if (action === 'done') { onDone(payload); }
        else if (action === 'frame') { onFrame(payload); }
        return 'OK';
      } catch (e) {
        showGlobalError('Fehler in der Editor-Oberfläche: ' + e);
        return 'FAILED';
      }
    }
  };

  /* --------------------------------------------------------- Hilfsfunktionen */

  function clone(v) { return JSON.parse(JSON.stringify(v)); }

  function round(v, digits) {
    var f = Math.pow(10, digits === undefined ? 4 : digits);
    return Math.round(v * f) / f;
  }

  function toUi(param, value) {
    return param.type === 'length' ? round(value * 10, 4) : value;
  }

  function fromUi(param, value) {
    return param.type === 'length' ? value / 10 : value;
  }

  function unitOf(param) {
    if (param.type === 'length') { return 'mm'; }
    if (param.type === 'angle') { return '°'; }
    if (param.type === 'percent') { return '%'; }
    return '';
  }

  function loadLastUsed() {
    try { return JSON.parse(window.localStorage.getItem(STORAGE_KEY)) || {}; }
    catch (e) { return {}; }
  }

  function saveLastUsed() {
    try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(lastUsed)); }
    catch (e) { /* localStorage kann in der Palette gesperrt sein */ }
  }

  function patternSchema(id) {
    var list = (schema && schema.patterns) || [];
    for (var i = 0; i < list.length; i++) { if (list[i].id === id) { return list[i]; } }
    return null;
  }

  function sectionData(section) {
    switch (section) {
      case 'container': return doc.container;
      case 'placement': return doc.placement;
      case 'style': return doc.style;
      case 'pattern': return doc.pattern.params;
      case 'text': return doc.textLayers[0];
      default: return {};
    }
  }

  function sectionParams(section) {
    if (section === 'pattern') {
      var ps = patternSchema(doc.pattern.type);
      return ps ? ps.params : [];
    }
    return schema[section] || [];
  }

  /* ------------------------------------------------------- Eigener Rahmen */

  function customPoints() {
    var pts = doc && doc.container ? doc.container.customPoints : null;
    return (pts && pts.length >= 3) ? pts : null;
  }

  function customSource() {
    return (doc && doc.container && doc.container.customSource) || {};
  }

  function shownShape() {
    return customPending ? 'custom' : (doc.container.shape || 'rect');
  }

  function fmtMm(cm) {
    return (cm * 10).toFixed(1).replace('.', ',');
  }

  function updateCustomFrameBox() {
    if (!el.customFrameBox) { return; }
    var show = shownShape() === 'custom';
    el.customFrameBox.hidden = !show;
    if (!show) { return; }
    var pts = customPoints();
    var info = el.customFrameInfo;
    if (!pts) {
      info.className = 'missing';
      info.textContent = 'Im Fusion-Canvas ein geschlossenes Skizzenprofil oder '
        + 'eine ebene Fläche auswählen, dann „Aus Fusion-Auswahl übernehmen“.';
    } else {
      var xs = pts.map(function (p) { return p[0]; });
      var ys = pts.map(function (p) { return p[1]; });
      var w = Math.max.apply(null, xs) - Math.min.apply(null, xs);
      var h = Math.max.apply(null, ys) - Math.min.apply(null, ys);
      var label = customSource().label || 'eingelesene Kontur';
      info.className = '';
      info.textContent = 'Quelle: ' + label + ' · ' + pts.length + ' Punkte · '
        + fmtMm(w) + ' × ' + fmtMm(h) + ' mm';
    }
    el.rereadFrameBtn.disabled = !customSource().token;
  }

  /* ---------------------------------------------------------- Mantelfläche */

  function development() {
    return (doc && doc.development) || null;
  }

  function updateSurfaceBox() {
    if (!el.surfaceBox) { return; }
    var dev = development();
    el.surfaceBox.hidden = !dev;
    if (!dev) { return; }
    var source = dev.source || {};
    el.surfaceInfo.className = '';
    el.surfaceInfo.textContent = source.label
      || 'Mantelfläche (Radius ' + fmtMm(dev.radius) + ' mm)';
    var angle = Math.round(Number(dev.seamAngle) || 0);
    el.seamAngle.value = angle;
    el.seamAngleNum.value = angle;
  }

  function setSeamAngle(value) {
    var dev = development();
    if (!dev) { return; }
    var angle = Math.max(-180, Math.min(180, Number(value) || 0));
    dev.seamAngle = angle;
    el.seamAngle.value = angle;
    el.seamAngleNum.value = angle;
    /* Der Nahtwinkel ändert die Abwicklung nicht - nur, wo sie auf dem Bauteil
       landet. Die Vorschau bleibt also gleich; gespeichert werden muss er
       trotzdem. */
    changed();
  }

  function dropSurface() {
    if (!development()) { return; }
    doc.development = null;
    renderAll();
    pushHistory();
    setStatus('Mantelfläche verworfen - der Rahmen ist wieder eben.');
    requestPreview(true);
  }

  function requestFrame(action) {
    setStatus(action === 'pickFrame'
      ? 'Auswahl wird gelesen …' : 'Rahmen wird neu eingelesen …');
    sendToFusion(action, {});
  }

  function onFrame(payload) {
    if (!payload.ok) {
      setStatus(payload.message || 'Rahmen konnte nicht eingelesen werden.', true);
      return;
    }
    customPending = false;
    doc.container = payload.doc.container;
    doc.placement = payload.doc.placement;
    doc.development = payload.doc.development || null;
    if (payload.target) { el.targetLabel.textContent = payload.target; }
    renderAll();
    pushHistory();
    setStatus(payload.message || '');
    requestPreview(true);
  }

  function errorPath(section, key) {
    if (section === 'pattern') { return 'pattern.params.' + key; }
    if (section === 'text') { return 'textLayers.0.' + key; }
    return section + '.' + key;
  }

  /* --------------------------------------------------------- Initialisierung */

  function onInit(payload) {
    gotInit = true;
    clearGlobalError();
    schema = payload.schema;
    doc = payload.doc;
    mode = payload.mode || 'create';
    limits.entity = payload.entityWarnLimit || 2000;
    limits.preview = payload.previewWarnLimit || 5000;
    el.targetLabel.textContent = payload.target || '';
    el.commitBtn.textContent = mode === 'edit' ? 'Skizze aktualisieren' : 'In Skizze erzeugen';
    buildPatternPopup();
    renderAll();
    history = [];
    historyIndex = -1;
    pushHistory();
    requestPreview(true);
  }

  /* -------------------------------------------------------- Musterauswahl */

  function iconSvg(pathData) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="' + (pathData || 'M4 4h16v16H4z') + '"/></svg>';
  }

  function buildPatternPopup() {
    var popup = el.patternPopup;
    popup.innerHTML = '';
    var groups = {};
    var order = [];
    (schema.patterns || []).forEach(function (p) {
      if (!groups[p.group]) { groups[p.group] = []; order.push(p.group); }
      groups[p.group].push(p);
    });
    order.forEach(function (name) {
      var head = document.createElement('div');
      head.className = 'pattern-group';
      head.textContent = name;
      popup.appendChild(head);
      groups[name].forEach(function (p) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'pattern-item';
        b.setAttribute('role', 'option');
        b.dataset.id = p.id;
        b.innerHTML = '<span class="pict">' + iconSvg(p.icon) + '</span><span>' +
          escapeHtml(p.label) + '</span>';
        b.addEventListener('click', function () {
          setPatternType(p.id);
          togglePopup(false);
        });
        popup.appendChild(b);
      });
    });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  function togglePopup(show) {
    var popup = el.patternPopup;
    var open = show === undefined ? popup.hidden : show;
    popup.hidden = !open;
    el.patternButton.setAttribute('aria-expanded', String(open));
    if (open) {
      var r = el.patternButton.getBoundingClientRect();
      popup.style.top = (r.bottom + 4) + 'px';
      Array.prototype.forEach.call(popup.querySelectorAll('.pattern-item'), function (b) {
        b.setAttribute('aria-selected', String(b.dataset.id === doc.pattern.type));
      });
    }
  }

  function setPatternType(id) {
    if (id === doc.pattern.type) { return; }
    var ps = patternSchema(id);
    if (!ps) { return; }
    // Zuletzt benutzte Werte pro Mustertyp vorschlagen (Wiedererkennung statt Erinnern)
    var params = {};
    ps.params.forEach(function (p) { params[p.key] = p.default; });
    if (lastUsed[id]) {
      Object.keys(lastUsed[id]).forEach(function (k) {
        if (params.hasOwnProperty(k)) { params[k] = lastUsed[id][k]; }
      });
    }
    doc.pattern = { type: id, params: params };
    ensureFillTarget();
    renderAll();
    changed(true);
  }

  function ensureFillTarget() {
    var ps = patternSchema(doc.pattern.type);
    if (!ps) { return; }
    if (ps.fillTargets.indexOf(doc.style.fillTarget) < 0) {
      doc.style.fillTarget = ps.fillTargets[0];
    }
  }

  function updatePatternHeader() {
    var ps = patternSchema(doc.pattern.type);
    el.patternName.textContent = ps ? ps.label : doc.pattern.type;
    el.patternIcon.innerHTML = iconSvg(ps && ps.icon);
  }

  /* ------------------------------------------------------ Formular-Aufbau */

  function renderAll() {
    updatePatternHeader();
    buildSection(el.patternFields, 'pattern');
    buildSection(el.containerFields, 'container');
    buildSection(el.placementFields, 'placement');
    buildSection(el.styleFields, 'style');
    buildSection(el.textFields, 'text');
    buildPresets();
    updateCustomFrameBox();
    updateSurfaceBox();
    el.seedInput.value = doc.seed;
    updateHelp();
    updateHistoryButtons();
  }

  function buildPresets() {
    var ps = patternSchema(doc.pattern.type);
    var row = el.presetRow;
    row.innerHTML = '<span>Vorgaben:</span>';
    var presets = (ps && ps.presets) || {};
    var names = Object.keys(presets);
    row.style.display = names.length ? '' : 'none';
    names.forEach(function (name) {
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = name.charAt(0).toUpperCase() + name.slice(1);
      b.addEventListener('click', function () {
        Object.keys(presets[name]).forEach(function (k) {
          doc.pattern.params[k] = presets[name][k];
        });
        renderAll();
        changed(true);
      });
      row.appendChild(b);
    });
  }

  function buildSection(host, section) {
    host.innerHTML = '';
    var params = sectionParams(section);
    var data = sectionData(section);
    params.forEach(function (param) {
      if (section === 'style' && param.key === 'fillTarget') {
        var ps = patternSchema(doc.pattern.type);
        if (ps && ps.fillTargets.length < 2) { return; }
      }
      host.appendChild(buildField(section, param, data));
    });
    applyVisibility(host, section);
  }

  function buildField(section, param, data) {
    var wrap = document.createElement('div');
    wrap.className = 'field';
    wrap.dataset.key = param.key;
    wrap.dataset.section = section;
    if (param.visibleIf) { wrap.dataset.visibleIf = JSON.stringify(param.visibleIf); }

    var value = data[param.key];
    var control = document.createElement('div');
    control.className = 'control';

    if (param.type === 'bool') {
      wrap.className += ' check';
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = !!value;
      cb.id = section + '_' + param.key;
      var lab = document.createElement('label');
      lab.htmlFor = cb.id;
      lab.textContent = param.label;
      cb.addEventListener('change', function () {
        data[param.key] = cb.checked;
        applyVisibilityAll();
        changed();
      });
      control.appendChild(cb);
      control.appendChild(lab);
      wrap.appendChild(control);
    } else {
      var label = document.createElement('label');
      label.textContent = param.label;
      var u = unitOf(param);
      if (u) { label.innerHTML = escapeHtml(param.label) + ' <span class="unit">(' + u + ')</span>'; }
      wrap.appendChild(label);

      if (param.type === 'choice') {
        var isShape = section === 'container' && param.key === 'shape';
        var shown = isShape ? shownShape() : value;
        var sel = document.createElement('select');
        (param.choices || []).forEach(function (c) {
          var o = document.createElement('option');
          o.value = c.value; o.textContent = c.label;
          if (c.value === shown) { o.selected = true; }
          sel.appendChild(o);
        });
        sel.addEventListener('change', function () {
          if (isShape) {
            /* "Eigener Rahmen" ohne Kontur bleibt reine Oberflaeche: das Doc
               behaelt seine bisherige Form, sonst kaeme ein Feldfehler zurueck
               und die Vorschau bliebe stehen. */
            customPending = sel.value === 'custom' && !customPoints();
            if (customPending) {
              updateCustomFrameBox();
              applyVisibilityAll();
              return;
            }
          }
          data[param.key] = sel.value;
          if (section === 'container' || section === 'style' || section === 'pattern') {
            applyVisibilityAll();
          }
          changed(true);
        });
        control.appendChild(sel);
      } else if (param.type === 'string') {
        var multi = param.key === 'text';
        var input = document.createElement(multi ? 'textarea' : 'input');
        if (!multi) { input.type = 'text'; }
        input.value = value === undefined || value === null ? '' : value;
        input.addEventListener('input', function () {
          data[param.key] = input.value;
          changed();
        });
        control.appendChild(input);
      } else {
        var uiValue = toUi(param, Number(value));
        var hasRange = param.min !== undefined && param.max !== undefined;
        var num = document.createElement('input');
        num.type = 'number';
        num.value = uiValue;
        if (param.min !== undefined) { num.min = toUi(param, param.min); }
        if (param.max !== undefined) { num.max = toUi(param, param.max); }
        if (param.step !== undefined) { num.step = toUi(param, param.step); }

        var range = null;
        if (hasRange) {
          range = document.createElement('input');
          range.type = 'range';
          range.min = toUi(param, param.min);
          range.max = toUi(param, param.max);
          range.step = param.step !== undefined ? toUi(param, param.step) : 'any';
          range.value = uiValue;
          range.addEventListener('input', function () {
            num.value = range.value;
            data[param.key] = fromUi(param, Number(range.value));
            changed();
          });
          control.appendChild(range);
        }
        num.addEventListener('input', function () {
          var v = Number(num.value);
          if (isNaN(v)) { return; }
          if (range) { range.value = v; }
          data[param.key] = fromUi(param, v);
          changed();
        });
        control.appendChild(num);
      }
      wrap.appendChild(control);
    }

    if (param.help) {
      var hint = document.createElement('div');
      hint.className = 'hint';
      hint.textContent = param.help;
      wrap.appendChild(hint);
    }
    var err = document.createElement('div');
    err.className = 'err';
    err.hidden = true;
    wrap.appendChild(err);
    return wrap;
  }

  /* Was ``visibleIf`` nicht ausdrücken kann: es sieht immer nur den eigenen
     Abschnitt, die Mantelfläche steht aber daneben im Dokument. */
  function hiddenByDevelopment(section, key) {
    var dev = development();
    if (section === 'container') { return !!dev; }
    if (section === 'placement') {
      /* Ursprung und Drehung des Rahmens setzt Fusion beim Erzeugen selbst -
         die Abwicklung muss auf der Tangentialebene liegen, nicht irgendwo.
         Die Musterdrehung entfällt zusätzlich, weil ein gedrehtes Gitter sich
         nach einem Umlauf nicht mehr fortsetzt. */
      if (key === 'patternAngle') { return !!(dev && dev.periodic); }
      return !!dev;
    }
    if (section === 'style') {
      if (key === 'embossOn' || key === 'embossDepth') { return !dev; }
      /* Ohne Beschnitt reicht das Muster über den Umlauf hinaus und läge nach
         dem Wickeln auf sich selbst - die Wahl gibt es dort nicht. */
      if (key === 'clip') { return !!(dev && dev.periodic); }
    }
    return false;
  }

  function applyVisibility(host, section) {
    var data = sectionData(section);
    Array.prototype.forEach.call(host.querySelectorAll('.field'), function (f) {
      if (hiddenByDevelopment(section, f.dataset.key)) { f.hidden = true; return; }
      if (!f.dataset.visibleIf) { f.hidden = false; return; }
      var cond = JSON.parse(f.dataset.visibleIf);
      var show = Object.keys(cond).every(function (k) {
        /* Solange nur das Dropdown auf "Eigener Rahmen" steht, sollen die
           Massfelder trotzdem schon verschwinden. */
        var v = (section === 'container' && k === 'shape') ? shownShape() : data[k];
        return cond[k].indexOf(v) >= 0;
      });
      f.hidden = !show;
    });
  }

  function applyVisibilityAll() {
    updateCustomFrameBox();
    updateSurfaceBox();
    applyVisibility(el.patternFields, 'pattern');
    applyVisibility(el.containerFields, 'container');
    applyVisibility(el.placementFields, 'placement');
    applyVisibility(el.styleFields, 'style');
    applyVisibility(el.textFields, 'text');
  }

  /* ------------------------------------------------------------- Hilfe */

  function updateHelp() {
    var ps = patternSchema(doc.pattern.type);
    if (!ps) { el.helpBox.hidden = true; return; }
    var html = '<strong>' + escapeHtml(ps.label) + '</strong><br>' +
      escapeHtml(ps.description) + '<ul>';
    ps.params.forEach(function (p) {
      html += '<li><strong>' + escapeHtml(p.label) + '</strong>' +
        (p.help ? ' – ' + escapeHtml(p.help) : '') + '</li>';
    });
    html += '</ul>';
    el.helpBox.innerHTML = html;
  }

  /* ---------------------------------------------------- Änderungen/Historie */

  function changed(immediate) {
    scheduleHistory();
    if (immediate) {
      requestPreview();
    } else {
      clearTimeout(previewTimer);
      previewTimer = setTimeout(requestPreview, PREVIEW_DEBOUNCE);
    }
    rememberParams();
  }

  function rememberParams() {
    lastUsed[doc.pattern.type] = clone(doc.pattern.params);
    saveLastUsed();
  }

  function scheduleHistory() {
    if (suppressHistory) { return; }
    clearTimeout(historyTimer);
    historyTimer = setTimeout(pushHistory, HISTORY_DEBOUNCE);
  }

  function pushHistory() {
    var snap = JSON.stringify(doc);
    if (historyIndex >= 0 && history[historyIndex] === snap) { return; }
    history = history.slice(0, historyIndex + 1);
    history.push(snap);
    if (history.length > MAX_HISTORY) { history.shift(); }
    historyIndex = history.length - 1;
    updateHistoryButtons();
  }

  function updateHistoryButtons() {
    el.undoBtn.disabled = historyIndex <= 0;
    el.redoBtn.disabled = historyIndex >= history.length - 1;
  }

  function applyHistory(index) {
    if (index < 0 || index >= history.length) { return; }
    historyIndex = index;
    doc = JSON.parse(history[index]);
    suppressHistory = true;
    renderAll();
    suppressHistory = false;
    requestPreview(true);
    updateHistoryButtons();
  }

  /* ----------------------------------------------------------- Vorschau */

  function requestPreview(fit) {
    clearTimeout(previewTimer);
    requestSeq += 1;
    if (fit) { preview._fitNext = true; }
    sendToFusion('docChanged', { requestId: requestSeq, doc: doc });
  }

  function onPreview(payload) {
    if (payload.requestId < appliedRequest) { return; }   // veraltete Antwort
    appliedRequest = payload.requestId;
    showErrors(payload.errors || {});
    if (!payload.scene) {
      setStatus('Ungültige Werte – Vorschau angehalten.', true);
      return;
    }
    var stats = payload.scene.stats || {};
    var estimate = payload.entityEstimate || 0;
    var many = stats.contours > limits.preview;
    preview.setScene(payload.scene, many);
    if (preview._fitNext) { preview._fitNext = false; preview.fit(); }
    el.stats.textContent = stats.contours + ' Konturen · ' + stats.areas +
      ' Flächen · ca. ' + estimate + ' Skizzen-Elemente';
    var warnings = (payload.scene.warnings || []).slice();
    if (estimate > limits.entity) {
      warnings.push('Etwa ' + estimate + ' Skizzen-Elemente – das Erzeugen kann dauern.');
    }
    if (warnings.length) {
      el.banner.hidden = false;
      el.banner.textContent = warnings.join(' ');
    } else {
      el.banner.hidden = true;
    }
    setStatus('');
  }

  function showErrors(errors) {
    var keys = Object.keys(errors);
    Array.prototype.forEach.call(document.querySelectorAll('.field'), function (f) {
      var path = errorPath(f.dataset.section, f.dataset.key);
      var msg = errors[path];
      var errEl = f.querySelector('.err');
      /* Nicht jedes Feld kommt aus dem Schema: der Nahtwinkel steht von Hand im
         HTML und hat weder Fehlerzeile noch Feldpfad. Ohne diese Abfrage stirbt
         die ganze Oberflaeche an ihm ("Cannot set properties of null"). */
      if (!errEl) { return; }
      if (msg) {
        f.classList.add('invalid');
        errEl.hidden = false;
        errEl.textContent = msg;
      } else {
        f.classList.remove('invalid');
        errEl.hidden = true;
        errEl.textContent = '';
      }
    });
    if (errors._global) {
      showGlobalError(errors._global);
    } else {
      el.globalError.hidden = true;
    }
    el.commitBtn.disabled = keys.length > 0 || busy;
  }

  function showGlobalError(message) {
    el.globalError.hidden = false;
    el.globalError.textContent = message;
  }

  function clearGlobalError() {
    el.globalError.hidden = true;
    el.globalError.textContent = '';
  }

  function setStatus(message, isError) {
    el.status.textContent = message || '';
    el.status.className = isError ? 'error' : '';
  }

  function setBusy(state, message) {
    busy = state;
    document.body.classList.toggle('busy', state);
    el.commitBtn.disabled = state;
    if (message) { setStatus(message); }
  }

  function onDone(payload) {
    setBusy(false);
    setStatus(payload.message || '', !payload.ok);
    if (payload.ok) {
      mode = 'edit';
      el.commitBtn.textContent = 'Skizze aktualisieren';
    }
  }

  /* ------------------------------------------------------------ Aktionen */

  function resetSection(section) {
    var params = sectionParams(section);
    var data = sectionData(section);
    params.forEach(function (p) { data[p.key] = p.default; });
    if (section === 'container') { forgetCustomFrame(); }
    if (section === 'style') { ensureFillTarget(); }
    renderAll();
    changed(true);
  }

  function forgetCustomFrame() {
    /* Zuruecksetzen heisst zuruecksetzen: die eingelesene Kontur bleibt nicht
       im Doc liegen. */
    customPending = false;
    delete doc.container.customPoints;
    delete doc.container.customSource;
  }

  function resetAll() {
    ['pattern', 'container', 'placement', 'style', 'text'].forEach(function (s) {
      var params = sectionParams(s);
      var data = sectionData(s);
      params.forEach(function (p) { data[p.key] = p.default; });
    });
    forgetCustomFrame();
    doc.seed = schema.seed.default;
    ensureFillTarget();
    renderAll();
    changed(true);
  }

  function rollSeed() {
    doc.seed = Math.floor(Math.random() * 1000000);
    el.seedInput.value = doc.seed;
    changed(true);
  }

  /* ------------------------------------------------------------ Start */

  function bind() {
    el.patternButton = document.getElementById('patternButton');
    el.patternPopup = document.getElementById('patternPopup');
    el.patternName = document.getElementById('patternName');
    el.patternIcon = document.getElementById('patternIcon');
    el.helpBtn = document.getElementById('helpBtn');
    el.helpBox = document.getElementById('helpBox');
    el.seedInput = document.getElementById('seedInput');
    el.diceBtn = document.getElementById('diceBtn');
    el.targetLabel = document.getElementById('targetLabel');
    el.patternFields = document.getElementById('patternFields');
    el.containerFields = document.getElementById('containerFields');
    el.placementFields = document.getElementById('placementFields');
    el.styleFields = document.getElementById('styleFields');
    el.textFields = document.getElementById('textFields');
    el.presetRow = document.getElementById('presetRow');
    el.stats = document.getElementById('stats');
    el.banner = document.getElementById('banner');
    el.status = document.getElementById('status');
    el.globalError = document.getElementById('globalError');
    el.undoBtn = document.getElementById('undoBtn');
    el.redoBtn = document.getElementById('redoBtn');
    el.commitBtn = document.getElementById('commitBtn');
    el.cancelBtn = document.getElementById('cancelBtn');
    el.resetBtn = document.getElementById('resetBtn');
    el.fitBtn = document.getElementById('fitBtn');
    el.customFrameBox = document.getElementById('customFrameBox');
    el.customFrameInfo = document.getElementById('customFrameInfo');
    el.pickFrameBtn = document.getElementById('pickFrameBtn');
    el.rereadFrameBtn = document.getElementById('rereadFrameBtn');
    el.surfaceBox = document.getElementById('surfaceBox');
    el.surfaceInfo = document.getElementById('surfaceInfo');
    el.seamAngle = document.getElementById('seamAngle');
    el.seamAngleNum = document.getElementById('seamAngleNum');
    el.pickSurfaceBtn = document.getElementById('pickSurfaceBtn');
    el.dropSurfaceBtn = document.getElementById('dropSurfaceBtn');

    preview = new Preview(document.getElementById('preview'));
    preview.onTextMove = function (dx, dy) {
      var layer = doc.textLayers[0];
      if (!layer || !layer.enabled) { return; }
      layer.x = round(layer.x + dx, 5);
      layer.y = round(layer.y + dy, 5);
      buildSection(el.textFields, 'text');
      changed();
    };

    el.patternButton.addEventListener('click', function (e) {
      e.stopPropagation();
      togglePopup();
    });
    document.addEventListener('click', function (e) {
      if (!el.patternPopup.hidden && !el.patternPopup.contains(e.target)) {
        togglePopup(false);
      }
    });
    el.helpBtn.addEventListener('click', function () {
      el.helpBox.hidden = !el.helpBox.hidden;
    });
    el.seedInput.addEventListener('input', function () {
      var v = parseInt(el.seedInput.value, 10);
      if (!isNaN(v)) { doc.seed = v; changed(); }
    });
    el.diceBtn.addEventListener('click', rollSeed);
    el.pickFrameBtn.addEventListener('click', function () { requestFrame('pickFrame'); });
    el.pickSurfaceBtn.addEventListener('click', function () { requestFrame('pickFrame'); });
    el.dropSurfaceBtn.addEventListener('click', dropSurface);
    el.seamAngle.addEventListener('input', function () { setSeamAngle(el.seamAngle.value); });
    el.seamAngleNum.addEventListener('input', function () { setSeamAngle(el.seamAngleNum.value); });
    el.rereadFrameBtn.addEventListener('click', function () { requestFrame('rereadFrame'); });
    el.fitBtn.addEventListener('click', function () { preview.fit(); });
    el.undoBtn.addEventListener('click', function () { applyHistory(historyIndex - 1); });
    el.redoBtn.addEventListener('click', function () { applyHistory(historyIndex + 1); });
    el.resetBtn.addEventListener('click', resetAll);
    el.cancelBtn.addEventListener('click', function () { sendToFusion('cancel', {}); });
    el.commitBtn.addEventListener('click', function () {
      setBusy(true, 'Erzeuge …');
      sendToFusion('commit', { requestId: ++requestSeq, doc: doc });
    });

    Array.prototype.forEach.call(document.querySelectorAll('[data-reset]'), function (b) {
      b.addEventListener('click', function (e) {
        e.preventDefault();
        var s = b.dataset.reset;
        if (s === 'container') { resetSection('container'); resetSection('placement'); }
        else { resetSection(s); }
      });
    });

    document.addEventListener('keydown', function (e) {
      var meta = e.ctrlKey || e.metaKey;
      if (!meta) { return; }
      var k = e.key.toLowerCase();
      if (k === 'z') {
        e.preventDefault();
        if (e.shiftKey) { applyHistory(historyIndex + 1); }
        else { applyHistory(historyIndex - 1); }
      } else if (k === 'y') {
        e.preventDefault();
        applyHistory(historyIndex + 1);
      } else if (k === 'r') {
        e.preventDefault();
        rollSeed();
      } else if (k === 'enter') {
        e.preventDefault();
        el.commitBtn.click();
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    bind();
    sendReady();
  });
}());
