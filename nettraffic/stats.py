#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ventana de Estadísticas fiel al original de Windows:

  - General: bloques Estado actual / Promedio / Pronóstico con filas por periodo
    (Desde el inicio, Año, Mes, Día, Hora), Enviado, Tiempo (d:hh:mm:ss) y
    Cursor (distancia recorrida por el puntero, como el original).
  - Cuota: barra de uso + % + Enviado/Recibido/Transferencia/Ajuste/Usado/
    Restante y Periodo (Inicio/Fin/Duración), con Factor.
  - Gráficos / tablas: rango de fechas + unidad de tiempo + Buscar;
    sub-pestañas Gráfico (Tráfico / Tiempo activo) y Tabla con fila de suma.
"""
import csv
import calendar
from datetime import datetime, timedelta

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from .core import (fmt_amount, parse_amount, quota_period_bounds, quota_period_progress,
                   theme_colors, hex_to_rgba, available_months, iter_month_data,
                   q_enabled)

UNITS = ("hour", "day", "month", "year")
KIND = "iB"


def _fmt_duration(sec):
    """d:hh:mm:ss — el formato 'Time' del original (0:13:43:05)."""
    sec = max(0, int(sec))
    d, r = divmod(sec, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return "%d:%02d:%02d:%02d" % (d, h, m, s)


def _fmt_km(km):
    if km >= 1.0:
        return "%.2f km" % km
    return "%.2f m" % (km * 1000.0)


def _fmt_mm_s(mm_s):
    if mm_s >= 1000.0:
        return "%.2f m/s" % (mm_s / 1000.0)
    return "%.2f mm/s" % mm_s


def summary_values(app, now=None):
    """Números del bloque General (función pura para probarla sin GUI).

    Filas por periodo natural (Desde el inicio/Año/Mes/Día/Hora) con tres
    vistas: valor actual, promedio (por segundo medido) y pronóstico
    (extrapolado al final del periodo; antes se multiplicaba por la fracción
    transcurrida y daba un valor MENOR al actual — bug corregido)."""
    now = now or datetime.now()
    per = app.sampler.get_period_totals(now)
    rx, tx = app.sampler.get_session_totals()
    dur = max(1.0, (now - app.started_at).total_seconds())

    end_hour = (now.replace(minute=59, second=59, microsecond=0)
                + timedelta(seconds=1))
    end_day = datetime(now.year, now.month, now.day) + timedelta(days=1)
    end_month = (datetime(now.year + 1, 1, 1) if now.month == 12
                 else datetime(now.year, now.month + 1, 1))
    end_year = datetime(now.year + 1, 1, 1)
    end_all = quota_period_bounds(app.cfg, now)[1] if q_enabled(app.cfg) else end_day

    rows = {}
    for key, end in (("all", end_all), ("year", end_year), ("month", end_month),
                     ("day", end_day), ("hour", end_hour)):
        v_rx, v_tx, v_s = per.get(key, (0.0, 0.0, 0.0))
        v_s = max(v_s, 0.0)
        # promedio por segundo MEDIDO del periodo (si aún no hay, por sesión)
        avg_rx = (v_rx / v_s) if v_s > 0 else (v_rx / dur)
        avg_tx = (v_tx / v_s) if v_s > 0 else (v_tx / dur)
        # pronóstico: extrapolado al final del periodo natural. Para 'Desde el
        # inicio' y 'Año' NO se extrapola (son acumulados ya completos); el
        # original solo proyecta lo que está en curso.
        if key in ("all", "year"):
            pro_rx, pro_tx = v_rx, v_tx
        else:
            span = max(1.0, (end - app.started_at).total_seconds())
            frac = max(1e-6, min(1.0, dur / span))
            pro_rx, pro_tx = v_rx / frac, v_tx / frac
        rows[key] = {
            "now_rx": v_rx, "now_tx": v_tx, "now_s": v_s,
            "avg_rx": avg_rx, "avg_tx": avg_tx,
            "pro_rx": pro_rx, "pro_tx": pro_tx,
            "pro_s": max(1.0, (end - app.started_at).total_seconds()),
        }
    cur_km, cur_mm_s = app.cursor_stats()
    cur_avg_mm_s = (cur_km * 1e6) / dur if cur_km else 0.0
    # ritmo del cursor medido contra el DÍA (estable, no contra la sesión corta)
    day_s = max(1.0, rows["day"]["now_s"])
    cursor_day_speed = (float(app.cfg["stats"].get("cursor_m", 0.0)) * 1000.0) / day_s
    # proyección del cursor al final del día con ese ritmo
    cursor_day_proj = (cursor_day_speed / 1000.0) * (rows["day"]["pro_s"] / 1000.0) \
        if rows["day"]["pro_s"] > rows["day"]["now_s"] else cur_km
    return {"rows": rows, "dur": dur, "rx": rx, "tx": tx,
            "cursor_km": cur_km, "cursor_mm_s": cur_mm_s,
            "cursor_avg_mm_s": cur_avg_mm_s,
            "cursor_day_proj": cursor_day_proj}


def quota_values(app, now=None):
    """Números del bloque de Cuota (o None si el conteo está apagado).
    Como el original: separa Transferencia (medida) de Ajuste (corrección
    manual) y muestra Restante y el tiempo que falta del periodo."""
    now = now or datetime.now()
    q = app.cfg["quota"]
    if not q_enabled(app.cfg):
        return None
    limit = parse_amount(q["limit"]["value"], q["limit"]["prefix"], q["limit"]["kind"])
    transfer = float(q.get("used_bytes", 0.0))
    adjust = float(q.get("adjustment_bytes", 0.0))
    used = transfer + adjust
    start, end = quota_period_bounds(app.cfg, now)
    elapsed = max(0.0, (now - start).total_seconds())
    length = max(1.0, (end - start).total_seconds())
    factor = (used / elapsed * length) if elapsed > 0 else 0.0
    return {"limit": limit, "transfer": transfer, "adjust": adjust, "used": used,
            "left": max(0.0, limit - used),
            "start": start, "end": end, "length": length,
            "left_s": max(0.0, length - elapsed),
            "factor": factor,
            "pct": (used / limit) if limit > 0 else 0.0,
            "period_pct": quota_period_progress(app.cfg, now),
            "period_kind": q.get("period_kind", "month")}


def aggregate_rows(app, months, y0, m0, d0, y1, m1, d1, unit):
    """Renglones (label, rx, tx, secs) del rango pedido, agregados por unidad."""
    start = datetime(y0, m0, d0)
    end = datetime(y1, m1, d1, 23, 59, 59)
    cur_ym = app.sampler.month_stats.get("month")
    cur = app.sampler.get_month_stats()
    acc = {}

    def add(key, order_key, label, rx, tx, secs):
        row = acc.get(key)
        if row is None:
            acc[key] = [label, float(rx), float(tx), float(secs), order_key]
        else:
            row[1] += float(rx)
            row[2] += float(tx)
            row[3] += float(secs)

    for ym, data in iter_month_data(months, cur_ym, cur):
        try:
            yy, mm = int(ym[:4]), int(ym[5:7])
        except Exception:
            continue
        if unit == "hour":
            for hkey, vals in data.get("hours", {}).items():
                try:
                    dstr, hstr = hkey.split()
                    dt = datetime(yy, mm, int(dstr), int(hstr))
                except Exception:
                    continue
                if start <= dt <= end:
                    add(dt, dt, dt.strftime("%Y-%m-%d %H:00"), vals[0], vals[1],
                        data.get("hour_secs", {}).get(hkey, 3600.0))
            continue
        days = data.get("days", {})
        if unit == "day":
            for dkey, vals in days.items():
                try:
                    dt = datetime(yy, mm, int(dkey))
                except Exception:
                    continue
                if start <= dt <= end:
                    add(dt, dt, dt.strftime("%Y-%m-%d"), vals[0], vals[1],
                        data.get("day_secs", {}).get(dkey, 86400.0))
        elif unit == "month":
            first = datetime(yy, mm, 1)
            last = datetime(yy, mm, calendar.monthrange(yy, mm)[1], 23, 59)
            if last < start or first > end:
                continue
            secs = sum(float(data.get("day_secs", {}).get(k, 86400.0)) for k in days)
            rx = sum(v[0] for v in days.values())
            tx = sum(v[1] for v in days.values())
            add((yy, mm), first, "%04d-%02d" % (yy, mm), rx, tx, secs)
        elif unit == "year":
            if not (start.year <= yy <= end.year):
                continue
            from_dt = start if yy == start.year else datetime(yy, 1, 1)
            to_dt = end if yy == end.year else datetime(yy, 12, 31, 23, 59)
            rx = tx = secs = 0.0
            for dkey, vals in days.items():
                try:
                    dt = datetime(yy, mm, int(dkey))
                except Exception:
                    continue
                if from_dt <= dt <= to_dt:
                    rx += vals[0]
                    tx += vals[1]
                    secs += float(data.get("day_secs", {}).get(dkey, 86400.0))
            if rx or tx:
                add(yy, datetime(yy, 1, 1), "%04d" % yy, rx, tx, secs)
    return [(r[0], r[1], r[2], r[3]) for r in sorted(acc.values(), key=lambda r: r[4])]


class StatsWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title=app.tr("statistic"))
        self.app = app
        self.cfg = app.cfg
        self.tr = app.tr
        self._last_rows = []
        self.chart_mode = "traffic"     # traffic | uptime
        self.set_default_size(720, 540)
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vb.set_border_width(8)
        self.add(vb)

        nb = Gtk.Notebook()
        vb.pack_start(nb, True, True, 0)
        self._page_general_widget = self._page_general()
        nb.append_page(self._page_general_widget, Gtk.Label(label=self.tr("stat_general")))
        nb.append_page(self._page_advanced(), Gtk.Label(label=self.tr("stat_advanced")))

        hb = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        vb.pack_start(hb, False, False, 4)
        b_data = Gtk.Button(label=self.tr("data"))
        b_data.connect("clicked", self.on_data_menu)
        hb.pack_start(b_data, False, False, 0)
        b_close = Gtk.Button(label=self.tr("ok"))
        b_close.connect("clicked", lambda *_: self.destroy())
        hb.pack_start(b_close, False, False, 0)

        # refresco periódico de la pestaña visible (números vivos)
        self._timer = None
        nb.connect("switch-page", self._on_switch_page)
        self.nb_top = nb
        self._start_refresh()

    def _on_switch_page(self, *_):
        self._start_refresh()

    def _start_refresh(self):
        if self._timer is None:
            self._timer = GLib.timeout_add(1000, self._tick_refresh)
        return True

    def _tick_refresh(self):
        if not self._page_general_widget.get_visible():
            return True        # la pestaña de gráficos no necesita refresco
        self.refresh_general()
        return True

    # ── helpers de UI ──
    def _row(self, g, r, label, value, bold=False):
        lbl = Gtk.Label(label=label, halign=Gtk.Align.START)
        val = Gtk.Label(label=value, halign=Gtk.Align.END, selectable=True)
        if bold:
            lbl.set_markup("<b>%s</b>" % Gtk.Label.escape(label))
            val.set_markup("<b>%s</b>" % Gtk.Label.escape(value))
        g.attach(lbl, 0, r, 1, 1)
        g.attach(val, 1, r, 1, 1)
        return r + 1

    def _block(self, title, rows):
        f = Gtk.Frame(label=title)
        f.set_border_width(4)
        g = Gtk.Grid(column_spacing=16, row_spacing=2, margin=6)
        f.add(g)
        r = 0
        for label, value in rows:
            r = self._row(g, r, label, value)
        return f

    # ── pestaña General (resumen) ──
    def _page_general(self):
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        # altura mínima: sin esto la ventana crece con el contenido en vez de
        # desplazarse y el bloque de Cuota queda fuera de pantalla
        sw.set_min_content_height(380)
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sw.add(vb)
        self._general_box = vb
        self.refresh_general()
        return sw

    def refresh_general(self):
        vb = self._general_box
        for child in list(vb.get_children()):
            vb.remove(child)
        s = summary_values(self.app)
        rows = s["rows"]
        k = KIND

        def pair(v_rx, v_tx, per_sec=False):
            return "%s  /  %s" % (fmt_amount(v_rx, k, per_sec),
                                  fmt_amount(v_tx, k, per_sec))

        # Estado actual: periodos + Enviado + Tiempo + Cursor
        vb.pack_start(self._block(self.tr("stat_now"), [
            (self.tr("all_time"), pair(rows["all"]["now_rx"], rows["all"]["now_tx"])),
            (self.tr("unit_year"), pair(rows["year"]["now_rx"], rows["year"]["now_tx"])),
            (self.tr("unit_month"), pair(rows["month"]["now_rx"], rows["month"]["now_tx"])),
            (self.tr("unit_day"), pair(rows["day"]["now_rx"], rows["day"]["now_tx"])),
            (self.tr("unit_hour"), pair(rows["hour"]["now_rx"], rows["hour"]["now_tx"])),
            (self.tr("stat_sent"), fmt_amount(s["tx"], k)),
            (self.tr("stat_time"), _fmt_duration(s["dur"])),
            (self.tr("stat_cursor"), _fmt_km(s["cursor_km"])),
        ]), False, False, 0)

        # Promedio: velocidades medias + Cursor en mm/s
        vb.pack_start(self._block(self.tr("stat_avg2"), [
            (self.tr("all_time"), pair(rows["all"]["avg_rx"], rows["all"]["avg_tx"], True)),
            (self.tr("unit_year"), pair(rows["year"]["avg_rx"], rows["year"]["avg_tx"], True)),
            (self.tr("unit_month"), pair(rows["month"]["avg_rx"], rows["month"]["avg_tx"], True)),
            (self.tr("unit_day"), pair(rows["day"]["avg_rx"], rows["day"]["avg_tx"], True)),
            (self.tr("unit_hour"), pair(rows["hour"]["avg_rx"], rows["hour"]["avg_tx"], True)),
            (self.tr("stat_sent"), fmt_amount(s["tx"] / max(1.0, s["dur"]), k, True)),
            (self.tr("stat_cursor"), _fmt_mm_s(s["cursor_mm_s"])),
        ]), False, False, 0)

        # Pronóstico: extrapolado al final de cada periodo + Cursor proyectado
        vb.pack_start(self._block(self.tr("stat_prognosis"), [
            (self.tr("all_time"), pair(rows["all"]["pro_rx"], rows["all"]["pro_tx"])),
            (self.tr("unit_year"), pair(rows["year"]["pro_rx"], rows["year"]["pro_tx"])),
            (self.tr("unit_month"), pair(rows["month"]["pro_rx"], rows["month"]["pro_tx"])),
            (self.tr("unit_day"), pair(rows["day"]["pro_rx"], rows["day"]["pro_tx"])),
            (self.tr("unit_hour"), pair(rows["hour"]["pro_rx"], rows["hour"]["pro_tx"])),
            (self.tr("stat_sent"), fmt_amount(
                s["tx"] * (rows["day"]["pro_rx"] / rows["day"]["now_rx"])
                if rows["day"]["now_rx"] > 0 else 0.0, k)),
            (self.tr("stat_cursor"), _fmt_km(s.get("cursor_day_proj", 0.0))),
        ]), False, False, 0)

        # Cuota: barra + % + detalle, como el original
        q = quota_values(self.app)
        if q:
            kind = self.cfg["quota"]["limit"]["kind"]
            pct = min(1.0, q["pct"])
            f = Gtk.Frame(label=self.tr("quota"))
            f.set_border_width(4)
            fbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin=6)
            f.add(fbox)
            top = Gtk.Box(spacing=10)
            bar = Gtk.LevelBar()
            bar.set_min_value(0.0)
            bar.set_max_value(1.0)
            bar.set_value(pct)
            bar.set_size_request(160, 14)
            top.pack_start(bar, False, False, 0)
            lbl_pct = Gtk.Label(halign=Gtk.Align.START)
            lbl_pct.set_markup("<b>%.1f%%</b>" % (pct * 100.0))
            top.pack_start(lbl_pct, False, False, 6)
            lbl_left = Gtk.Label(halign=Gtk.Align.START)
            lbl_left.set_text("%s: %s" % (self.tr("stat_remain"),
                                          fmt_amount(q["left"], kind)))
            top.pack_start(lbl_left, False, False, 6)
            fbox.pack_start(top, False, False, 0)
            g = Gtk.Grid(column_spacing=16, row_spacing=2)
            fbox.pack_start(g, False, False, 0)
            r = 0
            for label, value in (
                    (self.tr("stat_q_used"), fmt_amount(q["used"], kind)),
                    (self.tr("stat_transfer"), fmt_amount(q["transfer"], kind)),
                    (self.tr("stat_adjustment"), fmt_amount(q["adjust"], kind)),
                    (self.tr("stat_q_limit"), fmt_amount(q["limit"], kind)),
                    (self.tr("stat_time"), _fmt_duration(q["left_s"])),
                    (self.tr("stat_q_begin"), q["start"].strftime("%d/%m/%Y %H:%M")),
                    (self.tr("stat_q_end"), q["end"].strftime("%d/%m/%Y %H:%M")),
                    (self.tr("stat_length"), _fmt_duration(q["length"])),
                    (self.tr("stat_q_factor"), fmt_amount(q["factor"], kind))):
                r = self._row(g, r, label, value)
            vb.pack_start(f, False, False, 0)
            al = Gtk.Alignment(xalign=0.5)
            b = Gtk.Button(label=self.tr("stat_q_adjust"))
            b.connect("clicked", self.on_adjust_quota)
            al.add(b)
            vb.pack_start(al, False, False, 6)
        vb.show_all()

    # ── pestaña Gráficos / tablas ──
    def _page_advanced(self):
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        now = datetime.now()

        bar = Gtk.Box(spacing=6)
        bar.pack_start(Gtk.Label(label=self.tr("stat_from")), False, False, 0)
        self.spin_f = self._date_spinbox(now - timedelta(days=30), now)
        bar.pack_start(self.spin_f, False, False, 0)
        bar.pack_start(Gtk.Label(label=self.tr("stat_to")), False, False, 0)
        self.spin_t = self._date_spinbox(now, now)
        bar.pack_start(self.spin_t, False, False, 0)
        bar.pack_start(Gtk.Label(label=self.tr("stat_time_unit")), False, False, 0)
        cb_unit = Gtk.ComboBoxText()
        for k in ("unit_hour", "unit_day", "unit_month", "unit_year"):
            cb_unit.append_text(self.tr(k))
        cb_unit.set_active(1)  # Día
        self.unit = "day"
        cb_unit.connect("changed", lambda w: (setattr(self, "unit", UNITS[w.get_active()]),
                                               self.on_find()))
        bar.pack_start(cb_unit, False, False, 0)
        b_find = Gtk.Button(label=self.tr("stat_find"))
        b_find.connect("clicked", self.on_find)
        bar.pack_start(b_find, False, False, 0)
        vb.pack_start(bar, False, False, 0)

        self.nb2 = Gtk.Notebook()
        vb.pack_start(self.nb2, True, True, 0)
        self.nb2.append_page(self._page_chart(), Gtk.Label(label=self.tr("stat_plot")))
        self.nb2.append_page(self._page_table(), Gtk.Label(label=self.tr("stat_table")))

        self._last_rows = []
        self.on_find()
        return vb

    def _date_spinbox(self, dt, hi):
        hb = Gtk.Box(spacing=2)
        spins = []
        for val, lo_i, hi_i in ((dt.year, 2007, hi.year), (dt.month, 1, 12), (dt.day, 1, 31)):
            sp = Gtk.SpinButton.new_with_range(lo_i, hi_i, 1)
            sp.set_value(val)
            sp.set_digits(0)
            if lo_i == hi_i:
                sp.set_sensitive(False)
            spins.append(sp)
            hb.pack_start(sp, False, False, 0)
        hb._spins = spins
        return hb

    def _get_date(self, widget):
        y, m, d = (int(s.get_value()) for s in widget._spins)
        m = max(1, min(12, m))
        # un mes corto no admite día 31: se ajusta al último día real
        d = max(1, min(d, calendar.monthrange(y, m)[1]))
        return y, m, d

    def _page_chart(self):
        sw = Gtk.ScrolledWindow()
        sw.set_min_content_height(260)
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        # tipo de gráfica: Tráfico / Tiempo activo (como el original)
        hb = Gtk.Box(spacing=10)
        rb_t = Gtk.RadioButton.new_with_label_from_widget(None, self.tr("chart_traffic"))
        rb_u = Gtk.RadioButton.new_with_label_from_widget(rb_t, self.tr("chart_uptime"))
        rb_t.connect("toggled", lambda w: w.get_active() and self._set_mode("traffic"))
        rb_u.connect("toggled", lambda w: w.get_active() and self._set_mode("uptime"))
        rb_t.set_active(True)
        hb.pack_start(rb_t, False, False, 0)
        hb.pack_start(rb_u, False, False, 0)
        vb.pack_start(hb, False, False, 2)
        self.chart_draw = Gtk.DrawingArea()
        self.chart_draw.connect("draw", self.on_draw_chart)
        self.chart_draw.set_size_request(-1, 220)
        vb.pack_start(self.chart_draw, True, True, 0)
        sw.add(vb)
        return sw

    def _set_mode(self, mode):
        if self.chart_mode != mode:
            self.chart_mode = mode
            self.chart_draw.queue_draw()

    def _page_table(self):
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sw = Gtk.ScrolledWindow()
        sw.set_min_content_height(220)
        self.table_store = Gtk.ListStore(str, str, str, str, str)
        tv = Gtk.TreeView(model=self.table_store)
        cols = ((self.tr("date"), 0.0), (self.tr("total"), 1.0),
                (self.tr("stat_received"), 1.0), (self.tr("stat_sent"), 1.0),
                (self.tr("stat_time"), 1.0))
        for i, (title, align) in enumerate(cols):
            r = Gtk.CellRendererText()
            if i > 0:
                r.set_property("xalign", 1.0)
            col = Gtk.TreeViewColumn(title, r, text=i)
            col.set_alignment(align)
            col.set_expand(i == 0)
            tv.append_column(col)
        sw.add(tv)
        vb.pack_start(sw, True, True, 0)
        # fila de suma, como el original
        self.sum_label = Gtk.Label(halign=Gtk.Align.END, margin_end=8)
        vb.pack_start(self.sum_label, False, False, 2)
        return vb

    def on_find(self, *_):
        try:
            y0, m0, d0 = self._get_date(self.spin_f)
            y1, m1, d1 = self._get_date(self.spin_t)
        except Exception:
            return
        if (y0, m0, d0) > (y1, m1, d1):
            y0, m0, d0, y1, m1, d1 = y1, m1, d1, y0, m0, d0
        rows = aggregate_rows(self.app, available_months(), y0, m0, d0, y1, m1, d1, self.unit)
        self._last_rows = rows
        self.table_store.clear()
        s_rx = s_tx = s_s = 0.0
        for label, rx, tx, secs in rows:
            self.table_store.append([label, fmt_amount(rx + tx, KIND),
                                     fmt_amount(rx, KIND), fmt_amount(tx, KIND),
                                     _fmt_duration(secs)])
            s_rx += rx; s_tx += tx; s_s += secs
        self.sum_label.set_markup(
            "<b>%s: %s    %s: %s    %s: %s    %s: %s</b>" % (
                self.tr("sum_total"), fmt_amount(s_rx + s_tx, KIND),
                self.tr("stat_received"), fmt_amount(s_rx, KIND),
                self.tr("stat_sent"), fmt_amount(s_tx, KIND),
                self.tr("stat_time"), _fmt_duration(s_s)))
        self.chart_draw.queue_draw()

    def on_draw_chart(self, da, cr):
        rows = self._last_rows
        w = max(1, da.get_allocated_width())
        h = max(1, da.get_allocated_height())
        theme = theme_colors(self.cfg)
        cr.set_source_rgba(*hex_to_rgba(theme["back"]))
        cr.rectangle(0, 0, w, h)
        cr.fill()
        if not rows:
            cr.set_source_rgba(*hex_to_rgba(theme["font"], 0.7))
            cr.select_font_face("Sans", 0, 1)
            cr.set_font_size(12)
            txt = self.tr("stat_no_data")
            cr.move_to(max(6, (w - cr.text_extents(txt).width) / 2), h / 2)
            cr.show_text(txt)
            return False

        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(8)
        uptime = self.chart_mode == "uptime"
        if uptime:
            vals = [r[3] for r in rows]           # segundos medidos
            maxv = max(vals) or 1.0
            yfmt = lambda v: _fmt_duration(v)
        else:
            vals = [r[1] + r[2] for r in rows]
            maxv = max(vals) or 1.0
            yfmt = lambda v: fmt_amount(v, KIND)
        pad_l = 6 + max(cr.text_extents(yfmt(maxv * i / 4.0)).width for i in range(5))
        pad_b, pad_t, pad_r = 26, 8, 6
        plot_w = max(10, w - pad_l - pad_r)
        plot_h = max(10, h - pad_t - pad_b)

        # rejilla + etiquetas del eje Y
        for i in range(5):
            frac = i / 4.0
            y = pad_t + plot_h - plot_h * frac
            cr.set_source_rgba(*hex_to_rgba(theme["axis"], 0.35))
            cr.set_line_width(0.5)
            cr.move_to(pad_l, y)
            cr.line_to(pad_l + plot_w, y)
            cr.stroke()
            cr.set_source_rgba(*hex_to_rgba(theme["font"], 0.75))
            lbl = yfmt(maxv * frac)
            cr.move_to(max(1, pad_l - 4 - cr.text_extents(lbl).width), y + 3)
            cr.show_text(lbl)

        n = len(rows)
        step = plot_w / float(n)
        bw = max(2.0, min(step * 0.8, 42.0))

        # etiquetas del eje X (primeras/últimas + intermedias repartidas)
        idxs = set(range(n)) if n <= 8 else {0, n - 1}
        if n > 8:
            for i in range(1, 8):
                idxs.add(int((n - 1) * i / 8.0))
        for i in sorted(idxs):
            lbl = rows[i][0]
            if self.unit == "hour":
                lbl = lbl[11:16] if len(lbl) > 11 else lbl
            elif self.unit == "day":
                lbl = lbl[5:]                     # MM-DD
            elif self.unit == "month":
                lbl = lbl[2:] if False else lbl   # YYYY-MM tal cual
            cr.set_source_rgba(*hex_to_rgba(theme["font"], 0.75))
            tw = cr.text_extents(lbl).width
            x = pad_l + step * i + (step - bw) / 2.0
            cr.move_to(max(pad_l, min(w - tw - 2, x - tw / 2.0)), h - 8)
            cr.show_text(lbl)

        for i, (_label, rx, tx, secs) in enumerate(rows):
            x0 = pad_l + step * i + (step - bw) / 2.0
            if uptime:
                hh = (secs / maxv) * plot_h
                cr.set_source_rgba(*hex_to_rgba(theme["total"], 0.95))
                cr.rectangle(x0, pad_t + plot_h - hh, bw, hh)
                cr.fill()
            else:
                # barra apilada: descarga abajo (verde) + subida arriba (roja)
                hr = (rx / maxv) * plot_h
                hu = (tx / maxv) * plot_h
                cr.set_source_rgba(*hex_to_rgba(theme["download"], 0.95))
                cr.rectangle(x0, pad_t + plot_h - hr, bw, hr)
                cr.fill()
                cr.set_source_rgba(*hex_to_rgba(theme["upload"], 0.95))
                cr.rectangle(x0, pad_t + plot_h - hr - hu, bw, hu)
                cr.fill()

        # línea base
        cr.set_source_rgba(*hex_to_rgba(theme["axis"], 0.8))
        cr.set_line_width(0.8)
        cr.move_to(pad_l, pad_t + plot_h)
        cr.line_to(pad_l + plot_w, pad_t + plot_h)
        cr.stroke()
        return False

    # ── Datos: Exportar / Borrar / Ajustar ──
    def on_data_menu(self, btn):
        m = Gtk.Menu()
        it_exp = Gtk.MenuItem(label=self.tr("stat_data_export"))
        it_exp.connect("activate", self.on_export)
        m.append(it_exp)
        it_del = Gtk.MenuItem(label=self.tr("stat_data_delete"))
        it_del.connect("activate", self.on_clear)
        m.append(it_del)
        if q_enabled(self.cfg):
            m.append(Gtk.SeparatorMenuItem())
            it_adj = Gtk.MenuItem(label=self.tr("stat_q_adjust"))
            it_adj.connect("activate", self.on_adjust_quota)
            m.append(it_adj)
        m.show_all()
        m.popup_at_widget(btn, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None)

    def on_export(self, *_):
        dlg = Gtk.FileChooserNative.new(self.tr("stat_data_export"), self,
                                        Gtk.FileChooserAction.SAVE, None, None)
        dlg.set_current_name("nettraffic-%s.csv" % datetime.now().strftime("%Y%m%d"))
        dlg.set_do_overwrite_confirmation(True)
        if dlg.run() != Gtk.ResponseType.ACCEPT:
            dlg.destroy()
            return
        path = dlg.get_filename()
        dlg.destroy()
        months = available_months()
        cur_ym = self.app.sampler.month_stats.get("month")
        cur = self.app.sampler.get_month_stats()
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["date", "received_bytes", "sent_bytes", "total_bytes",
                            "received", "sent", "total", "seconds"])
                for ym, data in iter_month_data(months, cur_ym, cur):
                    for dkey in sorted(data.get("days", {})):
                        rx, tx = data["days"][dkey]
                        secs = data.get("day_secs", {}).get(dkey, "")
                        w.writerow(["%s-%s" % (ym, dkey), int(rx), int(tx), int(rx + tx),
                                    fmt_amount(rx, KIND), fmt_amount(tx, KIND),
                                    fmt_amount(rx + tx, KIND),
                                    round(float(secs), 1) if secs != "" else ""])
            self._info("%s\n%s" % (self.tr("stat_data_export"), path))
        except Exception as e:
            self._info(str(e))

    def _info(self, text):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True,
                                message_type=Gtk.MessageType.INFO,
                                buttons=Gtk.ButtonsType.OK, text=text)
        dlg.run()
        dlg.destroy()

    def on_clear(self, *_):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True,
                                message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.YES_NO,
                                text=self.tr("stat_ask_clear"))
        resp = dlg.run()
        dlg.destroy()
        if resp == Gtk.ResponseType.YES:
            self.app.sampler.clear_stats()
            self._last_rows = []
            self.table_store.clear()
            self.chart_draw.queue_draw()
            self.refresh_general()

    # ── Ajustar contador de cuota ──
    def on_adjust_quota(self, *_):
        """Ajusta el CONTADOR: el valor que se fija es el Usado total; la
        diferencia contra la transferencia medida queda como 'Ajuste' (como
        el original: 'Current value of counter can be adjusted')."""
        q = self.cfg["quota"]
        dialog = Gtk.Dialog(title=self.tr("stat_q_adjust"), transient_for=self, modal=True)
        dialog.add_button(self.tr("cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(self.tr("ok"), Gtk.ResponseType.OK)
        area = dialog.get_content_area()
        area.set_spacing(6)
        area.set_border_width(10)
        area.add(Gtk.Label(label=self.tr("q_note"), wrap=True, halign=Gtk.Align.START))
        adj = Gtk.Adjustment(value=0.0, lower=0, upper=100000, step_increment=1)
        sp = Gtk.SpinButton(adjustment=adj, digits=2)
        sp.set_value(float(q["limit"]["value"]))
        cb_p = Gtk.ComboBoxText()
        for pre in ("", "k", "M", "G", "T"):
            cb_p.append_text(pre if pre else "—")
        cb_p.set_active(["", "k", "M", "G", "T"].index(q["limit"]["prefix"]))
        cb_k = Gtk.ComboBoxText()
        for kk in ("b", "ib", "B", "iB"):
            cb_k.append_text(kk)
        cb_k.set_active(["b", "ib", "B", "iB"].index(q["limit"]["kind"]))
        hb = Gtk.Box(spacing=4)
        hb.pack_start(Gtk.Label(label=self.tr("stat_q_used")), False, False, 0)
        hb.pack_start(sp, False, False, 0)
        hb.pack_start(cb_p, False, False, 0)
        hb.pack_start(cb_k, False, False, 0)
        area.add(hb)
        area.add(Gtk.Label(halign=Gtk.Align.START, label="%s: %s  (+%s %s)" % (
            self.tr("stat_now"), fmt_amount(float(q.get("used_bytes", 0)), KIND),
            fmt_amount(float(q.get("adjustment_bytes", 0)), KIND),
            self.tr("stat_adjustment"))))
        area.show_all()
        resp = dialog.run()
        if resp == Gtk.ResponseType.OK:
            value = parse_amount(sp.get_value(), ["", "k", "M", "G", "T"][cb_p.get_active()],
                                 cb_k.get_active_text())
            self.app.sampler.adjust_quota_counter(value)
            self.app.apply_all()
            self.refresh_general()
        dialog.destroy()