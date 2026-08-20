/* Canvas-Renderer für die IR (JSON vom Python-Backend).
 * Zeichnet exakt dieselben Elemente, die später in die Skizze gehen -
 * Vorschau und Ergebnis können deshalb nicht auseinanderlaufen.
 * Reines Vanilla JS, keine externen Bibliotheken.
 */
(function (global) {
  'use strict';

  var CHAR_W = 0.62;      // wie in text/text_layer.py

  function Preview(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.scene = null;
    this.scale = 40;
    this.offset = { x: 0, y: 0 };
    this.simplify = false;
    this.onTextMove = null;       // function(x, y) in cm
    this._drag = null;
    this._bind();
  }

  Preview.prototype.colors = function () {
    var s = getComputedStyle(document.documentElement);
    return {
      accent: s.getPropertyValue('--accent').trim() || '#0b6bcb',
      line: s.getPropertyValue('--line').trim() || '#d8dce2',
      text: s.getPropertyValue('--text').trim() || '#1f2328',
      muted: s.getPropertyValue('--muted').trim() || '#6b7280'
    };
  };

  /* ------------------------------------------------------------ Transform */

  Preview.prototype.toScreen = function (x, y) {
    return { x: this.offset.x + x * this.scale, y: this.offset.y - y * this.scale };
  };

  Preview.prototype.toModel = function (px, py) {
    return { x: (px - this.offset.x) / this.scale, y: (this.offset.y - py) / this.scale };
  };

  Preview.prototype.resize = function () {
    var dpr = global.devicePixelRatio || 1;
    var w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (!w || !h) { return; }
    // Beim Ändern der Canvas-Größe (Andocken, Aufklappen der Gruppen) bleibt der
    // Punkt in der Mitte stehen, statt dass die Vorschau verrutscht.
    if (this._lastW !== undefined && (this._lastW !== w || this._lastH !== h)) {
      this.offset.x += (w - this._lastW) / 2;
      this.offset.y += (h - this._lastH) / 2;
    }
    this._lastW = w;
    this._lastH = h;
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };

  Preview.prototype.setScene = function (scene, simplify) {
    var first = !this.scene;
    this.scene = scene;
    this.simplify = !!simplify;
    if (first) { this.fit(); } else { this.draw(); }
  };

  Preview.prototype.fit = function () {
    this.resize();
    var b = (this.scene && this.scene.bounds) || [-5, -3, 5, 3];
    var w = Math.max(1e-6, b[2] - b[0]), h = Math.max(1e-6, b[3] - b[1]);
    var cw = this.canvas.clientWidth || 400, ch = this.canvas.clientHeight || 260;
    this.scale = Math.min(cw / w, ch / h) * 0.88;
    var cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2;
    this.offset.x = cw / 2 - cx * this.scale;
    this.offset.y = ch / 2 + cy * this.scale;
    this.draw();
  };

  /* -------------------------------------------------------------- Zeichnen */

  Preview.prototype.draw = function () {
    this.resize();
    var ctx = this.ctx, c = this.colors();
    var cw = this.canvas.clientWidth, ch = this.canvas.clientHeight;
    ctx.clearRect(0, 0, cw, ch);
    if (!this.scene) { return; }

    var els = this.scene.elements || [];
    var fill = !this.simplify;
    var self = this;

    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    // Zusammenhaengende Flaeche (Stegnetz): Aussenkontur und Loecher gehoeren zu
    // EINEM Pfad, sonst wuerden die Loecher die Flaeche wieder zumalen.
    if (fill) {
      var face = els.filter(function (e) { return e.role === 'face' || e.role === 'hole'; });
      if (face.length) {
        ctx.save();
        ctx.beginPath();
        face.forEach(function (e) { self._sub(e); });
        ctx.fillStyle = self._fillStyle(c);
        ctx.fill('evenodd');
        ctx.restore();
      }
    }

    els.forEach(function (el) {
      var isBorder = el.layer === 'border';
      var inFace = el.role === 'face' || el.role === 'hole';
      ctx.save();
      ctx.strokeStyle = isBorder ? c.muted : c.accent;
      ctx.lineWidth = isBorder ? 1.2 : 1;
      if (isBorder && !inFace) { ctx.setLineDash([5, 4]); }
      if (inFace) { ctx.strokeStyle = c.accent; }
      ctx.fillStyle = self._fillStyle(c);

      switch (el.t) {
        case 'path': self._path(el, fill && !isBorder && !inFace); break;
        case 'circle': self._circle(el, fill && !isBorder && !inFace); break;
        case 'arc': self._arc(el); break;
        case 'ellipse': self._ellipse(el); break;
        case 'text': self._text(el, c); break;
      }
      ctx.restore();
    });
  };

  Preview.prototype._fillStyle = function (c) {
    var m = /^#([0-9a-f]{6})$/i.exec(c.accent);
    if (!m) { return 'rgba(11,107,203,.18)'; }
    var n = parseInt(m[1], 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',.18)';
  };

  Preview.prototype._trace = function (pts, closed, spline) {
    var ctx = this.ctx, i;
    if (!pts.length) { return; }
    var p = this.toScreen(pts[0][0], pts[0][1]);
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
    if (spline && pts.length > 2) {
      var n = pts.length;
      var last = closed ? n : n - 1;
      for (i = 0; i < last; i++) {
        var p0 = pts[closed ? (i - 1 + n) % n : Math.max(0, i - 1)];
        var p1 = pts[i % n];
        var p2 = pts[(i + 1) % n];
        var p3 = pts[closed ? (i + 2) % n : Math.min(n - 1, i + 2)];
        var c1 = this.toScreen(p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6);
        var c2 = this.toScreen(p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6);
        var e = this.toScreen(p2[0], p2[1]);
        ctx.bezierCurveTo(c1.x, c1.y, c2.x, c2.y, e.x, e.y);
      }
    } else {
      for (i = 1; i < pts.length; i++) {
        var q = this.toScreen(pts[i][0], pts[i][1]);
        ctx.lineTo(q.x, q.y);
      }
    }
    if (closed) { ctx.closePath(); }
  };

  /** Element als Teilpfad an den laufenden Pfad haengen (ohne beginPath). */
  Preview.prototype._sub = function (el) {
    var ctx = this.ctx, p, i;
    if (el.t === 'path') {
      if (!el.pts.length) { return; }
      p = this.toScreen(el.pts[0][0], el.pts[0][1]);
      ctx.moveTo(p.x, p.y);
      for (i = 1; i < el.pts.length; i++) {
        var q = this.toScreen(el.pts[i][0], el.pts[i][1]);
        ctx.lineTo(q.x, q.y);
      }
      ctx.closePath();
    } else if (el.t === 'circle') {
      p = this.toScreen(el.c[0], el.c[1]);
      ctx.moveTo(p.x + Math.abs(el.r * this.scale), p.y);
      ctx.arc(p.x, p.y, Math.abs(el.r * this.scale), 0, Math.PI * 2);
      ctx.closePath();
    } else if (el.t === 'ellipse') {
      p = this.toScreen(el.c[0], el.c[1]);
      if (ctx.ellipse) {
        ctx.moveTo(p.x + el.rx * this.scale, p.y);
        ctx.ellipse(p.x, p.y, el.rx * this.scale, el.ry * this.scale, -el.rot, 0, Math.PI * 2);
      } else {
        ctx.moveTo(p.x + el.rx * this.scale, p.y);
        ctx.arc(p.x, p.y, el.rx * this.scale, 0, Math.PI * 2);
      }
      ctx.closePath();
    }
  };

  Preview.prototype._path = function (el, fill) {
    this._trace(el.pts, el.closed, el.curve === 'spline');
    if (fill && el.closed) { this.ctx.fill('evenodd'); }
    this.ctx.stroke();
  };

  Preview.prototype._circle = function (el, fill) {
    var p = this.toScreen(el.c[0], el.c[1]);
    this.ctx.beginPath();
    this.ctx.arc(p.x, p.y, Math.abs(el.r * this.scale), 0, Math.PI * 2);
    if (fill) { this.ctx.fill(); }
    this.ctx.stroke();
  };

  Preview.prototype._arc = function (el) {
    var p = this.toScreen(el.c[0], el.c[1]);
    this.ctx.beginPath();
    this.ctx.arc(p.x, p.y, Math.abs(el.r * this.scale), -el.a1, -el.a0);
    this.ctx.stroke();
  };

  Preview.prototype._ellipse = function (el) {
    var p = this.toScreen(el.c[0], el.c[1]);
    var ctx = this.ctx;
    ctx.beginPath();
    if (ctx.ellipse) {
      ctx.ellipse(p.x, p.y, el.rx * this.scale, el.ry * this.scale, -el.rot, 0, Math.PI * 2);
    } else {
      ctx.arc(p.x, p.y, el.rx * this.scale, 0, Math.PI * 2);
    }
    ctx.stroke();
  };

  Preview.prototype._text = function (el, c) {
    var ctx = this.ctx;
    var p = this.toScreen(el.x, el.y);
    var px = el.h * this.scale;
    if (px < 3) { return; }
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(-el.angle);
    ctx.fillStyle = c.text;
    ctx.font = Math.round(px) + 'px ' + (el.font || 'Arial') + ', sans-serif';
    ctx.textBaseline = 'alphabetic';
    ctx.fillText(el.text, 0, 0);
    ctx.restore();
  };

  /* ------------------------------------------------------- Maus-Interaktion */

  Preview.prototype.textHit = function (px, py) {
    if (!this.scene) { return false; }
    var els = this.scene.elements || [];
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (el.t !== 'text') { continue; }
      var m = this.toModel(px, py);
      var dx = m.x - el.x, dy = m.y - el.y;      // Abstand im Modellraum
      var ca = Math.cos(el.angle), sa = Math.sin(el.angle);
      var lx = dx * ca + dy * sa;                // in die Textrichtung drehen
      var ly = -dx * sa + dy * ca;
      var w = el.text.length * el.h * CHAR_W;
      var tol = 6 / this.scale;
      if (lx >= -tol && lx <= w + tol && ly >= -tol && ly <= el.h + tol) { return true; }
    }
    return false;
  };

  Preview.prototype._bind = function () {
    var self = this, cv = this.canvas;

    cv.addEventListener('wheel', function (ev) {
      ev.preventDefault();
      var r = cv.getBoundingClientRect();
      var mx = ev.clientX - r.left, my = ev.clientY - r.top;
      var before = self.toModel(mx, my);
      var f = Math.pow(1.0015, -ev.deltaY);
      self.scale = Math.max(0.5, Math.min(4000, self.scale * f));
      var after = self.toModel(mx, my);
      self.offset.x += (after.x - before.x) * self.scale;
      self.offset.y -= (after.y - before.y) * self.scale;
      self.draw();
    }, { passive: false });

    cv.addEventListener('mousedown', function (ev) {
      var r = cv.getBoundingClientRect();
      var mx = ev.clientX - r.left, my = ev.clientY - r.top;
      var onText = self.onTextMove && self.textHit(mx, my);
      self._drag = { x: mx, y: my, text: onText };
      cv.classList.add('dragging');
    });

    global.addEventListener('mousemove', function (ev) {
      if (!self._drag) { return; }
      var r = cv.getBoundingClientRect();
      var mx = ev.clientX - r.left, my = ev.clientY - r.top;
      var dx = mx - self._drag.x, dy = my - self._drag.y;
      self._drag.x = mx; self._drag.y = my;
      if (self._drag.text) {
        self.onTextMove(dx / self.scale, -dy / self.scale);
      } else {
        self.offset.x += dx;
        self.offset.y += dy;
        self.draw();
      }
    });

    global.addEventListener('mouseup', function () {
      self._drag = null;
      cv.classList.remove('dragging');
    });

    global.addEventListener('resize', function () { self.draw(); });
  };

  global.Preview = Preview;
}(window));
