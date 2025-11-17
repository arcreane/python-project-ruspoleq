# main.py
from __future__ import annotations
import sys
import math
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

# -----------------------------
# MODELE : Aircraft (dataclass)
# -----------------------------
def random_color() -> QtGui.QColor:
    return QtGui.QColor.fromHsv(random.randint(0, 359), 200, 230)

@dataclass
class Aircraft:
    callsign: str
    x: float
    y: float
    altitude: float  # meters
    speed: float     # km/h
    heading: float   # degrees
    fuel: float      # percent 0-100

    status: str = "en route"   # en route, holding, landing, on_ground
    selected: bool = False
    last_update: float = field(default_factory=time.time)
    color: QtGui.QColor = field(default_factory=random_color)

    # vertical speed when landing (m/s) - increased for faster descent
    landing_descent_rate_mps: float = 6.0

    def update(self, dt_seconds: float):
        if self.status == "on_ground":
            return

        # fuel consumption slower but present
        self.fuel = max(0.0, self.fuel - 0.005 * dt_seconds)

        # if critical fuel -> start landing
        if self.fuel <= 1.0 and self.status != "on_ground":
            self.status = "landing"

        # landing: reduce speed and descend
        if self.status == "landing":
            # reduce speed (km/h)
            self.speed = max(80.0, self.speed - 60.0 * dt_seconds / 3600.0)
            # descend faster (m/s)
            self.altitude = max(0.0, self.altitude - self.landing_descent_rate_mps * dt_seconds)
            if self.altitude <= 0.5:
                self.altitude = 0.0
                self.status = "on_ground"
                self.speed = 0.0

        # simple holding: slowly turn
        if self.status == "holding":
            self.heading = (self.heading + 10.0 * dt_seconds) % 360.0

        # movement: convert speed+heading to dx/dy
        rad = math.radians(90.0 - self.heading)
        km_per_s = self.speed / 3600.0
        dx = km_per_s * math.cos(rad) * dt_seconds
        dy = km_per_s * math.sin(rad) * dt_seconds
        self.x += dx
        self.y += dy

        self.last_update = time.time()

    def climb(self, meters: float):
        if self.status != "on_ground":
            self.altitude += meters

    def descend(self, meters: float):
        if self.status != "on_ground":
            self.altitude = max(0.0, self.altitude - meters)
            if self.altitude == 0.0:
                self.status = "on_ground"

    def set_heading(self, heading: float):
        self.heading = heading % 360.0

    def set_holding(self):
        if self.status != "on_ground":
            self.status = "holding"

    def request_landing(self):
        if self.status != "on_ground":
            self.status = "landing"

    def go_around(self):
        # remise de gaz: climb and return to en route
        self.altitude += 800.0
        self.speed = max(self.speed, 300.0)
        self.status = "en route"
        self.heading = (self.heading + 30.0) % 360.0

