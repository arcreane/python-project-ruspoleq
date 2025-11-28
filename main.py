"""
Radar Simulator - PySide6
Single-file example implementing:
- Radar display with sweeping green beam
- Planes represented by simple drawn icons
- Continuous simulation of plane movement (heading, speed, altitude)
- Selection of planes and controls to change heading/speed/altitude
- "Dévier" button to force a deviation in trajectory
- Collision proximity detection and simple gamification counters

Requirements:
- Python 3.12
- PySide6

Run:
python radar_simulator.py

This is a simplified but extensible prototype intended for the IPSA project.
"""

from math import sin, cos, radians, atan2, degrees, sqrt
import random
import sys
from PySide6.QtCore import (QPointF, QRectF, Qt, QTimer)
from PySide6.QtGui import (QBrush, QColor, QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import (QApplication, QGraphicsItem, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget, QPushButton, QFormLayout, QSpinBox,
                               QSlider, QListWidget, QListWidgetItem, QGroupBox,
                               QLineEdit, QMessageBox)

# ---- Constants ----
RADAR_RADIUS = 400
UPDATE_INTERVAL_MS = 40  # 25 fps
SWEEP_SPEED_DEG_PER_SEC = 90  # degrees per second
PROXIMITY_THRESHOLD = 30  # pixels for 'near collision'

# ---- Utility functions ----

def project_move(x, y, heading_deg, distance):
    # heading: 0 = up (north), 90 = right (east)
    angle = radians(-heading_deg + 90)
    nx = x + cos(angle) * distance
    ny = y + sin(angle) * distance
    return nx, ny


def distance(a: QPointF, b: QPointF):
    return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)

# ---- Plane graphical item ----

class PlaneItem(QGraphicsItem):
    def __init__(self, callsign: str, x: float, y: float,
                 heading: float, speed_kmh: float, altitude_m: float):
        super().__init__()
        self.callsign = callsign
        self.setPos(x, y)
        self.heading = heading  # degrees
        self.speed_kmh = speed_kmh
        self.altitude_m = altitude_m
        self.selected = False
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)

        # Derived attribute: pixels per second speed (approx)
        # assume radar scale: 1 pixel = 10 meters (arbitrary, tuneable)
        self.scale_m_per_pixel = 10

    def boundingRect(self) -> QRectF:
        return QRectF(-12, -12, 24, 24)

    def paint(self, painter: QPainter, option, widget=None):
        # Draw aircraft icon (triangle with tail)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.save()
        painter.rotate(-self.heading)  # rotate icon to match heading

        # body
        path = QPainterPath()
        path.moveTo(0, -10)
        path.lineTo(6, 8)
        path.lineTo(0, 4)
        path.lineTo(-6, 8)
        path.closeSubpath()

        painter.setBrush(QBrush(QColor(200, 200, 255)))
        painter.setPen(QPen(QColor(180, 180, 220), 1))
        painter.drawPath(path)

        # contrail / heading indicator
        painter.setPen(QPen(QColor(100, 255, 100), 1, Qt.DashLine))
        painter.drawLine(0, -10, 0, -30)

        painter.restore()

        # Draw callsign and altitude
        painter.setPen(QPen(Qt.white))
        painter.drawText(14, 0, f"{self.callsign} ({int(self.altitude_m)}m)")

        if self.isSelected():
            painter.setPen(QPen(Qt.yellow, 1))
            painter.drawEllipse(-16, -16, 32, 32)

    def advance(self, dt_sec):
        # speed_kmh -> m/s
        speed_m_s = (self.speed_kmh * 1000) / 3600
        # convert to pixels using scale
        distance_pixels = (speed_m_s * dt_sec) / self.scale_m_per_pixel
        x, y = self.x(), self.y()
        nx, ny = project_move(x, y, self.heading, distance_pixels)
        self.setPos(nx, ny)

    def change_heading(self, new_heading_deg):
        self.heading = new_heading_deg % 360
        self.update()

    def change_speed(self, new_speed_kmh):
        self.speed_kmh = max(50, new_speed_kmh)

    def change_altitude(self, new_alt_m):
        self.altitude_m = max(0, new_alt_m)

    def deviate_randomly(self):
        # small random offset to heading and speed
        self.heading = (self.heading + random.uniform(-60, 60)) % 360
        self.speed_kmh = max(80, self.speed_kmh + random.uniform(-120, 120))

