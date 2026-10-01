#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ventana de Ajustes: navegación lateral General / Gráfica / Cuota, como el
panel del original. Cada página va en un ScrolledWindow con scroll propio
(min-content-height) para que la rueda del mouse funcione siempre; antes los
paneles se recortaban porque los scrolled window no tenían contenido declarado.

Todos los controles aplican en vivo (sin necesidad de pulsar Aplicar) y el
estado se guarda al Aceptar/Aplicar. Cancelar restaura lo que había al abrir."""
import copy

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

from .core import (read_interfaces, is_loopback, save_settings, fmt_amount,
                   parse_amount, hex_to_rgba)

PAGES = (("general", "general"), ("chart", "chart"), ("quota", "quota"))
COLOR_KEYS = ("download", "upload", "total", "activity", "back", "font", "axis")


def _scroll(vb):
    """ScrolledWindow con política explícita y altura mínima (scroll con rueda)."""
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.set_min_content_height(340)
    sw.set_overlay_scrolling(True)
    sw.add(vb)
    return sw


class SettingsWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title=app.tr("settings"))
        self.app = app
        self.cfg = app.cfg
        self.tr = app.tr
        self.set_default_size(620, 560)
        self.set_transient_for(app.win if app.win else None)
        self._snapshot = copy.deepcopy(app.cfg)

        root = Gtk.Box(spacing=10)
        root.set_border_width(8)
        self.add(root)

        # navegación lateral
        nav = Gtk.ListBox()
        nav.set_size_request(130, -1)
        nav.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for i, (key, label) in enumerate(PAGES):
            nav.add(Gtk.ListBoxRow(name=key, child=Gtk.Label(label=self.tr(label),
                                                             xalign=0, margin=4)))
        root.pack_start(nav, False, False, 0)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        root.pack_start(right, True, True, 0)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        right.pack_start(self.stack, True, True, 0)

        self.stack.add_named(self._page_general(), "general")
        self.stack.add_named(self._page_chart(), "chart")
        self.stack.add_named(self._page_quota(), "quota")

        hb = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        right.pack_start(hb, False, False, 0)
        b_reset = Gtk.Button(label=self.tr("reset"))
        b_reset.connect("clicked", self.on_reset)
        hb.pack_start(b_reset, False, False, 0)
        b_cancel = Gtk.Button(label=self.tr("cancel"))
        b_cancel.connect("clicked", self.on_cancel)
        hb.pack_start(b_cancel, False, False, 0)
        b_apply = Gtk.Button(label=self.tr("apply"))
        b_apply.connect("clicked", self.on_apply)
        hb.pack_start(b_apply, False, False, 0)
        b_ok = Gtk.Button(label=self.tr("ok"))
        b_ok.connect("clicked", self.on_ok)
        hb.pack_start(b_ok, False, False, 0)

        def on_row(_lb, row):
            if row is not None:
                self.stack.set_visible_child_name(row.get_name())

        nav.connect("row-selected", on_row)
        nav.select_row(nav.get_row_at_index(0))

    # ── helpers ──
    def _live(self, widget, signal, setter):
        """Conecta un control para aplicar en vivo (los widgets añadidos después
        del show_all no heredan las señales globales: hay que conectarlas aquí)."""
        def handler(w, *_):
            setter(w)
            self.app.apply_live()
        widget.connect(signal, handler)
        return widget

    def _setter(self, section, key_path, from_widget=lambda w: w.get_active()):
        def s(w):
            obj = self.cfg[section]
            for k in key_path[:-1]:
                obj = obj[k]
            obj[key_path[-1]] = from_widget(w)
        return s

    def _frame(self, title, parent_box):
        f = Gtk.Frame(label=title)
        f.set_border_width(2)
        g = Gtk.Grid(column_spacing=8, row_spacing=4, margin=6)
        f.add(g)
        parent_box.pack_start(f, False, False, 2)
        return g

    def _row(self, g, r, label, widget):
        g.attach(Gtk.Label(label=label, halign=Gtk.Align.START), 0, r, 1, 1)
        g.attach(widget, 1, r, 1, 1)
        return r + 1

    def _check_row(self, g, r, section, key, label):
        cb = Gtk.CheckButton()
        cb.set_active(bool(self.cfg[section][key]))
        self._live(cb, "toggled", self._setter(section, (key,)))
        g.attach(cb, 0, r, 1, 1)
        g.attach(Gtk.Label(label=label, halign=Gtk.Align.START), 1, r, 1, 1)
        return r + 1

    def _spin_row(self, g, r, label, value, lo, hi, step, setter, digits=0):
        adj = Gtk.Adjustment(value=float(value), lower=lo, upper=hi, step_increment=step)
        sp = Gtk.SpinButton(adjustment=adj, digits=digits)
        sp.set_value(float(value))
        if digits:
            sp.connect("value-changed", lambda w: (setter(w.get_value()),
                                                   self.app.apply_live()))
        else:
            self._live(sp, "value-changed", lambda w: setter(int(w.get_value())))
        return self._row(g, r, label, sp)

    def _combo_row(self, g, r, label, options, current, setter):
        cb = Gtk.ComboBoxText()
        for o in options:
            cb.append_text(o[1])
        idx = next((i for i, o in enumerate(options) if o[0] == current), 0)
        cb.set_active(idx)
        self._live(cb, "changed", lambda w: setter(options[max(0, w.get_active())][0]))
        return self._row(g, r, label, cb)

    def _label(self, vb, text, dim=True):
        lbl = Gtk.Label(label=text, wrap=True, halign=Gtk.Align.START)
        lbl.set_margin_start(6)
        if dim:
            ctx = lbl.get_style_context()
            ctx.add_class("dim-label")
        vb.pack_start(lbl, False, False, 0)

    # ── página: General ──
    def _page_general(self):
        g = self.cfg["general"]
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        gr = self._frame(self.tr("general"), vb)
        r = self._combo_row(gr, 0, self.tr("language"),
                            (("es", "Español"), ("en", "English")), g["language"],
                            self._setter("general", ("language",)))
        r = self._spin_row(gr, r, self.tr("frequency"), g["frequency_ms"], 100, 60000, 100,
                           self._setter("general", ("frequency_ms",)))
        r = self._check_row(gr, r, "general", "start_with_system", self.tr("start_system"))

        gr = self._frame(self.tr("window_state"), vb)
        for i, (val, label) in enumerate(((1, self.tr("ws_normal")),
                                          (0, self.tr("ws_minimized")))):
            rb = Gtk.RadioButton.new_with_label_from_widget(
                None if i == 0 else rb, label)
            if int(g["window_restore"]) == val:
                rb.set_active(True)
            rb.connect("toggled", lambda w, v=val: (
                self.cfg["general"].__setitem__("window_restore", v)
                if w.get_active() else None))
            gr.attach(rb, 0, i, 2, 1)

        gr = self._frame(self.tr("behavior"), vb)
        r = 0
        for key, label in (("on_top", "on_top"), ("click_through", "click_through"),
                           ("hide_under_pointer", "hide_under_pointer"),
                           ("hide_when_fullscreen", "hide_fullscreen"),
                           ("close_to_tray", "close_tray")):
            r = self._check_row(gr, r, "general", key, self.tr(label))

        # Fuente de datos
        gr = self._frame(self.tr("data_source"), vb)
        r = 0
        rb_all = Gtk.RadioButton.new_with_label_from_widget(None, self.tr("if_all"))
        rb_sel = Gtk.RadioButton.new_with_label_from_widget(rb_all, self.tr("if_selected"))
        (rb_all if g["interfaces_mode"] == "all" else rb_sel).set_active(True)

        def mode_toggled(w):
            if w.get_active():
                self.cfg["general"]["interfaces_mode"] = "all" if rb_all.get_active() else "selected"
                self.app.apply_live()

        rb_all.connect("toggled", mode_toggled)
        rb_sel.connect("toggled", mode_toggled)
        gr.attach(rb_all, 0, r, 2, 1); r += 1
        gr.attach(rb_sel, 0, r, 2, 1); r += 1
        r = self._check_row(gr, r, "general", "exclude_loopback", self.tr("exclude_lo"))
        r = self._spin_row(gr, r, self.tr("rescan"), g.get("rescan_seconds", 10), 1, 600, 1,
                           self._setter("general", ("rescan_seconds",)))

        self._if_store = Gtk.ListStore(bool, str)
        selected = set(g["selected_interfaces"])
        for name in sorted(read_interfaces()):
            self._if_store.append([name in selected, name])
        tv = Gtk.TreeView(model=self._if_store)
        rt = Gtk.CellRendererToggle()
        rt.set_property("activatable", True)
        rt.connect("toggled", self._if_toggled)
        tv.append_column(Gtk.TreeViewColumn("", rt, active=0))
        tv.append_column(Gtk.TreeViewColumn(self.tr("interfaces"), Gtk.CellRendererText(), text=1))
        tv.set_headers_visible(False)
        sw_if = Gtk.ScrolledWindow()
        sw_if.set_min_content_height(96)
        sw_if.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw_if.add(tv)
        gr.attach(sw_if, 0, r, 2, 1)

        self._label(vb, "Base de datos del sistema: /proc/net/dev. "
                        "«Excluir bucle invertido» evita contar lo (tráfico interno).")
        self._label(vb, "Icono de bandeja: el clon dibuja el icono por software "
                        "(activo RX/TX, inactivo y barras de cuota), así que no "
                        "necesita colecciones de PNG como el original.")
        self._label(vb, "Comprobar actualizaciones: no aplica (versión para Linux, "
                        "sin servidor de actualizaciones propio).")
        return _scroll(vb)

    def _if_toggled(self, widget, path):
        self._if_store[path][0] = not self._if_store[path][0]
        self.cfg["general"]["selected_interfaces"] = [row[1] for row in self._if_store if row[0]]
        self.app.apply_live()

    # ── página: Gráfica ──
    def _page_chart(self):
        p = self.cfg["plot"]
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        gr = self._frame(self.tr("type"), vb)
        r = self._combo_row(gr, 0, self.tr("type"),
                            (("area", self.tr("area")), ("column", self.tr("column")),
                             ("line", self.tr("line"))), p["chart_type"],
                            self._setter("plot", ("chart_type",)))
        r = self._combo_row(gr, r, self.tr("shape"),
                            (("rectangle", self.tr("rectangle")), ("pie", self.tr("pie"))),
                            p["chart_shape"], self._setter("plot", ("chart_shape",)))

        gr = self._frame(self.tr("points"), vb)
        r = self._spin_row(gr, 0, self.tr("points"), p["points_count"], 10, 600, 1,
                           self._setter("plot", ("points_count",)))
        r = self._spin_row(gr, r, self.tr("point_width"), p["point_width"], 1, 20, 1,
                           self._setter("plot", ("point_width",)))
        r = self._spin_row(gr, r, self.tr("buffer"), p["points_buffer"], 60, 3600, 10,
                           self._setter("plot", ("points_buffer",)))

        # Escala Y
        gr = self._frame(self.tr("scale"), vb)
        rb_auto = Gtk.RadioButton.new_with_label_from_widget(None, self.tr("auto"))
        rb_man = Gtk.RadioButton.new_with_label_from_widget(rb_auto, self.tr("manual"))
        (rb_auto if p["scale_y"] == "auto" else rb_man).set_active(True)

        def scale_mode(w):
            if w.get_active():
                p["scale_y"] = "auto" if rb_auto.get_active() else "manual"
                sp_max.set_sensitive(p["scale_y"] == "manual")
                self.app.apply_live()

        rb_auto.connect("toggled", scale_mode)
        rb_man.connect("toggled", scale_mode)
        gr.attach(rb_auto, 0, 0, 2, 1)
        gr.attach(rb_man, 0, 1, 2, 1)
        hb = Gtk.Box(spacing=4)
        adj = Gtk.Adjustment(value=float(p["scale_max"]["value"]), lower=1, upper=1024, step_increment=1)
        sp_max = Gtk.SpinButton(adjustment=adj, digits=1)
        sp_max.set_value(float(p["scale_max"]["value"]))
        sp_max.set_sensitive(p["scale_y"] == "manual")
        sp_max.connect("value-changed", lambda w: (p["scale_max"].__setitem__("value", w.get_value()),
                                                   self.app.apply_live()))
        cb_pre = Gtk.ComboBoxText()
        for pre in ("", "k", "M", "G", "T"):
            cb_pre.append_text(pre if pre else "—")
        cb_pre.set_active(["", "k", "M", "G", "T"].index(p["scale_max"]["prefix"]))
        cb_pre.connect("changed", lambda w: (p["scale_max"].__setitem__(
            "prefix", ["", "k", "M", "G", "T"][max(0, w.get_active())]), self.app.apply_live()))
        gr.attach(Gtk.Label(label=self.tr("scale_max"), halign=Gtk.Align.START), 0, 2, 1, 1)
        hb.pack_start(sp_max, False, False, 0)
        hb.pack_start(cb_pre, False, False, 0)
        hb.pack_start(Gtk.Label(label=p["scale_max"]["kind"]), False, False, 0)
        gr.attach(hb, 1, 2, 1, 1)

        # Componentes
        gr = self._frame(self.tr("elements"), vb)
        r = 0
        for key, label in (("title_bar", "title_bar"), ("show_dl", "show_dl"),
                           ("show_ul", "show_ul"), ("show_total", "show_total"),
                           ("show_quota", "show_quota")):
            r = self._check_row(gr, r, "plot", key, self.tr(label))
        r = self._check_row(gr, r, "plot", "hide_y_labels", self.tr("hide_labels"))
        r = self._check_row(gr, r, "plot", "font_autosize", self.tr("font_auto"))
        r = self._check_row(gr, r, "plot", "window_frame", self.tr("window_mode"))

        # Estilos
        gr = self._frame(self.tr("colors"), vb)
        r = self._combo_row(gr, 0, self.tr("theme"),
                            (("dark", self.tr("dark")), ("light", self.tr("light")),
                             ("system", self.tr("system"))), p.get("theme", "dark"),
                            self._on_theme)
        adj = Gtk.Adjustment(value=p["transparency"], lower=0, upper=90, step_increment=5)
        sc = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        sc.set_value_pos(Gtk.PositionType.RIGHT)
        sc.set_size_request(200, -1)
        sc.set_draw_value(True)
        sc.connect("value-changed", lambda w: (p.__setitem__("transparency", int(w.get_value())),
                                               self.app.win._set_wm_opacity(
                                                   self.app.win._target_opacity()),
                                               self.app.tray.update(force=True)))
        r = self._row(gr, r, self.tr("transparency"), sc)

        # Colores por componente (editan la paleta del tema activo)
        self._color_buttons = {}
        for i, key in enumerate(COLOR_KEYS):
            btn = Gtk.ColorButton()
            btn.set_rgba(Gdk.RGBA(*hex_to_rgba(self._palette()[key])))
            btn.connect("color-set", self._on_color, key)
            self._color_buttons[key] = btn
            gr.attach(Gtk.Label(label=self.tr(key), halign=Gtk.Align.START), 0, r, 1, 1)
            gr.attach(btn, 1, r, 1, 1)
            r += 1
        self._color_hint = Gtk.Label(label="", wrap=True, halign=Gtk.Align.START)
        vb.pack_start(self._color_hint, False, False, 2)
        self._update_color_hint()

        self._label(vb, "La transparencia bajo el cursor y en clic a través del "
                        "original no se configuran aparte: con «Ocultar bajo el "
                        "puntero» la ventana se desvanece y deja pasar los clics.")
        return _scroll(vb)

    def _palette(self):
        """Paleta que editan los botones de color: la del tema elegido."""
        p = self.cfg["plot"]
        key = "light" if p.get("theme") == "light" else "dark"
        return p["colors"][key]

    def _update_color_hint(self):
        theme = self.cfg["plot"].get("theme", "dark")
        if theme == "system":
            self._color_hint.set_text("Tema «Sistema»: los colores los toma del "
                                      "escritorio. Elige Oscuro o Claro para editarlos.")
            for b in self._color_buttons.values():
                b.set_sensitive(False)
        else:
            self._color_hint.set_text("Editando la paleta del tema «%s»." %
                                      self.tr("light" if theme == "light" else "dark"))
            for b in self._color_buttons.values():
                b.set_sensitive(True)

    def _on_theme(self, value):
        self.cfg["plot"]["theme"] = value
        for key, btn in getattr(self, "_color_buttons", {}).items():
            btn.set_rgba(Gdk.RGBA(*hex_to_rgba(self._palette()[key])))
        self._update_color_hint()

    def _on_color(self, btn, key):
        rgba = btn.get_rgba()
        hexc = "#%02x%02x%02x" % (round(rgba.red * 255), round(rgba.green * 255),
                                  round(rgba.blue * 255))
        self._palette()[key] = hexc
        self.app.apply_live()

    # ── página: Cuota ──
    def _page_quota(self):
        q = self.cfg["quota"]
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        gr = self._frame(self.tr("quota"), vb)
        r = self._check_row(gr, 0, "quota", "enabled", self.tr("q_enabled"))
        r = self._spin_row(gr, r, self.tr("limit"), q["limit"]["value"], 1, 100000, 1,
                           lambda v: self._set_limit(v))
        hb = Gtk.Box(spacing=4)
        cb_p = Gtk.ComboBoxText()
        for pre in ("", "k", "M", "G", "T"):
            cb_p.append_text(pre if pre else "—")
        cb_p.set_active(["", "k", "M", "G", "T"].index(q["limit"]["prefix"]))
        cb_p.connect("changed", lambda w: (q["limit"].__setitem__(
            "prefix", ["", "k", "M", "G", "T"][max(0, w.get_active())]), self.app.apply_live()))
        cb_k = Gtk.ComboBoxText()
        for kk in ("b", "ib", "B", "iB"):
            cb_k.append_text(kk)
        cb_k.set_active(["b", "ib", "B", "iB"].index(q["limit"]["kind"]))
        cb_k.connect("changed", lambda w: (q["limit"].__setitem__(
            "kind", w.get_active_text()), self.app.apply_live()))
        hb.pack_start(cb_p, False, False, 0)
        hb.pack_start(cb_k, False, False, 0)
        gr.attach(hb, 1, r, 1, 1)
        self._limit_label = Gtk.Label(label="", halign=Gtk.Align.START)
        vb.pack_start(self._limit_label, False, False, 0)
        self._refresh_limit_label()
        cb_k.connect("changed", lambda w: self._refresh_limit_label())

        # ámbito del contador
        gr = self._frame(self.tr("stat_q_scope"), vb)
        cb_scope = Gtk.ComboBoxText()
        cb_scope.append_text(self.tr("scope_all"))
        cb_scope.append_text(self.tr("scope_iface"))
        cb_scope.set_active(0 if q.get("scope", "all") == "all" else 1)
        ifaces = sorted(n for n in read_interfaces() if not is_loopback(n))
        cb_if = Gtk.ComboBoxText()
        for n in ifaces:
            cb_if.append_text(n)
        cur = q.get("interface") or (ifaces[0] if ifaces else "")
        if cur and cur in ifaces:
            cb_if.set_active(ifaces.index(cur))
        cb_scope.connect("changed", lambda w: (q.__setitem__(
            "scope", "all" if w.get_active() == 0 else "iface"), self.app.apply_live()))
        cb_if.connect("changed", lambda w: (q.__setitem__("interface", w.get_active_text()),
                                            self.app.apply_live()))
        cb_if.set_sensitive(q.get("scope", "all") == "iface")
        cb_scope.connect("changed", lambda w: cb_if.set_sensitive(w.get_active() == 1))
        self._row(gr, 0, self.tr("stat_q_scope"), cb_scope)
        self._row(gr, 1, self.tr("interfaces"), cb_if)
        self._label(vb, "El contador por interfaz no se mezcla al cambiar de fuente: "
                        "cada interfaz lleva su propia base de lectura.")

        # periodo
        gr = self._frame(self.tr("period"), vb)
        r = self._combo_row(gr, 0, self.tr("period"),
                            (("day", self.tr("day")), ("week", self.tr("week")),
                             ("month", self.tr("month"))), q["period_kind"],
                            self._setter("quota", ("period_kind",)))
        r = self._spin_row(gr, r, self.tr("reset_day"), q["reset_day_number"], 1, 28, 1,
                           self._setter("quota", ("reset_day_number",)))
        from datetime import date
        dows = [(i, date(2023, 4, 3 + i).strftime("%A")) for i in range(7)]
        r = self._combo_row(gr, r, self.tr("reset_dow"), dows, int(q["reset_day_of_week"]) % 7,
                            lambda v: self.cfg["quota"].__setitem__("reset_day_of_week", int(v)))
        e_hour = Gtk.Entry()
        e_hour.set_text(q["reset_hour"])
        e_hour.set_width_chars(6)

        def hour_changed(w):
            txt = w.get_text().strip()
            try:
                hh, mm = (int(x) for x in txt.split(":")[:2])
                assert 0 <= hh < 24 and 0 <= mm < 60
            except Exception:
                return
            q["reset_hour"] = "%02d:%02d" % (hh, mm)
            self.app.apply_live()

        e_hour.connect("focus-out-event", lambda w, e: (hour_changed(w), False)[1])
        e_hour.connect("activate", hour_changed)
        r = self._row(gr, r, self.tr("reset_hour"), e_hour)

        # contador
        gr = self._frame(self.tr("stat_q_used"), vb)
        used = float(q.get("used_bytes", 0.0) or 0.0)
        adj = Gtk.Adjustment(value=used, lower=0, upper=1e15, step_increment=1024)
        sp_used = Gtk.SpinButton(adjustment=adj, digits=0)
        sp_used.set_value(used)
        hb = Gtk.Box(spacing=4)
        hb.pack_start(sp_used, False, False, 0)
        l_used = Gtk.Label(label=fmt_amount(used, q["limit"]["kind"]))
        hb.pack_start(l_used, False, False, 0)

        def set_used(*_):
            val = sp_used.get_value()
            self.app.sampler.set_quota_counter(val)
            l_used.set_text(fmt_amount(val, q["limit"]["kind"]))
            self.app.apply_live()

        sp_used.connect("value-changed", set_used)
        self._row(gr, 0, self.tr("stat_q_used"), hb)
        b_reset_c = Gtk.Button(label=self.tr("reset_counter"))
        b_reset_c.connect("clicked", lambda *_: (sp_used.set_value(0), set_used()))
        self._row(gr, 1, "", b_reset_c)
        self._label(vb, self.tr("q_note"))
        self._label(vb, "«Ajustar contador» también está en Estadísticas → Datos.")
        return _scroll(vb)

    def _set_limit(self, value):
        self.cfg["quota"]["limit"]["value"] = value
        self._refresh_limit_label()

    def _refresh_limit_label(self):
        q = self.cfg["quota"]
        total = parse_amount(q["limit"]["value"], q["limit"]["prefix"], q["limit"]["kind"])
        self._limit_label.set_text("= %s" % fmt_amount(total, q["limit"]["kind"]))

    # ── acciones ──
    def on_reset(self, *_):
        from .core import default_settings
        fresh = default_settings()
        fresh["general"]["language"] = self.cfg["general"]["language"]
        fresh["general"]["location"] = self.cfg["general"]["location"]
        fresh["quota"]["period_start"] = self.cfg["quota"].get("period_start", "")
        fresh["quota"]["used_bytes"] = self.cfg["quota"].get("used_bytes", 0)
        self.cfg.clear()
        self.cfg.update(fresh)
        self.app.apply_live()
        save_settings(self.cfg)
        self.destroy()
        self.app.reopen_settings()

    def on_cancel(self, *_):
        """Descartar: restaura el estado de la config al abrir la ventana."""
        self.cfg.clear()
        self.cfg.update(copy.deepcopy(self._snapshot))
        self.app.apply_live()
        save_settings(self.cfg)
        self.destroy()

    def on_apply(self, *_):
        save_settings(self.cfg)
        self.app.apply_all()
        self._snapshot = copy.deepcopy(self.cfg)
        if self._lang_changed():
            self._reopen_for_language()

    def on_ok(self, *_):
        self.on_apply()
        self.destroy()

    def _lang_changed(self):
        return self._snapshot.get("general", {}).get("language") != self.cfg["general"]["language"]

    def _reopen_for_language(self):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True,
                                message_type=Gtk.MessageType.INFO,
                                buttons=Gtk.ButtonsType.OK,
                                text="Idioma cambiado / Language changed")
        dlg.format_secondary_text("Se reabre Ajustes para aplicar los textos.\n"
                                  "Settings reopen to apply the new texts.")
        dlg.run()
        dlg.destroy()
        self.destroy()
        self.app.reopen_settings()