# -----------------------------
# SIMULATION
# -----------------------------
class Simulation(QtCore.QObject):
    aircraft_added = QtCore.Signal(Aircraft)
    aircraft_removed = QtCore.Signal(str)
    aircraft_updated = QtCore.Signal(Aircraft)
    collision_detected = QtCore.Signal(Aircraft, Aircraft)
    score_updated = QtCore.Signal(int)
    event_logged = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.aircraft: List[Aircraft] = []
        self.last_time = time.time()
        self.timer = QtCore.QTimer()
        self.timer.setInterval(200)  # simulation tick 200 ms
        self.timer.timeout.connect(self.tick)

        # spawn slower: 15s
        self.spawn_timer = QtCore.QTimer()
        self.spawn_timer.setInterval(15000)
        self.spawn_timer.timeout.connect(self.spawn_aircraft)

        # events slower: 20s
        self.event_timer = QtCore.QTimer()
        self.event_timer.setInterval(20000)
        self.event_timer.timeout.connect(self.random_event)

        self.score = 0
        self._colors = [QtGui.QColor(c) for c in ['#e63946','#457b9d','#2a9d8f','#f4a261','#8d99ae','#06d6a0','#ffb300']]

    def start(self):
        self.last_time = time.time()
        self.timer.start()
        self.spawn_timer.start()
        self.event_timer.start()

    def stop(self):
        self.timer.stop()
        self.spawn_timer.stop()
        self.event_timer.stop()

    def tick(self):
        now = time.time()
        dt = now - self.last_time
        self.last_time = now

        # update aircraft
        for ac in list(self.aircraft):
            ac.update(dt)
            if ac.fuel <= 1.0 and ac.status != "on_ground":
                ac.status = "landing"
            self.aircraft_updated.emit(ac)

        # collision detection: adapted for lower altitudes
        n = len(self.aircraft)
        for i in range(n):
            for j in range(i+1, n):
                a = self.aircraft[i]
                b = self.aircraft[j]
                dx = a.x - b.x
                dy = a.y - b.y
                dist = math.hypot(dx, dy)
                if dist < 0.08 and abs(a.altitude - b.altitude) < 50.0 and a.status != 'on_ground' and b.status != 'on_ground':
                    # collision
                    self.collision_detected.emit(a, b)
                    self.log_event(f"COLLISION: {a.callsign} & {b.callsign}")
                    self._safe_remove(a)
                    self._safe_remove(b)
                elif dist < 0.35 and abs(a.altitude - b.altitude) < 150.0:
                    # near miss
                    self.log_event(f"Near-miss détecté: {a.callsign} / {b.callsign}")
                    a.heading = (a.heading + 15.0) % 360.0
                    b.heading = (b.heading - 15.0) % 360.0

        # landed aircraft scoring and removal
        for ac in list(self.aircraft):
            if ac.status == 'on_ground':
                self.score += 1
                self.score_updated.emit(self.score)
                self.log_event(f"{ac.callsign} a atterri (+1).")
                self._safe_remove(ac)

    def _safe_remove(self, ac: Aircraft):
        try:
            self.aircraft.remove(ac)
        except ValueError:
            pass
        self.aircraft_removed.emit(ac.callsign)

    def spawn_aircraft(self):
        # spawn at edges, altitude limited to <= 1000m
        side = random.choice(['N','S','E','W'])
        if side == 'N':
            x = random.uniform(-10, 10); y = -12.0; heading = random.uniform(160,200)
        elif side == 'S':
            x = random.uniform(-10, 10); y = 12.0; heading = random.uniform(-20,20)
        elif side == 'E':
            x = 12.0; y = random.uniform(-10,10); heading = random.uniform(250,290)
        else:
            x = -12.0; y = random.uniform(-10,10); heading = random.uniform(70,110)

        callsign = random.choice(['AF','BA','LH','DL','SU','AZ']) + str(random.randint(100,9999))
        altitude = random.uniform(400, 1000)   # <=1000m
        speed = random.uniform(250, 450)       # somewhat lower speeds
        fuel = random.uniform(30, 100)
        color = random.choice(self._colors)
        ac = Aircraft(callsign=callsign, x=x, y=y, altitude=altitude, speed=speed, heading=heading, fuel=fuel, color=color)
        self.aircraft.append(ac)
        self.aircraft_added.emit(ac)
        self.log_event(f"Spawn: {ac.callsign} alt {int(ac.altitude)}m")

    def find(self, callsign: str) -> Optional[Aircraft]:
        for ac in self.aircraft:
            if ac.callsign == callsign:
                return ac
        return None

    def log_event(self, text: str):
        ts = time.strftime("%H:%M:%S", time.localtime())
        self.event_logged.emit(f"[{ts}] {text}")

    def random_event(self):
        if not self.aircraft:
            return
        r = random.random()
        if r < 0.3:
            # panne moteur
            ac = random.choice(self.aircraft)
            ac.speed = max(80.0, ac.speed * 0.5)
            ac.fuel = max(0.5, ac.fuel * 0.6)
            ac.request_landing()
            self.log_event(f"Panne moteur: {ac.callsign} -> atterrissage d'urgence")
        elif r < 0.6:
            # météo : mise en holding plusieurs avions
            chosen = random.sample(self.aircraft, min(3, len(self.aircraft)))
            for ac in chosen:
                ac.set_holding()
            self.log_event("Urgence météo: plusieurs avions mis en attente")
        elif r < 0.8:
            # remise de gaz
            landers = [a for a in self.aircraft if a.status == 'landing']
            if landers:
                ac = random.choice(landers)
                ac.go_around()
                self.log_event(f"Remise de gaz: {ac.callsign}")
        else:
            # risque de collision: nudge two planes closer
            if len(self.aircraft) >= 2:
                a, b = random.sample(self.aircraft, 2)
                midx = (a.x + b.x) / 2.0
                midy = (a.y + b.y) / 2.0
                a.x = midx + 0.03
                a.y = midy + 0.03
                b.x = midx - 0.03
                b.y = midy - 0.03
                self.log_event(f"Situation: risque de collision entre {a.callsign} et {b.callsign}")

