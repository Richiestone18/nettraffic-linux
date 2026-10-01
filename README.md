# NetTraffic para Linux (nettraffic-linux)

Monitor de tráfico de red con gráfica flotante y icono en bandeja para MATE/Linux.
Reimplementación libre desde cero, inspirada en el comportamiento observable de
NetTraffic de venea.net (no contiene código del original; su licencia prohíbe
decompilación).

## Qué hace

- Gráfica flotante en tiempo real: descarga (verde) / subida (rojo) / total.
- Tipos: área, columnas, líneas. Formas: rectangular o velocímetro (arco 270°).
- Barra de título con velocidades centradas (configurable) y fuente que
  auto-escala con el tamaño de la ventana.
- Redimensión: arrastra cualquier borde o esquina (14 px). Mover: arrastre en el centro.
- Transparencia ajustable 0-90 % (Ajustes → Gráfica), aplicada en vivo.
- Siempre encima, clic a través (X11 shape), ocultar bajo puntero,
  ocultar con otra ventana en pantalla completa.
- Ventana con marco del WM (con ajuste para que la barra nunca quede fuera de
  pantalla) o sin marco con barra de título propia.
- Arranque normal o iniciado oculto (solo bandeja), como el original.
- Icono en bandeja: estados TX/RX/inactivo; con cuota habilitada, barra superior
  = % del límite usado, barra inferior = transcurso del periodo.
- Cuota: límite con unidad (b/ib/B/iB × k/M/G/T), periodos día/semana/mes con
  día y hora de reinicio, ámbito del contador (todas las interfaces o una
  concreta) y ajuste manual del contador.
- Estadísticas: bloques Estado actual / Promedio / Pronóstico, bloque de Cuota
  (Usado, Límite, Restante, Periodo, Inicio, Final, Factor, Mínimo/Máximo),
  rango de fechas con unidad de tiempo Hora/Día/Mes/Año, gráfica de barras,
  tabla y exportación a CSV.
- Muestreo: /proc/net/dev — todas o interfaces seleccionadas, exclusión de lo,
  re-escaneo de disponibilidad configurable.
- Idiomas: español e inglés. Temas: claro/oscuro/sistema, con colores editables.

## Uso

- Clic derecho (gráfica o icono): Mostrar/Ocultar, Siempre encima, Clic a través,
  Ocultar bajo puntero, Gráfica en ventana con marco, Ajustes, Estadísticas,
  Acerca de, Salir.
- Clic izquierdo + arrastre: mover. Bordes/esquinas: redimensionar.

## Instalación

Paquete Debian: `nettraffic_1.2.1-1_all.deb` ( Releases de este repo o en este directorio)

    sudo apt install ./nettraffic_1.2.1-1_all.deb   # resuelve dependencias
    nettraffic &

Dependencias (declaradas en el paquete): python3, python3-gi, python3-cairo,
gir1.2-gtk-3.0, gir1.2-ayatanaappindicator3-0.1, gir1.2-pango-1.0, x11-utils.
El clic a través usa libX11 + libXext (presentes en cualquier Debian).

Desinstalar: `sudo apt remove nettraffic` (no toca ~/.config/nettraffic).

## Reconstruir el .deb

    cd ~/Documentos/nettraffic-linux
    cp nettraffic/*.py pkgroot/usr/share/nettraffic/
    rm -rf pkgroot/usr/share/nettraffic/__pycache__
    dpkg-deb --build pkgroot nettraffic_1.2.1-1_all.deb

## Archivos

- nettraffic/core.py     — núcleo: i18n, unidades, config, cuota, /proc/net/dev,
                           sampler, X11 shape (clic a través)
- nettraffic/chart.py    — ventana GTK+cairo, redimensión por bordes, opacidad X11
- nettraffic/tray.py     — icono AppIndicator dinámico con barras de cuota
- nettraffic/settings.py — Ajustes (navegación lateral: General/Gráfica/Cuota)
- nettraffic/stats.py    — Estadísticas (resumen, cuota, gráfica, tabla, CSV)
- nettraffic/app.py      — aplicación y menú
- debian/                — metadatos Debian
- pkgroot/               — árbol del .deb

## Notas del entorno (verificadas con MATE + Compiz)

- Compiz pisa posición/opacidad al mapear: la app re-aplica ambas tras show().
- La opacidad se fija por XChangeProperty(_NET_WM_WINDOW_OPACITY) — el
  set_opacity de GTK no llega al WM en este entorno.
- begin_resize_drag del WM no funciona en ventanas sin marco con Compiz:
  la redimensión es manual (resize+move por zona).
- **Clic a través**: XShapeCombineRectangles/XShapeCombineShape viven en
  **libXext.so.6**, NO en libX11. Cargarlas de libX11 lanza AttributeError y la
  opción se queda muda sin avisar (era el bug: nunca funcionó). Además no basta
  con la ventana principal: GtkDrawingArea tiene su propia ventana X hija que hay
  que recortar también, y hay que re-aplicarlo tras el repintado (XFixes hace que
  GTK reponga su forma de entrada).
- Para probar el clic a través NO sirve xdotool getmouselocation (usa
  XQueryPointer, que ignora las formas): hay que hacer clics reales contra una
  ventana colocada debajo.
- get_monitor_workarea() quiere el ÍNDICE del monitor; Gdk.Display.get_monitor_at_window()
  devuelve un objeto Gdk.Monitor (usar la variante de Gdk.Screen).
- En un Gtk.CheckMenuItem, set_active() emite "activate": el estado inicial debe
  fijarse ANTES de conectar el handler, o éste corre a media construcción del menú.
- El lanzador del .deb necesita PYTHONPATH=/usr/share (el PADRE del paquete), no
  /usr/share/nettraffic.

## Verificación

Batería de pruebas (muestreador, estadísticas, UI, clic-a-través, arranque
oculto) corrida contra un HOME aislado para no tocar la configuración real:
56 comprobaciones, 0 fallas.

## Licencia

MIT (código propio).