# ---- Radar scene ----

class RadarScene(QGraphicsScene):
    def __init__(self, radius: int):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.radius = radius
        self.planes = []
        self.sweep_angle = 0.0  # degrees
        self.elapsed_acc = 0.0

        # background grid lines / circles
        self.setBackgroundBrush(QBrush(QColor(10, 30, 10)))

    def add_plane(self, plane: PlaneItem):
        self.planes.append(plane)
        self.addItem(plane)

    def remove_plane(self, plane: PlaneItem):
        if plane in self.planes:
            self.planes.remove(plane)
            self.removeItem(plane)

    def advance_simulation(self, dt_sec):
        # Move planes
        for p in list(self.planes):
            p.advance(dt_sec)

        # detect proximity
        events = []
        for i in range(len(self.planes)):
            for j in range(i + 1, len(self.planes)):
                d = distance(self.planes[i].pos(), self.planes[j].pos())
                if d < PROXIMITY_THRESHOLD:
                    events.append((self.planes[i], self.planes[j], d))
        return events

    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        center = QPointF(0, 0)

        # outer circle
        painter.setPen(QPen(QColor(0, 120, 0), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, self.radius, self.radius)

        # range rings
        painter.setPen(QPen(QColor(0, 80, 0), 1))
        for r in range(int(self.radius / 4), self.radius, int(self.radius / 4)):
            painter.drawEllipse(center, r, r)

        # radial lines
        painter.setPen(QPen(QColor(0, 60, 0), 1))
        for a in range(0, 360, 30):
            ang = radians(a)
            x = cos(ang) * self.radius
            y = sin(ang) * self.radius
            painter.drawLine(center, QPointF(x, y))

        # sweep effect: a translucent green pie sector
        gradient_color = QColor(80, 255, 80, 60)
        painter.setBrush(QBrush(gradient_color))
        painter.setPen(Qt.NoPen)
        # draw a sector spanning 8 degrees behind sweep angle
        span_deg = 12
        start_angle = -self.sweep_angle - span_deg
        path = QPainterPath()
        path.moveTo(center)
        path.arcTo(-self.radius, -self.radius, self.radius * 2, self.radius * 2,
                   start_angle, span_deg)
        path.closeSubpath()
        painter.drawPath(path)

        # center crosshair
        painter.setPen(QPen(QColor(60, 255, 60), 1))
        painter.drawLine(0, -10, 0, 10)
        painter.drawLine(-10, 0, 10, 0)

        painter.restore()

# ---- Main Window & Controls ----

class ControlPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Plane list
        self.plane_list = QListWidget()
        layout.addWidget(QLabel("Avions dans l'espace aérien"))
        layout.addWidget(self.plane_list)

        # Info / controls
        card = QGroupBox("Contrôles avion sélectionné")
        form = QFormLayout()
        card.setLayout(form)

        self.callsign_label = QLabel("Aucun")
        form.addRow("Sélection:", self.callsign_label)

        self.heading_spin = QSpinBox(); self.heading_spin.setRange(0, 359)
        form.addRow("Cap (°):", self.heading_spin)

        self.speed_spin = QSpinBox(); self.speed_spin.setRange(50, 900)
        form.addRow("Vitesse (km/h):", self.speed_spin)

        self.alt_spin = QSpinBox(); self.alt_spin.setRange(0, 15000)
        form.addRow("Altitude (m):", self.alt_spin)

        self.apply_btn = QPushButton("Appliquer")
        self.deviate_btn = QPushButton("Dévier")
        form.addRow(self.apply_btn, self.deviate_btn)

        layout.addWidget(card)

        # Gamification / stats
        stats = QGroupBox("Statistiques")
        v = QVBoxLayout(); stats.setLayout(v)
        self.score_label = QLabel("Score: 0")
        self.events_label = QLabel("Événements: 0")
        v.addWidget(self.score_label)
        v.addWidget(self.events_label)
        layout.addWidget(stats)

        layout.addStretch()

# ---- Main application ----

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simulateur de tour de contrôle - Radar")
        self.resize(1100, 850)

        self.scene = RadarScene(RADAR_RADIUS)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setFixedSize(RADAR_RADIUS * 2 + 4, RADAR_RADIUS * 2 + 4)

        self.controls = ControlPanel()

        h = QHBoxLayout()
        h.addWidget(self.view)
        h.addWidget(self.controls)
        self.setLayout(h)

        # Connect signals
        self.controls.plane_list.currentItemChanged.connect(self.on_plane_selected)
        self.controls.apply_btn.clicked.connect(self.apply_controls)
        self.controls.deviate_btn.clicked.connect(self.force_deviate)

        # Simulation state
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(UPDATE_INTERVAL_MS)

        self.last_dt = UPDATE_INTERVAL_MS / 1000.0
        self.score = 0
        self.events = 0

        # seed a few planes
        self.create_random_planes(6)

    def create_random_callsign(self):
        prefix = random.choice(["AF", "LH", "BA", "AFR", "EZY", "DLH"])
        num = random.randint(100, 9999)
        return f"{prefix}{num}"

    def create_random_planes(self, n=5):
        for _ in range(n):
            angle = random.uniform(0, 360)
            r = random.uniform(50, RADAR_RADIUS - 50)
            x = cos(radians(angle)) * r
            y = sin(radians(angle)) * r
            p = PlaneItem(self.create_random_callsign(), x, y,
                          heading=random.uniform(0, 360),
                          speed_kmh=random.uniform(200, 700),
                          altitude_m=random.uniform(1000, 9000))
            self.scene.add_plane(p)
            self.controls.plane_list.addItem(p.callsign)

    def tick(self):
        dt = self.last_dt
        # advance sweep
        self.scene.sweep_angle = (self.scene.sweep_angle + SWEEP_SPEED_DEG_PER_SEC * dt) % 360
        # advance simulation
        events = self.scene.advance_simulation(dt)
        if events:
            self.events += len(events)
            self.controls.events_label.setText(f"Événements: {self.events}")
            # Show warning for near collisions
            for a, b, d in events:
                print(f"Proximité: {a.callsign} - {b.callsign} (d={d:.1f})")
        # refresh view
        self.scene.update()

    def find_plane_by_callsign(self, callsign: str):
        for p in self.scene.planes:
            if p.callsign == callsign:
                return p
        return None

    def on_plane_selected(self, current: QListWidgetItem, previous: QListWidgetItem):
        if current is None:
            return
        cs = current.text()
        p = self.find_plane_by_callsign(cs)
        if p:
            # set selection in scene
            for other in self.scene.planes:
                other.setSelected(False)
            p.setSelected(True)
            self.controls.callsign_label.setText(p.callsign)
            self.controls.heading_spin.setValue(int(p.heading))
            self.controls.speed_spin.setValue(int(p.speed_kmh))
            self.controls.alt_spin.setValue(int(p.altitude_m))

    def apply_controls(self):
        cs = self.controls.callsign_label.text()
        if cs == "Aucun":
            QMessageBox.warning(self, "Aucun avion", "Sélectionnez d'abord un avion.")
            return
        p = self.find_plane_by_callsign(cs)
        if p:
            p.change_heading(self.controls.heading_spin.value())
            p.change_speed(self.controls.speed_spin.value())
            p.change_altitude(self.controls.alt_spin.value())
            self.score += 1
            self.controls.score_label.setText(f"Score: {self.score}")

    def force_deviate(self):
        cs = self.controls.callsign_label.text()
        if cs == "Aucun":
            QMessageBox.information(self, "Aucun avion", "Sélectionnez d'abord un avion.")
            return
        p = self.find_plane_by_callsign(cs)
        if p:
            p.deviate_randomly()
            self.controls.heading_spin.setValue(int(p.heading))
            self.controls.speed_spin.setValue(int(p.speed_kmh))

# ---- Run ----

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
