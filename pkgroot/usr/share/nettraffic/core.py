#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Núcleo de nettraffic-linux: i18n (es/en), unidades, configuración,
periodo de cuota, lectura de /proc/net/dev y muestreo con estadísticas."""
import glob
import json
import math
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta

APP_ID = "nettraffic-linux"
APP_TITLE = "NetTraffic"
VERSION = "1.0.0"
CONF_DIR = os.path.expanduser("~/.config/nettraffic")
CONF_FILE = os.path.join(CONF_DIR, "settings.json")
STATS_DIR = os.path.join(CONF_DIR, "stats")

# ─────────────────────────── IDIOMAS: solo español e inglés ───────────────────────────
LANGS = {
    "es": {
        "settings": "Ajustes", "statistic": "Estadísticas", "about": "Acerca de...",
        "exit": "Salir", "show": "Mostrar gráfica", "hide": "Ocultar gráfica",
        "window_mode": "Gráfica en ventana con marco", "on_top": "Siempre encima",
        "click_through": "Hacer clic a través", "hide_under_pointer": "Ocultar bajo el puntero",
        "hide_fullscreen": "Ocultar con otra ventana a pantalla completa",
        "general": "General", "chart": "Gráfica", "quota": "Cuota",
        "language": "Idioma", "frequency": "Intervalo de actualización (ms)",
        "interfaces": "Interfaces de red", "if_all": "Usar todas las interfaces",
        "if_selected": "Usar interfaces seleccionadas", "exclude_lo": "Excluir bucle invertido (lo)",
        "behavior": "Comportamiento", "close_tray": "Cerrar a la bandeja",
        "start_system": "Iniciar con el sistema", "start_min": "Iniciar oculto (solo bandeja)",
        "units": "Unidades base", "data_rate": "Velocidad de datos (b/B/ib/iB)",
        "type": "Tipo de gráfica", "shape": "Forma", "points": "Puntos (eje X)",
        "point_width": "Ancho de punto (px)", "buffer": "Puntos en búfer",
        "scale": "Escala máxima (eje Y)", "auto": "Automática", "manual": "Fija",
        "scale_max": "Máximo (escala Y)",
        "show_dl": "Descarga", "show_ul": "Subida", "show_total": "Total", "show_quota": "Cuota",
        "hide_labels": "Ocultar etiquetas del eje Y", "font_auto": "Auto-escala de fuente",
        "transparency": "Transparencia de la ventana (%)", "theme": "Tema",
        "dark": "Oscuro", "light": "Claro", "system": "Sistema", "colors": "Colores",
        "download": "Descarga", "upload": "Subida", "total": "Total",
        "activity": "Actividad", "background": "Fondo", "font": "Fuente", "axis": "Eje",
        "area": "Área", "column": "Columnas", "line": "Líneas",
        "rectangle": "Rectangular", "pie": "Circular (velocímetro)",
        "title_bar": "Barra de título de la gráfica", "elements": "Elementos",
        "q_enabled": "Conteo habilitado", "limit": "Límite", "period": "Periodo",
        "day": "Día", "week": "Semana", "month": "Mes",
        "reset_day": "Día de reinicio (día del mes)", "reset_dow": "Día de reinicio (día de semana)",
        "reset_hour": "Hora de reinicio (HH:MM)", "reset_counter": "Reiniciar contador ahora",
        "q_note": "Redefinir el inicio del periodo abre un contador nuevo en cero.",
        "used": "Usado", "left": "Restante", "period_end": "Fin del periodo",
        "session": "Sesión actual", "table": "Tabla", "date": "Fecha",
        "export": "Exportar CSV", "clear_data": "Borrar datos",
        "ask_clear": "¿Borrar todas las estadísticas guardadas?",
        "ok": "OK", "apply": "Aplicar", "cancel": "Cancelar", "reset": "Por defecto",
        "no_data": "Sin datos", "avg": "Promedio", "speed": "Velocidad",
        "about_text": "Monitor de tráfico de red para Linux.\nReimplementación libre inspirada en NetTraffic (venea.net).",
        "data": "Datos",
        "window": "Ventana", "window_state": "Estado de la ventana al iniciar",
        "ws_normal": "Mostrar normalmente", "ws_minimized": "Iniciar oculto (solo bandeja)",
        "data_source": "Fuente de datos", "rescan": "Re-escanear disponibilidad cada (s)",
        "stat_q_adjust": "Ajustar contador", "stat_q_notset": "Sin iniciar",
        "stat_q_scope": "Contador por", "scope_all": "Todas las interfaces",
        "scope_iface": "Interfaz seleccionada", "quota_min": "Mínimo del periodo",
        "quota_max": "Máximo del periodo",
        # ── estadísticas (textos del original) ──
        "stat_general": "General", "stat_advanced": "Gráficos / tablas",
        "stat_plot": "Gráfico", "stat_table": "Tabla",
        "stat_date_range": "Rango de fechas", "stat_from": "Desde", "stat_to": "Hasta",
        "stat_time_unit": "Unidad de tiempo", "unit_year": "Año", "unit_month": "Mes",
        "unit_day": "Día", "unit_hour": "Hora",
        "stat_find": "Buscar", "stat_no_data": "No hay datos disponibles para el rango seleccionado.",
        "stat_now": "Estado actual", "stat_avg2": "Promedio", "stat_prognosis": "Pronóstico",
        "stat_time": "Tiempo", "stat_received": "Recibido", "stat_sent": "Enviado",
        "stat_cursor": "Cursor", "stat_distance": "Distancia",
        "stat_q_used": "Usado", "stat_q_limit": "Límite", "stat_q_left": "Restante",
        "stat_q_period": "Periodo", "stat_q_begin": "Inicio", "stat_q_end": "Final",
        "stat_q_factor": "Factor",
        "stat_data_export": "Exportar", "stat_data_delete": "Borrar",
        "stat_ask_clear": "¿Está seguro de que desea eliminar los datos estadísticos?",
        "stat_transfer": "Transferencia", "stat_adjustment": "Ajuste",
        "stat_remain": "Restante", "stat_length": "Duración",
        "chart_traffic": "Tráfico", "chart_uptime": "Tiempo activo",
        "all_time": "Desde el inicio", "sum_total": "Suma",
    },
    "en": {
        "settings": "Settings", "statistic": "Statistics", "about": "About...",
        "exit": "Exit", "show": "Show chart", "hide": "Hide chart",
        "window_mode": "Chart in framed window", "on_top": "Always on top",
        "click_through": "Click through", "hide_under_pointer": "Hide under pointer",
        "hide_fullscreen": "Hide when other window is fullscreen",
        "general": "General", "chart": "Chart", "quota": "Quota",
        "language": "Language", "frequency": "Update interval (ms)",
        "interfaces": "Network interfaces", "if_all": "Use all interfaces",
        "if_selected": "Use selected interfaces", "exclude_lo": "Exclude loopback (lo)",
        "behavior": "Behavior", "close_tray": "Close to tray",
        "start_system": "Start with system", "start_min": "Start hidden (tray only)",
        "units": "Base units", "data_rate": "Data rate unit (b/B/ib/iB)",
        "type": "Chart type", "shape": "Shape", "points": "Data points (axis X)",
        "point_width": "Point width (px)", "buffer": "Points in buffer",
        "scale": "Scale maximum (axis Y)", "auto": "Automatic", "manual": "Fixed",
        "scale_max": "Maximum (Y scale)",
        "show_dl": "Download", "show_ul": "Upload", "show_total": "Total", "show_quota": "Quota",
        "hide_labels": "Hide Y axis labels", "font_auto": "Font auto-scale",
        "transparency": "Window transparency (%)", "theme": "Theme",
        "dark": "Dark", "light": "Light", "system": "System", "colors": "Colors",
        "download": "Download", "upload": "Upload", "total": "Total",
        "activity": "Activity", "background": "Background", "font": "Font", "axis": "Axis",
        "area": "Area", "column": "Column", "line": "Line",
        "rectangle": "Rectangle", "pie": "Circular (speedometer)",
        "title_bar": "Chart title bar", "elements": "Elements",
        "q_enabled": "Counting enabled", "limit": "Limit", "period": "Period",
        "day": "Day", "week": "Week", "month": "Month",
        "reset_day": "Reset day (day of month)", "reset_dow": "Reset day (day of week)",
        "reset_hour": "Reset hour (HH:MM)", "reset_counter": "Reset counter now",
        "q_note": "Redefining period beginning opens a new counter at zero.",
        "used": "Used", "left": "Left", "period_end": "Period end",
        "session": "Current session", "table": "Table", "date": "Date",
        "export": "Export CSV", "clear_data": "Clear data",
        "ask_clear": "Delete all saved statistics?",
        "ok": "OK", "apply": "Apply", "cancel": "Cancel", "reset": "Reset",
        "no_data": "No data", "avg": "Average", "speed": "Speed",
        "about_text": "Network traffic monitor for Linux.\nFree reimplementation inspired by NetTraffic (venea.net).",
        "data": "Data",
        "window": "Window", "window_state": "Window state at startup",
        "ws_normal": "Show normally", "ws_minimized": "Start hidden (tray only)",
        "data_source": "Data source", "rescan": "Rescan availability every (s)",
        "stat_q_adjust": "Adjust counter", "stat_q_notset": "Not started",
        "stat_q_scope": "Counter scope", "scope_all": "All interfaces",
        "scope_iface": "Selected interface", "quota_min": "Period minimum",
        "quota_max": "Period maximum",
        # ── statistics (original texts) ──
        "stat_general": "General", "stat_advanced": "Charts / tables",
        "stat_plot": "Chart", "stat_table": "Table",
        "stat_date_range": "Date range", "stat_from": "From", "stat_to": "To",
        "stat_time_unit": "Time unit", "unit_year": "Year", "unit_month": "Month",
        "unit_day": "Day", "unit_hour": "Hour",
        "stat_find": "Search", "stat_no_data": "No data is available for selected date range.",
        "stat_now": "Current State", "stat_avg2": "Average", "stat_prognosis": "Prognosis",
        "stat_time": "Time", "stat_received": "Received", "stat_sent": "Sent",
        "stat_cursor": "Cursor", "stat_distance": "Distance",
        "stat_q_used": "Used", "stat_q_limit": "Limit", "stat_q_left": "Left",
        "stat_q_period": "Period", "stat_q_begin": "Beginning", "stat_q_end": "End",
        "stat_q_factor": "Factor",
        "stat_data_export": "Export", "stat_data_delete": "Delete",
        "stat_ask_clear": "Are you sure you want to delete statistical data?",
        "stat_transfer": "Transfer", "stat_adjustment": "Adjustment",
        "stat_remain": "Remain", "stat_length": "Length",
        "chart_traffic": "Traffic", "chart_uptime": "Up time",
        "all_time": "All time", "sum_total": "Sum",
    },
}


class Tr:
    """Traductor ligado a la config activa."""
    def __init__(self, cfg):
        self.cfg = cfg

    def __call__(self, key):
        lang = self.cfg["general"]["language"]
        return LANGS.get(lang, LANGS["es"]).get(key, key)


# ─────────────────────────── CONFIGURACIÓN ───────────────────────────
def _colors_dark():
    return {"download": "#22c55e", "upload": "#ef4444", "total": "#3b82f6",
            "activity": "#eab308", "font": "#e2e8f0", "axis": "#64748b", "back": "#1e293b"}


def _colors_light():
    return {"download": "#16a34a", "upload": "#dc2626", "total": "#2563eb",
            "activity": "#ca8a04", "font": "#1e293b", "axis": "#94a3b8", "back": "#f1f5f9"}


def system_theme_colors():
    """Colores reales del tema GTK del escritorio (vía GTK named colors).
    Fondo = theme_bg_color, texto = theme_fg_color, ejes = mezcla;
    verde/rojo de success/error_color del propio tema. Si algo falla,
    cae a los colores oscuros de siempre."""
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk, Gdk
        ctx = Gtk.StyleContext.new()
        ctx.set_screen(Gdk.Screen.get_default())
        ctx.add_class(Gtk.STYLE_CLASS_BACKGROUND)

        def hexc(name, fallback):
            ok, rgba = ctx.lookup_color(name)
            if not ok:
                return fallback
            try:
                return "#%02x%02x%02x" % (round(rgba.red * 255),
                                          round(rgba.green * 255),
                                          round(rgba.blue * 255))
            except Exception:
                return fallback

        back = hexc("theme_bg_color", "#1e293b")
        font = hexc("theme_fg_color", "#e2e8f0")
        return {"download": hexc("success_color", "#22c55e"),
                "upload": hexc("error_color", "#ef4444"),
                "total": hexc("theme_selected_bg_color", "#3b82f6"),
                "activity": hexc("warning_color", "#eab308"),
                "font": font,
                "axis": font,           # ejes con el color de texto del tema
                "back": back}
    except Exception:
        return _colors_dark()


def theme_colors(cfg):
    """Colores del tema elegido. Con 'system' los toma del escritorio GTK.
    Un solo lugar para chart/tray/stats (antes cada módulo repetía la lógica)."""
    p = cfg["plot"]
    theme = p.get("theme", "dark")
    if theme == "system":
        return system_theme_colors()
    if theme == "custom":
        custom = p.get("custom")
        if isinstance(custom, dict):
            base = dict(p["colors"].get(p.get("custom_base", "dark"),
                                        p["colors"]["dark"]))
            base.update({k: v for k, v in custom.items() if v})
            return base
    return p["colors"].get(theme, p["colors"]["dark"])


def default_settings():
    return {
        "version": 1,
        "general": {
            "language": "es", "frequency_ms": 1000,
            "window_restore": 1, "close_to_tray": True, "on_top": True,
            "click_through": False, "hide_under_pointer": False, "hide_when_fullscreen": False,
            "start_with_system": False,
            "interfaces_mode": "all", "exclude_loopback": True, "selected_interfaces": [],
            "rescan_seconds": 10,
            "unit_speed": "iB",
            "location": {"x": 60, "y": 40, "width": 320, "height": 120},
        },
        "plot": {
            "theme": "dark", "chart_type": "area", "chart_shape": "rectangle",
            "points_count": 60, "point_width": 3, "points_buffer": 600,
            "scale_y": "auto", "scale_max": {"value": 1, "prefix": "M", "kind": "iB"},
            "show_dl": True, "show_ul": True, "show_total": False, "show_quota": True,
            "hide_y_labels": False, "font_autosize": True, "transparency": 0,
            "window_frame": False, "title_bar": True,
            "colors": {"dark": _colors_dark(), "light": _colors_light()},
            "custom": {}, "custom_base": "dark",
        },
        "quota": {
            "enabled": False,
            "limit": {"value": 50, "prefix": "G", "kind": "iB"},
            "period_kind": "month", "reset_day_number": 1, "reset_day_of_week": 0,
            "reset_hour": "00:00", "used_bytes": 0, "period_start": "",
            # scope: 'all' = suma de interfaces; 'iface' = solo la interfaz elegida
            "scope": "all", "interface": "",
            # base por interfaz para que cambiar de fuente NO mezcle contadores
            "iface_bytes": {}, "iface_ts": {},
            "period_min": None, "period_max": None, "period_max_day": "",
            # 'adjustment' es lo que el usuario corrige a mano (como el original:
            # "Current value of counter can be changed (adjusted)"), separado de
            # la transferencia medida
            "adjustment_bytes": 0,
        },
        "stats": {
            # distancia recorrida por el puntero (el 'Cursor' del original, en km)
            "cursor_m": 0.0, "cursor_started": "",
        },
    }


def deep_merge(base, override):
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings():
    os.makedirs(CONF_DIR, exist_ok=True)
    try:
        with open(CONF_FILE, "r", encoding="utf-8") as f:
            return deep_merge(default_settings(), json.load(f))
    except FileNotFoundError:
        return default_settings()
    except Exception as e:
        print("settings corruptos (%s); usando valores por defecto" % e)
        return default_settings()


def save_settings(cfg):
    os.makedirs(CONF_DIR, exist_ok=True)
    with open(CONF_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ─────────────────────────── UNIDADES ───────────────────────────
def fmt_amount(n_bytes, kind, per_second=False):
    """kind: b (bits), ib (bits binarios), B (bytes), iB (bytes binarios)."""
    binary = kind in ("ib", "iB")
    is_bits = kind in ("b", "ib")
    n = float(n_bytes) * (8.0 if is_bits else 1.0)
    div = 1024.0 if binary else 1000.0
    istr = "i" if binary else ""
    unit = "b" if is_bits else "B"
    tail = "/s" if per_second else ""
    for prefix in ("", "k", "M", "G", "T"):
        if n < div:
            if prefix == "":
                return "%.0f %s%s" % (n, unit, tail)
            return "%.2f %s%s%s%s" % (n, prefix, istr, unit, tail)
        n /= div
    return "%.2f T%s%s%s" % (n, istr, unit, tail)


def parse_amount(value, prefix, kind):
    """(valor, prefijo, tipo) → bytes."""
    mult = 1024 if kind in ("ib", "iB") else 1000
    p = {"": 1, "one": 1, "k": mult, "M": mult ** 2, "G": mult ** 3, "T": mult ** 4}.get(prefix, 1)
    v = float(value) * p
    if kind in ("b", "ib"):
        v /= 8.0
    return v


def hex_to_rgba(hexc, alpha=1.0):
    hexc = hexc.lstrip("#")
    if len(hexc) == 3:
        hexc = "".join(c * 2 for c in hexc)
    return tuple(int(hexc[i:i + 2], 16) / 255.0 for i in (0, 2, 4)) + (alpha,)


def nice_ceil(v):
    if v <= 0:
        return 1.0
    exp = math.floor(math.log10(v))
    base = 10.0 ** exp
    for m in (1, 2, 5, 10):
        if v <= m * base:
            return m * base
    return 10 * base


# ─────────────────────────── /proc/net/dev ───────────────────────────
def read_interfaces():
    ifaces = {}
    try:
        with open("/proc/net/dev", "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines[2:]:
            if ":" not in line:
                continue
            name, rest = line.split(":", 1)
            fields = rest.split()
            if len(fields) >= 9:
                ifaces[name.strip()] = (int(fields[0]), int(fields[8]))
    except Exception:
        pass
    return ifaces


def is_loopback(name):
    return name == "lo" or name.startswith("lo.")


# ─────────────────────────── CUOTA: periodo ───────────────────────────
def _month_start(y, m, day, hh, mm):
    """Inicio del periodo mensual (día clamp al mes). Lanza ValueError si día inválido."""
    import calendar
    day_eff = max(1, min(int(day), calendar.monthrange(y, m)[1]))
    return datetime(y, m, day_eff, hh, mm)


def quota_period_bounds(cfg, now=None):
    """Regresa (inicio, fin) del periodo de cuota vigente."""
    q = cfg["quota"]
    now = now or datetime.now()
    try:
        hh, mm = [int(x) for x in q["reset_hour"].split(":")[:2]]
    except Exception:
        hh, mm = 0, 0
    kind = q["period_kind"]
    if kind == "day":
        start = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if start > now:
            start -= timedelta(days=1)
        return start, start + timedelta(days=1)
    if kind == "week":
        dow = int(q["reset_day_of_week"]) % 7
        start = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        start -= timedelta(days=(start.weekday() - dow) % 7)
        if start > now:
            start -= timedelta(days=7)
        return start, start + timedelta(days=7)
    # mes: día de reinicio (1-28), fin = mismo día del mes siguiente
    day = max(1, min(28, int(q["reset_day_number"])))
    y, m = now.year, now.month
    start = _month_start(y, m, day, hh, mm)
    if start > now:
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        start = _month_start(y, m, day, hh, mm)
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return start, _month_start(ny, nm, day, hh, mm)


def quota_period_progress(cfg, now=None):
    now = now or datetime.now()
    start, end = quota_period_bounds(cfg, now)
    total = (end - start).total_seconds()
    if total <= 0:
        return 1.0
    return min(1.0, max(0.0, (now - start).total_seconds() / total))


# ─────────────────────────── PANTALLA COMPLETA (X11) ───────────────────────────
def other_window_fullscreen():
    try:
        out = subprocess.run(["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                             capture_output=True, text=True, timeout=3).stdout
        wid = out.strip().split()[-1]
        if not wid.startswith("0x"):
            return False
        out = subprocess.run(["xprop", "-id", wid, "_NET_WM_STATE"],
                             capture_output=True, text=True, timeout=3).stdout
        return "_NET_WM_STATE_FULLSCREEN" in out
    except Exception:
        return False


# ─────────────────────────── X11 SHAPE (click-through) ───────────────────────────
class X11Shape:
    SHAPE_BOUNDING, SHAPE_INPUT, SHAPE_SET = 0, 2, 0

    def __init__(self):
        self.lib = None
        self.xext = None
        try:
            import ctypes
            self.ct = ctypes
            # XOpenDisplay/XFlush viven en libX11; las funciones de SHAPE en libXext
            self.lib = ctypes.CDLL("libX11.so.6")
            self.lib.XOpenDisplay.restype = ctypes.c_void_p
            self.xext = ctypes.CDLL("libXext.so.6")
            self.xext.XShapeCombineRectangles.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
            self.xext.XShapeCombineShape.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_ulong, ctypes.c_int, ctypes.c_int]
            self.display = self.lib.XOpenDisplay(None)
        except Exception as e:
            print("nettraffic: sin soporte de clic a través (XShape): %s" % e)
            self.lib = None
            self.xext = None

    def available(self):
        return (self.lib is not None and self.xext is not None
                and getattr(self, "display", None) is not None)

    def set_click_through(self, xid, enabled):
        """Vacía (o restaura) la forma de ENTRADA de una ventana X.
        OJO: hay que hacerlo en la ventana principal Y en cada ventana hija de
        GDK (GtkDrawingArea tiene la suya propia): recortar solo la principal
        deja al hijo tragándose los clics."""
        if not self.available() or not xid:
            return False
        ct = self.ct
        disp = ct.c_void_p(self.display)
        if enabled:
            self.xext.XShapeCombineRectangles(disp, ct.c_ulong(xid), self.SHAPE_INPUT,
                                              0, 0, None, 0, self.SHAPE_SET, 0)
        else:
            self.xext.XShapeCombineShape(disp, ct.c_ulong(xid), self.SHAPE_INPUT, 0, 0,
                                         ct.c_ulong(xid), self.SHAPE_BOUNDING, self.SHAPE_SET)
        # el servidor consulta la región vacía al instante: hace falta sincronizar
        # y, en este entorno (Compiz/GTK), volver a aplicarla tras el repintado
        self.lib.XSync(disp, False)
        self.lib.XFlush(disp)
        return True

    def window_xids(self, gtk_widget):
        """XIDs de la ventana del widget y de sus ventanas GDK descendientes."""
        out = []
        try:
            win = gtk_widget.get_window()
            if win is None:
                return out
            out.append(win.get_xid())

            def walk(w):
                try:
                    for c in w.get_children():
                        out.append(c.get_xid())
                        walk(c)
                except Exception:
                    pass

            walk(win)
        except Exception:
            pass
        return out

    def apply_to_widget(self, gtk_widget, enabled):
        ok = False
        for xid in self.window_xids(gtk_widget):
            ok = self.set_click_through(xid, enabled) or ok
        return ok


# ─────────────────────────── SAMPLER ───────────────────────────
class RateSampler(threading.Thread):
    """Hilo de muestreo: tasas DL/UL, historial, sesión, cuota y estadísticas por mes."""

    FLUSH_EVERY = 60           # muestras entre volcados a disco
    RESCAN_DEFAULT = 10        # segundos entre re-escaneos de interfaces

    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.stop_flag = threading.Event()
        self.lock = threading.RLock()
        self.dl_rate = 0.0
        self.ul_rate = 0.0
        self.session_rx = 0.0
        self.session_tx = 0.0
        self.history = []
        self.last = None
        self.available = {}         # interfaces con al menos un paquete
        self._iface_reported = set()
        self._last_rescan = 0.0
        self.month_stats = {"month": "", "days": {}, "hours": {},
                            "day_secs": {}, "hour_secs": {}}
        self._flush_counter = 0
        with self.lock:
            self._load_month(datetime.now())

    # ── estadísticas por mes (JSON en disco) ──
    def _month_file(self, ym):
        os.makedirs(STATS_DIR, exist_ok=True)
        return os.path.join(STATS_DIR, "%s.json" % ym)

    def _load_month(self, now):
        ym = now.strftime("%Y-%m")
        data = load_month_stats(ym)
        if data:
            for k, v in (("days", {}), ("hours", {}), ("day_secs", {}), ("hour_secs", {})):
                data.setdefault(k, v)
            self.month_stats = data
            return
        self.month_stats = {"month": ym, "days": {}, "hours": {},
                            "day_secs": {}, "hour_secs": {}}

    def _flush_month(self):
        try:
            os.makedirs(STATS_DIR, exist_ok=True)
            with open(self._month_file(self.month_stats["month"]), "w", encoding="utf-8") as f:
                json.dump(self.month_stats, f)
        except Exception:
            pass

    def stop(self):
        with self.lock:
            self._flush_month()
        self.stop_flag.set()

    def run(self):
        while not self.stop_flag.is_set():
            t0 = time.monotonic()
            try:
                self._sample_once(t0)
            except Exception:
                pass
            freq = max(0.1, float(self.cfg["general"].get("frequency_ms", 1000)) / 1000.0)
            self.stop_flag.wait(max(0.05, freq - (time.monotonic() - t0)))

    # ── detección de interfaces ──
    def _default_iface(self, ifaces=None):
        """Interfaz para el contador por interfaz: la elegida, o la de más tráfico."""
        q = self.cfg["quota"]
        name = q.get("interface") or ""
        ifaces = self.available if ifaces is None else ifaces
        if name and name in ifaces:
            return name
        cands = [n for n in ifaces if not is_loopback(n)] or list(ifaces)
        if not cands:
            return ""
        return max(cands, key=lambda n: sum(ifaces[n]))

    def _maybe_rescan(self, now_mono):
        every = max(1.0, float(self.cfg["general"].get("rescan_seconds", self.RESCAN_DEFAULT) or self.RESCAN_DEFAULT))
        if self.available and (now_mono - self._last_rescan) < every:
            return
        self._last_rescan = now_mono
        raw = read_interfaces()
        active = {n: v for n, v in raw.items() if (v[0] or v[1])}
        for n in sorted(active):
            if n not in self._iface_reported:
                self._iface_reported.add(n)
                print("nettraffic: interfaz %s rx=%d tx=%d bytes" % (n, active[n][0], active[n][1]))
        self.available = active or raw

    # ── muestreo ──
    def _sample_once(self, now_mono=None):
        now_mono = time.monotonic() if now_mono is None else now_mono
        now_dt = datetime.now()
        g = self.cfg["general"]
        self._maybe_rescan(now_mono)
        ifaces = self.available
        mode = g.get("interfaces_mode", "all")
        sel = set(g.get("selected_interfaces") or [])
        if mode == "selected" and sel:
            names = [n for n in ifaces if n in sel]
        else:
            names = [n for n in ifaces
                     if not (g.get("exclude_loopback", True) and is_loopback(n))]
        rx = float(sum(ifaces[n][0] for n in names))
        tx = float(sum(ifaces[n][1] for n in names))

        if self.last is None:
            self.last = (now_mono, rx, tx)
            with self.lock:
                self._sync_iface_bases(ifaces)
                # arranca el periodo aquí (si no, la primera muestra real se
                # gasta en inicializar period_start y se pierde ese ciclo)
                if q_enabled(self.cfg):
                    self._accrue_quota(ifaces, 0.0, now_dt)
            return
        dt = now_mono - self.last[0]
        if dt <= 0:
            dt = 1e-3
        dl = max(0.0, (rx - self.last[1]) / dt)
        ul = max(0.0, (tx - self.last[2]) / dt)
        self.last = (now_mono, rx, tx)

        with self.lock:
            self.dl_rate, self.ul_rate = dl, ul
            self.session_rx += dl * dt
            self.session_tx += ul * dt
            self.history.append((now_mono, dl, ul))
            buf = max(10, int(self.cfg["plot"].get("points_buffer", 600)))
            if len(self.history) > buf:
                del self.history[:len(self.history) - buf]
            ym = now_dt.strftime("%Y-%m")
            if self.month_stats.get("month") != ym:
                self._flush_month()
                self._load_month(now_dt)
            dkey = now_dt.strftime("%d")
            hkey = now_dt.strftime("%d %H")
            dd = self.month_stats["days"].setdefault(dkey, [0.0, 0.0])
            hh = self.month_stats["hours"].setdefault(hkey, [0.0, 0.0])
            dd[0] += dl * dt
            dd[1] += ul * dt
            hh[0] += dl * dt
            hh[1] += ul * dt
            self.month_stats["day_secs"][dkey] = self.month_stats["day_secs"].get(dkey, 0.0) + dt
            self.month_stats["hour_secs"][hkey] = self.month_stats["hour_secs"].get(hkey, 0.0) + dt
            self._accrue_quota(ifaces, dl * dt + ul * dt, now_dt)

        self._flush_counter += 1
        if self._flush_counter >= self.FLUSH_EVERY:
            self._flush_counter = 0
            with self.lock:
                self._flush_month()

    # ── cuota ──
    def _sync_iface_bases(self, ifaces=None):
        """Fija la lectura actual por interfaz: punto de partida del contador."""
        q = self.cfg["quota"]
        ifaces = self.available if ifaces is None else ifaces
        q["iface_bytes"] = {n: float(v[0] + v[1]) for n, v in ifaces.items()}
        q["iface_ts"] = {n: datetime.now().isoformat(timespec="seconds") for n in ifaces}
        q["iface_active"] = self._default_iface(ifaces)

    def _accrue_quota(self, ifaces, fallback_delta, now_dt):
        """Suma al contador de cuota. Si el ámbito es 'interfaz', usa su delta
        real (así cambiar de fuente no mezcla contadores)."""
        q = self.cfg["quota"]
        if not q.get("enabled"):
            self._sync_iface_bases(ifaces)
            return
        ps_iso = quota_period_bounds(self.cfg, now_dt)[0].isoformat()
        if q.get("period_start") != ps_iso:
            # periodo nuevo: contador a cero y base nueva (sin sumar este ciclo)
            q["period_start"] = ps_iso
            q["used_bytes"] = 0.0
            q["period_min"] = None
            q["period_max"] = None
            q["period_max_day"] = ""
            self._sync_iface_bases(ifaces)
            return

        if q.get("scope", "all") == "iface":
            name = self._default_iface(ifaces)
            if not name or q.get("iface_active") != name:
                # la interfaz cambió (o no hay): re-basar sin sumar
                self._sync_iface_bases(ifaces)
                return
            cur = float(sum(ifaces[name]))
            prev = q["iface_bytes"].get(name)
            if prev is None:
                q["iface_bytes"][name] = cur
                return
            delta = max(0.0, cur - float(prev))
            q["iface_bytes"][name] = cur
            q["iface_ts"][name] = now_dt.isoformat(timespec="seconds")
        else:
            delta = fallback_delta
            self._sync_iface_bases(ifaces)

        if delta <= 0:
            return
        used = float(q.get("used_bytes", 0.0)) + delta
        q["used_bytes"] = used
        mn = q.get("period_min")
        q["period_min"] = used if mn is None else min(float(mn), used)
        mx = q.get("period_max")
        if mx is None or used > float(mx):
            q["period_max"] = used
            q["period_max_day"] = now_dt.strftime("%Y-%m-%d")

    def set_quota_counter(self, value_bytes):
        """Ajuste manual del contador (Ajustes/Estadísticas → Ajustar contador)."""
        with self.lock:
            self.cfg["quota"]["used_bytes"] = float(value_bytes)
            self.cfg["quota"]["period_max"] = float(value_bytes)
            self.cfg["quota"]["period_max_day"] = datetime.now().strftime("%Y-%m-%d")
            mn = self.cfg["quota"].get("period_min")
            self.cfg["quota"]["period_min"] = float(value_bytes) if mn is None else min(float(mn), float(value_bytes))

    def adjust_quota_counter(self, target_used_bytes):
        """Fija el Usado total a un valor dado por el usuario y registra la
        diferencia como 'Ajuste' (como el original: la transferencia medida y
        el ajuste se reportan por separado)."""
        with self.lock:
            q = self.cfg["quota"]
            target = max(0.0, float(target_used_bytes))
            measured = float(q.get("used_bytes", 0.0)) - float(q.get("adjustment_bytes", 0.0))
            q["adjustment_bytes"] = max(0.0, target - max(0.0, measured))
            q["used_bytes"] = target
            q["period_max"] = max(float(q.get("period_max") or 0.0), target)
            q["period_max_day"] = datetime.now().strftime("%Y-%m-%d")

    def get_quota_pct(self):
        q = self.cfg["quota"]
        if not q.get("enabled"):
            return None
        limit = parse_amount(q["limit"]["value"], q["limit"]["prefix"], q["limit"]["kind"])
        if limit <= 0:
            return None
        return min(1.0, max(0.0, float(q.get("used_bytes", 0.0)) / limit))

    # ── consultas thread-safe ──
    def get_rates(self):
        with self.lock:
            return self.dl_rate, self.ul_rate

    def get_points(self, n):
        with self.lock:
            return list(self.history[-n:])

    def get_session_totals(self):
        with self.lock:
            return self.session_rx, self.session_tx

    def get_uptime(self, now=None):
        """Segundos medidos por día/hora del mes en curso (para Tráfico/Tiempo)."""
        now = now or datetime.now()
        with self.lock:
            return {"day_secs": dict(self.month_stats.get("day_secs", {})),
                    "hour_secs": dict(self.month_stats.get("hour_secs", {})),
                    "month": self.month_stats.get("month", "")}

    def get_period_totals(self, now=None):
        """Totales por periodos naturales (hora/día/mes/año en curso) y desde el
        inicio de los registros — como las filas Year/Month/Day/Hour del original.
        Devuelve (rx, tx, segundos_medidos) por periodo; los segundos vienen del
        muestreo real (day_secs/hour_secs), no de la sesión."""
        now = now or datetime.now()
        data = self.get_month_stats()
        days = data.get("days", {})
        d_secs = data.get("day_secs", {})
        h_secs = data.get("hour_secs", {})

        # hora en curso: rx/tx medidos en ESTA hora (clave "DD HH")
        hk = now.strftime("%d %H")
        h_rx, h_tx = data.get("hours", {}).get(hk, [0.0, 0.0])
        # día en curso
        dk = now.strftime("%d")
        d_rx, d_tx = days.get(dk, [0.0, 0.0])
        # mes en curso
        m_rx = sum(v[0] for v in days.values())
        m_tx = sum(v[1] for v in days.values())
        m_s = sum(float(v) for v in d_secs.values())
        # año en curso y desde el inicio: sumando todos los meses guardados
        y_rx = y_tx = y_s = 0.0
        a_rx = a_tx = a_s = 0.0
        for ym, mdata in iter_month_data(available_months(), data.get("month"), data):
            mdays = mdata.get("days", {})
            msec = mdata.get("day_secs", {})
            for v in mdays.values():
                a_rx += v[0]
                a_tx += v[1]
                if ym.startswith(str(now.year)):
                    y_rx += v[0]
                    y_tx += v[1]
            for sv in msec.values():
                s = float(sv)
                a_s += s
                if ym.startswith(str(now.year)):
                    y_s += s
        return {"hour": (h_rx, h_tx, h_secs.get(hk, 0.0)),
                "day": (d_rx, d_tx, d_secs.get(dk, 0.0)),
                "month": (m_rx, m_tx, m_s),
                "year": (y_rx, y_tx, y_s),
                "all": (a_rx, a_tx, a_s)}

    def get_month_stats(self):
        with self.lock:
            return json.loads(json.dumps(self.month_stats))

    def get_iface_totals(self):
        """Lectura actual por interfaz (bytes rx+tx desde el arranque del sistema)."""
        with self.lock:
            return {n: (int(v[0]), int(v[1])) for n, v in self.available.items()}

    def get_iface_bytes(self, name):
        with self.lock:
            return self.cfg["quota"].get("iface_bytes", {}).get(name)

    def reset_session(self):
        with self.lock:
            self.session_rx = self.session_tx = 0.0
            self.history.clear()

    def clear_stats(self):
        with self.lock:
            for f in glob.glob(os.path.join(STATS_DIR, "*.json")):
                try:
                    os.remove(f)
                except Exception:
                    pass
            self.month_stats = {"month": datetime.now().strftime("%Y-%m"),
                                "days": {}, "hours": {}, "day_secs": {}, "hour_secs": {}}
            self.session_rx = self.session_tx = 0.0
            self._flush_month()


def q_enabled(cfg):
    """¿El conteo de cuota está activo?"""
    return bool(cfg.get("quota", {}).get("enabled"))


# ─────────────────────────── ESTADÍSTICAS EN DISCO ───────────────────────────
def available_months():
    """Meses con estadísticas guardadas ('YYYY-MM'), más reciente primero."""
    try:
        names = [os.path.basename(f)[:-5] for f in glob.glob(os.path.join(STATS_DIR, "*.json"))]
        return sorted((m for m in names if len(m) == 7 and m[4] == "-"), reverse=True)
    except Exception:
        return []


def load_month_stats(ym):
    """Estadísticas guardadas de un mes, o None si no existen/es inválidas."""
    try:
        with open(os.path.join(STATS_DIR, "%s.json" % ym), "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("month") == ym:
            for k in ("days", "hours", "day_secs", "hour_secs"):
                data.setdefault(k, {})
            return data
    except Exception:
        pass
    return None


def iter_month_data(months, current_month=None, current_data=None):
    """Genera (ym, datos) de la lista de meses; usa el del sampler para el actual."""
    for ym in months:
        if current_month and ym == current_month and current_data is not None:
            yield ym, current_data
        else:
            data = load_month_stats(ym)
            if data:
                yield ym, data