# -----------------------------
# UI: AircraftItem + Explosion
# -----------------------------
class AircraftItem(QtWidgets.QGraphicsItem):
    def __init__(self, ac: Aircraft, km_to_scene: float = 1000.0, size: float = 14.0):
        super().__init__()
        self.ac = ac
        self.km_to_scene = km_to_scene
        self.size = size
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(5)

        # optional icon
        try:
            pix = QtGui.QPixmap("plane_icon.png")
            if pix and not pix.isNull():
                self.icon = pix.scaled(int(size*2), int(size*2), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            else:
                self.icon = None
        except Exception:
            self.icon = None

    def boundingRect(self):
        s = self.size * 2
        return QtCore.QRectF(-s, -s, s*2 + 60, s*2 + 6)

    def paint(self, painter: QtGui.QPainter, option, widget=None):
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # rotate according to heading
        painter.rotate(self.ac.heading)

        # draw icon or vector plane
        if self.icon:
            painter.drawPixmap(-self.icon.width()/2, -self.icon.height()/2, self.icon)
        else:
            pen = QtGui.QPen(QtGui.QColor('black'))
            pen.setWidth(1)
            painter.setPen(pen)
            brush = QtGui.QBrush(self.ac.color)
            painter.setBrush(brush)
            path = QtGui.QPainterPath()
            s = self.size
            path.moveTo(0, -s)
            path.lineTo(s*0.8, s)
            path.lineTo(0, s*0.2)
            path.lineTo(-s*0.8, s)
            path.closeSubpath()
            painter.drawPath(path)
            painter.setBrush(QtGui.QBrush(QtGui.QColor('white')))
            painter.drawEllipse(-2, -s*0.6, 4, 4)

        painter.restore()

        # label right
        txt = f"{self.ac.callsign} {int(self.ac.altitude)}m"
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        metrics = QtGui.QFontMetrics(font)
        w = metrics.horizontalAdvance(txt) + 8
        h = metrics.height() + 4
        rect = QtCore.QRectF(12, -h/2, w, h)
        painter.setPen(QtGui.QPen(QtGui.QColor(0,0,0,180)))
        painter.setBrush(QtGui.QBrush(QtGui.QColor(0,0,0,120)))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QtGui.QPen(QtGui.QColor('white')))
        painter.drawText(rect, QtCore.Qt.AlignCenter, txt)

    def hoverEnterEvent(self, event):
        QtWidgets.QToolTip.showText(event.screenPos().toPoint(),
                                    f"{self.ac.callsign}\nAlt: {int(self.ac.altitude)} m\nV: {int(self.ac.speed)} km/h\nFuel: {int(self.ac.fuel)} %\nStatus: {self.ac.status}")
        super().hoverEnterEvent(event)

class ExplosionItem(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, center: QtCore.QPointF):
        super().__init__(-20, -20, 40, 40)
        self.setPos(center)
        self.setBrush(QtGui.QBrush(QtGui.QColor(255, 120, 0, 220)))
        self.setPen(QtGui.QPen(QtGui.QColor('red')))
        self.setZValue(100)
        self.anim = QtCore.QVariantAnimation()
        self.anim.setDuration(900)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(6.0)
        self.anim.valueChanged.connect(self._on_value)
        self.anim.finished.connect(self._on_finished)
        self.anim.start()

    def _on_value(self, v):
        self.setScale(v)
        alpha = max(0, int(220 * (1.0 - (v-1.0)/5.0)))
        c = self.brush().color()
        c.setAlpha(alpha)
        self.setBrush(QtGui.QBrush(c))

    def _on_finished(self):
        scene = self.scene()
        if scene:
            scene.removeItem(self)
        self.deleteLater()

# -----------------------------
# MAIN WINDOW
# -----------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simulateur de Tour de Contrôle")
        self.resize(1400, 900)

        # global style
        self.setStyleSheet("""
            QWidget { background-color: #071826; color: #e6eef2; }
            QFrame#panel { background-color: #071826; border-radius: 8px; border: 1px solid #13333a; }
            QLabel.title { font-size: 20px; font-weight: bold; color: #e6eef2; }
            QPushButton { background-color: #1e88e5; color: white; border-radius: 8px; padding: 8px; font-size: 14px; }
            QPushButton:hover { background-color: #1565c0; }
            QPushButton#danger { background-color: #e63946; }
            QListWidget { background-color: #02181f; border: 1px solid #11333a; color: white; }
            QSpinBox { background-color: #02181f; color: white; border: 1px solid #11333a; border-radius: 4px; padding: 2px; }
        """)

        self.sim = Simulation()

        self.stack = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stack)
        self._build_welcome()
        self._build_game()

        # connect signals
        self.sim.aircraft_added.connect(self.on_aircraft_added)
        self.sim.aircraft_removed.connect(self.on_aircraft_removed)
        self.sim.aircraft_updated.connect(self.on_aircraft_updated)
        self.sim.collision_detected.connect(self.on_collision)
        self.sim.score_updated.connect(self.on_score_updated)
        self.sim.event_logged.connect(self.on_event_logged)

        self.item_map: dict[str, AircraftItem] = {}

        # pre-spawn a few
        for _ in range(4):
            self.sim.spawn_aircraft()

        # UI timer
        self.ui_timer = QtCore.QTimer()
        self.ui_timer.setInterval(200)
        self.ui_timer.timeout.connect(self.refresh_positions)
        self.ui_timer.start()

    # ---- Welcome ----
    def _build_welcome(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0,0,0,0)

        bg = QtWidgets.QLabel()
        try:
            pix = QtGui.QPixmap("menu_background.jpg")
            if not pix.isNull():
                pix = pix.scaled(1400,900, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
                bg.setPixmap(pix)
            else:
                raise Exception("no pix")
        except Exception:
            bg.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #021826, stop:1 #001219);")

        overlay = QtWidgets.QWidget(bg)
        overlay.setGeometry(0,0,1400,900)
        v = QtWidgets.QVBoxLayout(overlay)
        v.setAlignment(QtCore.Qt.AlignCenter)

        title = QtWidgets.QLabel("SIMULATEUR DE TOUR DE CONTRÔLE")
        title.setObjectName("title")
        title.setProperty("class", "title")
        title.setStyleSheet("font-size:32px; font-weight:bold; color: #e6eef2;")
        subtitle = QtWidgets.QLabel("Gère les arrivées, urgences et évite les collisions")
        subtitle.setStyleSheet("font-size:14px; color: #cfe8ef;")
        start_btn = QtWidgets.QPushButton("Lancer la partie")
        start_btn.setFixedSize(260,64)
        start_btn.clicked.connect(self.start_game)

        v.addWidget(title)
        v.addSpacing(8)
        v.addWidget(subtitle)
        v.addSpacing(16)
        v.addWidget(start_btn)

        layout.addWidget(bg)
        self.stack.addWidget(page)

    def start_game(self):
        self.stack.setCurrentIndex(1)
        self.sim.start()
        self.log("[SYSTEM] Partie démarrée")

    # ---- Game ----
    def _build_game(self):
        page = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(page)

        # left panel
        left = QtWidgets.QFrame()
        left.setObjectName("panel")
        left.setFixedWidth(320)
        lv = QtWidgets.QVBoxLayout(left)
        self.score_label = QtWidgets.QLabel("Score: 0")
        self.score_label.setStyleSheet("font-size:16px; font-weight:bold; color: #e6eef2;")
        lv.addWidget(self.score_label)
        lv.addWidget(QtWidgets.QLabel("Journal d'événements:"))
        self.event_log = QtWidgets.QListWidget()
        self.event_log.setMinimumHeight(240)
        lv.addWidget(self.event_log)
        lv.addWidget(QtWidgets.QLabel("Avions:"))
        self.aircraft_list = QtWidgets.QListWidget()
        lv.addWidget(self.aircraft_list)
        lv.addStretch()
        h.addWidget(left)

        # center: radar view
        self.scene = QtWidgets.QGraphicsScene(-15000, -15000, 30000, 30000)
        self.view = QtWidgets.QGraphicsView(self.scene)
        self.view.setRenderHint(QtGui.QPainter.Antialiasing)
        self.view.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.km_to_scene = 1000.0

        # load background but less zoomed: scale big and center
        try:
            pix = QtGui.QPixmap("background_airport.jpg")
            if pix and not pix.isNull():
                # dezoom: scale very large to cover scene without pixel zoom artifact
                big = pix.scaled(16000, 16000, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                bg_item = QtWidgets.QGraphicsPixmapItem(big)
                # center it more naturally (less zoom)
                bg_item.setOffset(-8000, -8000)
                bg_item.setZValue(-50)
                self.scene.addItem(bg_item)
            else:
                raise Exception("no pix")
        except Exception:
            # fallback bg color
            self.scene.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#00141c")))

        # runway (graphical)
        runway = QtWidgets.QGraphicsRectItem(-600, -120, 1200, 240)
        runway.setBrush(QtGui.QBrush(QtGui.QColor("#2b2d2f")))
        runway.setPen(QtGui.QPen(QtGui.QColor('#9fb4bf')))
        runway.setZValue(-5)
        self.scene.addItem(runway)

        h.addWidget(self.view, stretch=1)

        # right controls
        right = QtWidgets.QFrame()
        right.setObjectName("panel")
        right.setFixedWidth(320)
        rv = QtWidgets.QVBoxLayout(right)
        self.selected_label = QtWidgets.QLabel("Aucun avion sélectionné")
        rv.addWidget(self.selected_label)

        self.btn_climb = QtWidgets.QPushButton("Monter +1000 m")
        self.btn_descend = QtWidgets.QPushButton("Descendre -1000 m")
        self.btn_hold = QtWidgets.QPushButton("Mettre en attente")
        self.btn_land = QtWidgets.QPushButton("Autoriser atterrissage")
        self.btn_land.setStyleSheet("background-color:#06d6a0; color:black; font-weight:bold;")
        rv.addWidget(self.btn_climb)
        rv.addWidget(self.btn_descend)
        rv.addWidget(self.btn_hold)
        rv.addWidget(self.btn_land)

        rv.addSpacing(6)
        rv.addWidget(QtWidgets.QLabel("Changer cap (°):"))
        self.input_heading = QtWidgets.QSpinBox()
        self.input_heading.setRange(0,359)
        rv.addWidget(self.input_heading)
        self.btn_set_heading = QtWidgets.QPushButton("Appliquer cap")
        rv.addWidget(self.btn_set_heading)

        rv.addSpacing(8)
        self.btn_land_all = QtWidgets.QPushButton("Autoriser tous à atterrir")
        self.btn_land_all.setStyleSheet("background-color:#ffb703; color:black; font-weight:bold;")
        rv.addWidget(self.btn_land_all)
        rv.addStretch()
        h.addWidget(right)

        # connect
        self.aircraft_list.itemSelectionChanged.connect(self.on_list_selection_changed)
        self.btn_climb.clicked.connect(lambda: self._apply_to_selected('climb'))
        self.btn_descend.clicked.connect(lambda: self._apply_to_selected('descend'))
        self.btn_hold.clicked.connect(lambda: self._apply_to_selected('hold'))
        self.btn_land.clicked.connect(lambda: self._apply_to_selected('land'))
        self.btn_set_heading.clicked.connect(lambda: self._apply_to_selected('heading'))
        self.btn_land_all.clicked.connect(self.land_all)

        self.stack.addWidget(page)

    # -----------------------
    # Simulation slots
    # -----------------------
    def on_aircraft_added(self, ac: Aircraft):
        item = AircraftItem(ac, km_to_scene=self.km_to_scene, size=16)
        item.setPos(ac.x * self.km_to_scene, ac.y * self.km_to_scene)
        self.scene.addItem(item)
        self.item_map[ac.callsign] = item
        self.aircraft_list.addItem(ac.callsign)
        self.log(f"{ac.callsign} entré en zone (alt {int(ac.altitude)}m)")

    def on_aircraft_removed(self, callsign: str):
        it = self.item_map.get(callsign)
        if it:
            try:
                self.scene.removeItem(it)
            except Exception:
                pass
            del self.item_map[callsign]
        # remove from list widget
        for i in range(self.aircraft_list.count()):
            if self.aircraft_list.item(i).text() == callsign:
                self.aircraft_list.takeItem(i)
                break

    def on_aircraft_updated(self, ac: Aircraft):
        it = self.item_map.get(ac.callsign)
        if it:
            it.setPos(ac.x * self.km_to_scene, ac.y * self.km_to_scene)
            it.update()

    def on_collision(self, a: Aircraft, b: Aircraft):
        p1 = QtCore.QPointF(a.x * self.km_to_scene, a.y * self.km_to_scene)
        p2 = QtCore.QPointF(b.x * self.km_to_scene, b.y * self.km_to_scene)
        center = QtCore.QPointF((p1.x()+p2.x())/2.0, (p1.y()+p2.y())/2.0)
        explosion = ExplosionItem(center)
        self.scene.addItem(explosion)
        self.log(f"COLLISION: {a.callsign} & {b.callsign}")
        QtWidgets.QMessageBox.critical(self, "Collision !", f"Collision entre {a.callsign} et {b.callsign} !")

    def on_score_updated(self, score: int):
        self.score_label.setText(f"Score: {score}")

    def on_event_logged(self, text: str):
        self.event_log.insertItem(0, text)

    # -----------------------
    # UI actions
    # -----------------------
    def on_list_selection_changed(self):
        sels = self.aircraft_list.selectedItems()
        for ac in self.sim.aircraft:
            ac.selected = False
        for it in self.scene.selectedItems():
            it.setSelected(False)
        if not sels:
            self.selected_label.setText("Aucun avion sélectionné")
            return
        callsign = sels[0].text()
        ac = self.sim.find(callsign)
        if not ac:
            return
        ac.selected = True
        self.selected_label.setText(f"Sélectionné: {ac.callsign} | Alt: {int(ac.altitude)} m | V: {int(ac.speed)}")
        item = self.item_map.get(callsign)
        if item:
            item.setSelected(True)
            self.view.centerOn(QtCore.QPointF(ac.x * self.km_to_scene, ac.y * self.km_to_scene))

    def _apply_to_selected(self, action: str):
        sels = self.aircraft_list.selectedItems()
        if not sels:
            QtWidgets.QMessageBox.information(self, "Info", "Sélectionnez d'abord un avion.")
            return
        callsign = sels[0].text()
        ac = self.sim.find(callsign)
        if not ac:
            return
        if action == 'climb':
            ac.climb(1000.0)
            self.log(f"{ac.callsign} : montée +1000 m")
        elif action == 'descend':
            ac.descend(1000.0)
            self.log(f"{ac.callsign} : descente -1000 m")
        elif action == 'hold':
            ac.set_holding()
            self.log(f"{ac.callsign} : mise en attente")
        elif action == 'land':
            ac.request_landing()
            # increase descent rate for responsive landing
            ac.landing_descent_rate_mps = 8.0
            self.log(f"{ac.callsign} : autorisé à atterrir (descente active)")
        elif action == 'heading':
            ac.set_heading(self.input_heading.value())
            self.log(f"{ac.callsign} : cap {self.input_heading.value()}° appliqué")
        self.selected_label.setText(f"Sélectionné: {ac.callsign} | Alt: {int(ac.altitude)} m | V: {int(ac.speed)}")

    def land_all(self):
        for ac in list(self.sim.aircraft):
            ac.request_landing()
            ac.landing_descent_rate_mps = 6.0
        self.log("Autorisation d'atterrissage donnée à tous")

    def refresh_positions(self):
        for ac in list(self.sim.aircraft):
            it = self.item_map.get(ac.callsign)
            if it:
                it.setPos(ac.x * self.km_to_scene, ac.y * self.km_to_scene)
                it.update()

    def log(self, text: str):
        ts = time.strftime("%H:%M:%S", time.localtime())
        self.event_log.insertItem(0, f"[{ts}] {text}")

# -----------------------------
# Lancement
# -----------------------------
def main():
    app = QtWidgets.QApplication([])
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
