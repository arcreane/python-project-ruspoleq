from math import sin, cos, radians, sqrt
import random
import sys
from PySide6.QtCore import (QPointF, QRectF, Qt, QTimer, QPropertyAnimation,
                            QEasingCurve, Property, QAbstractAnimation)
from PySide6.QtGui import (QBrush, QColor, QPainter, QPainterPath, QPen,
                           QLinearGradient, QRadialGradient, QFont)
from PySide6.QtWidgets import (QApplication, QGraphicsItem, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget, QPushButton, QFormLayout, QSpinBox,
                               QListWidget, QListWidgetItem, QGroupBox, QMessageBox,
                               QGraphicsDropShadowEffect)

# Constantes
RADAR_RADIUS = 400
UPDATE_INTERVAL_MS = 40
SWEEP_SPEED_DEG_PER_SEC = 90
PROXIMITY_THRESHOLD = 30
LANDING_ZONE_SIZE = 80


# Fonctions utilitaires
def project_move(x, y, heading_deg, distance):
    angle = radians(-heading_deg + 90)
    nx = x + cos(angle) * distance
    ny = y + sin(angle) * distance
    return nx, ny


def distance(a: QPointF, b: QPointF):
    return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)


# ---- Zone d'atterrissage ----
class LandingZoneItem(QGraphicsItem):
    def __init__(self):
        super().__init__()
        self.setPos(-LANDING_ZONE_SIZE / 2, -LANDING_ZONE_SIZE / 2)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, LANDING_ZONE_SIZE, LANDING_ZONE_SIZE)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        # Piste d'atterrissage avec dégradé
        gradient = QLinearGradient(0, 0, LANDING_ZONE_SIZE, LANDING_ZONE_SIZE)
        gradient.setColorAt(0, QColor(100, 100, 120, 180))
        gradient.setColorAt(1, QColor(60, 60, 80, 180))

        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(255, 200, 0), 2))
        painter.drawRect(0, 0, LANDING_ZONE_SIZE, LANDING_ZONE_SIZE)

        # Lignes de piste
        painter.setPen(QPen(QColor(255, 255, 255, 200), 2, Qt.DashLine))
        painter.drawLine(LANDING_ZONE_SIZE / 2, 0, LANDING_ZONE_SIZE / 2, LANDING_ZONE_SIZE)

        # Texte
        painter.setPen(QPen(Qt.white))
        font = QFont("Arial", 10, QFont.Bold)
        painter.setFont(font)
        painter.drawText(self.boundingRect(), Qt.AlignCenter, "PISTE")


# ---- Avion amélioré avec animations ----
class PlaneItem(QGraphicsItem):
    def __init__(self, callsign: str, x: float, y: float, heading: float,
                 speed_kmh: float, altitude_m: float, fuel_percent: float = 100):
        super().__init__()
        self.callsign = callsign
        self.setPos(x, y)
        self.heading = heading
        self.speed_kmh = speed_kmh
        self.altitude_m = altitude_m
        self.fuel_percent = fuel_percent
        self.selected = False
        self.warning = False
        self.pulse_phase = 0
        self.scale_m_per_pixel = 10

        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)

        # Effet d'ombre
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 255, 0, 100))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)

    def boundingRect(self) -> QRectF:
        return QRectF(-25, -25, 50, 50)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.save()

        # Rotation selon le cap
        painter.rotate(-self.heading)

        # Corps de l'avion avec dégradé
        path = QPainterPath()
        path.moveTo(0, -12)
        path.lineTo(8, 10)
        path.lineTo(0, 6)
        path.lineTo(-8, 10)
        path.closeSubpath()

        # Couleur selon l'état
        if self.warning:
            self.pulse_phase = (self.pulse_phase + 0.2) % 6.28
            intensity = int(155 + 100 * abs(sin(self.pulse_phase)))
            color = QColor(intensity, 50, 50)
        elif self.selected:
            color = QColor(255, 200, 50)
        else:
            # Couleur selon altitude
            alt_ratio = min(self.altitude_m / 10000, 1.0)
            color = QColor(int(100 + 155 * alt_ratio),
                           int(150 + 105 * alt_ratio), 255)

        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(130), 2))
        painter.drawPath(path)

        # Trainée de condensation
        trail_color = QColor(150, 200, 255, 100)
        painter.setPen(QPen(trail_color, 2, Qt.DashLine))
        painter.drawLine(0, -12, 0, -35)

        painter.restore()

        # Informations textuelles
        painter.setPen(QPen(Qt.white))
        font = QFont("Consolas", 9, QFont.Bold)
        painter.setFont(font)

        # Callsign et altitude
        text = f"{self.callsign}\n{int(self.altitude_m)}m"
        if self.fuel_percent < 30:
            text += f"\n⚠ {int(self.fuel_percent)}%"
            painter.setPen(QPen(QColor(255, 100, 100)))

        painter.drawText(18, -5, text)

        # Cercle de sélection animé
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 200, 50), 2, Qt.DashLine))
            painter.drawEllipse(-20, -20, 40, 40)

    def advance(self, dt_sec):
        speed_m_s = (self.speed_kmh * 1000) / 3600
        distance_pixels = (speed_m_s * dt_sec) / self.scale_m_per_pixel

        x, y = self.x(), self.y()
        nx, ny = project_move(x, y, self.heading, distance_pixels)
        self.setPos(nx, ny)

        # Consommation de carburant
        self.fuel_percent = max(0, self.fuel_percent - 0.01 * dt_sec)

        self.update()

    def change_heading(self, new_heading_deg):
        self.heading = new_heading_deg % 360
        self.update()

    def change_speed(self, new_speed_kmh):
        self.speed_kmh = max(50, min(900, new_speed_kmh))

    def change_altitude(self, new_alt_m):
        self.altitude_m = max(0, min(15000, new_alt_m))

    def deviate_randomly(self):
        self.heading = (self.heading + random.uniform(-60, 60)) % 360
        self.speed_kmh = max(80, min(800, self.speed_kmh + random.uniform(-120, 120)))


# ---- Scene radar améliorée ----
class RadarScene(QGraphicsScene):
    def __init__(self, radius: int):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.radius = radius
        self.planes = []
        self.sweep_angle = 0.0
        self.landing_zone = LandingZoneItem()
        self.addItem(self.landing_zone)
        self.setBackgroundBrush(QBrush(QColor(5, 15, 25)))

    def add_plane(self, plane: PlaneItem):
        self.planes.append(plane)
        self.addItem(plane)

    def remove_plane(self, plane: PlaneItem):
        if plane in self.planes:
            self.planes.remove(plane)
            self.removeItem(plane)

    def advance_simulation(self, dt_sec):
        events = []
        planes_to_remove = []

        for p in list(self.planes):
            p.advance(dt_sec)
            p.warning = False

            # Vérifier si dans zone d'atterrissage
            if abs(p.x()) < LANDING_ZONE_SIZE / 2 and abs(p.y()) < LANDING_ZONE_SIZE / 2:
                if p.altitude_m < 500 and p.speed_kmh < 300:
                    planes_to_remove.append(p)
                    events.append(('landing', p))

            # Vérifier carburant
            if p.fuel_percent < 20:
                events.append(('fuel_low', p))

        # Détection de proximité
        for i in range(len(self.planes)):
            for j in range(i + 1, len(self.planes)):
                d = distance(self.planes[i].pos(), self.planes[j].pos())
                if d < PROXIMITY_THRESHOLD:
                    self.planes[i].warning = True
                    self.planes[j].warning = True
                    events.append(('proximity', self.planes[i], self.planes[j], d))

        # Retirer avions atterris
        for p in planes_to_remove:
            self.remove_plane(p)

        return events

    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        center = QPointF(0, 0)

        # Cercle extérieur avec dégradé
        gradient = QRadialGradient(center, self.radius)
        gradient.setColorAt(0, QColor(5, 15, 25))
        gradient.setColorAt(0.8, QColor(5, 15, 25))
        gradient.setColorAt(1, QColor(0, 80, 120))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(0, 150, 200), 3))
        painter.drawEllipse(center, self.radius, self.radius)

        # Cercles concentriques
        painter.setPen(QPen(QColor(0, 100, 150, 80), 1))
        for r in range(int(self.radius / 4), self.radius, int(self.radius / 4)):
            painter.drawEllipse(center, r, r)
            # Labels de distance
            painter.setPen(QPen(QColor(100, 200, 255, 150)))
            font = QFont("Arial", 8)
            painter.setFont(font)
            painter.drawText(QPointF(5, -r + 5), f"{r}px")
            painter.setPen(QPen(QColor(0, 100, 150, 80), 1))

        # Lignes radiales
        painter.setPen(QPen(QColor(0, 80, 120, 60), 1))
        for a in range(0, 360, 30):
            ang = radians(a)
            x = cos(ang) * self.radius
            y = sin(ang) * self.radius
            painter.drawLine(center, QPointF(x, y))

            # Labels d'angle
            if a % 90 == 0:
                painter.setPen(QPen(QColor(100, 200, 255)))
                font = QFont("Arial", 10, QFont.Bold)
                painter.setFont(font)
                tx = cos(ang) * (self.radius - 30)
                ty = sin(ang) * (self.radius - 30)
                directions = {0: "N", 90: "E", 180: "S", 270: "O"}
                painter.drawText(QPointF(tx - 10, ty + 5), directions.get(a, ""))
                painter.setPen(QPen(QColor(0, 80, 120, 60), 1))

        # Effet de balayage radar amélioré
        sweep_gradient = QRadialGradient(center, self.radius)
        sweep_gradient.setColorAt(0, QColor(100, 255, 100, 80))
        sweep_gradient.setColorAt(0.5, QColor(50, 200, 50, 40))
        sweep_gradient.setColorAt(1, QColor(0, 150, 0, 0))

        painter.setBrush(QBrush(sweep_gradient))
        painter.setPen(Qt.NoPen)

        span_deg = 15
        start_angle = -self.sweep_angle - span_deg
        path = QPainterPath()
        path.moveTo(center)
        path.arcTo(-self.radius, -self.radius, self.radius * 2,
                   self.radius * 2, start_angle, span_deg)
        path.closeSubpath()
        painter.drawPath(path)

        # Croix centrale
        painter.setPen(QPen(QColor(100, 255, 100), 2))
        painter.drawLine(-15, 0, 15, 0)
        painter.drawLine(0, -15, 0, 15)
        painter.drawEllipse(center, 5, 5)

        painter.restore()


# ---- Panneau de contrôle stylisé ----
class ControlPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.apply_styles()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)
        self.setLayout(layout)

        # Titre
        title = QLabel("🛫 CONTRÔLE AÉRIEN")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #00ff88;
                padding: 10px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a3a4a, stop:1 #0d1f2a);
                border-radius: 8px;
                border: 2px solid #00aa66;
            }
        """)
        layout.addWidget(title)

        # Liste des avions
        list_label = QLabel("📡 Avions Détectés")
        list_label.setStyleSheet("font-weight: bold; color: #88ddff; font-size: 12px;")
        layout.addWidget(list_label)

        self.plane_list = QListWidget()
        self.plane_list.setMaximumHeight(200)
        layout.addWidget(self.plane_list)

        # Contrôles avion
        card = QGroupBox("⚙ Contrôles de Vol")
        form = QFormLayout()
        card.setLayout(form)

        self.callsign_label = QLabel("Aucun")
        self.callsign_label.setStyleSheet("color: #ffaa00; font-weight: bold;")
        form.addRow("Sélection:", self.callsign_label)

        self.heading_spin = QSpinBox()
        self.heading_spin.setRange(0, 359)
        self.heading_spin.setSuffix("°")
        form.addRow("Cap:", self.heading_spin)

        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(50, 900)
        self.speed_spin.setSuffix(" km/h")
        form.addRow("Vitesse:", self.speed_spin)

        self.alt_spin = QSpinBox()
        self.alt_spin.setRange(0, 15000)
        self.alt_spin.setSuffix(" m")
        self.alt_spin.setSingleStep(100)
        form.addRow("Altitude:", self.alt_spin)

        # Boutons d'action
        btn_layout = QHBoxLayout()

        self.apply_btn = QPushButton("✓ Appliquer")
        self.deviate_btn = QPushButton("⚠ Dévier")
        self.land_btn = QPushButton("🛬 Atterrir")

        btn_layout.addWidget(self.apply_btn)
        btn_layout.addWidget(self.deviate_btn)
        form.addRow(btn_layout)
        form.addRow(self.land_btn)

        layout.addWidget(card)

        # Statistiques
        stats = QGroupBox("📊 Statistiques")
        v = QVBoxLayout()
        stats.setLayout(v)

        self.score_label = QLabel("Score: 0")
        self.events_label = QLabel("Alertes: 0")
        self.landed_label = QLabel("Atterrissages: 0")

        for label in [self.score_label, self.events_label, self.landed_label]:
            label.setStyleSheet("font-size: 13px; padding: 5px;")

        v.addWidget(self.score_label)
        v.addWidget(self.events_label)
        v.addWidget(self.landed_label)

        layout.addWidget(stats)
        layout.addStretch()

    def apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #0a1520;
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial;
            }
            QGroupBox {
                border: 2px solid #2a5570;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
                font-weight: bold;
                color: #88ddff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a5a7a, stop:1 #1a3a4a);
                color: white;
                border: 2px solid #3a7a9a;
                border-radius: 6px;
                padding: 8px 15px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3a7a9a, stop:1 #2a5a7a);
                border-color: #4a9aba;
            }
            QPushButton:pressed {
                background: #1a3a4a;
            }
            QSpinBox {
                background-color: #152530;
                border: 2px solid #2a5570;
                border-radius: 4px;
                padding: 5px;
                color: #ffffff;
            }
            QSpinBox:focus {
                border-color: #4a9aba;
            }
            QListWidget {
                background-color: #0f1f2a;
                border: 2px solid #2a5570;
                border-radius: 6px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
                margin: 2px;
            }
            QListWidget::item:selected {
                background-color: #2a5a7a;
                color: #ffaa00;
            }
            QListWidget::item:hover {
                background-color: #1a3a4a;
            }
            QLabel {
                color: #c0c0c0;
            }
        """)


# ---- Fenêtre principale ----
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🛫 Simulateur de Tour de Contrôle Aérien")
        self.resize(1200, 900)

        self.scene = RadarScene(RADAR_RADIUS)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing |
                                 QPainter.SmoothPixmapTransform)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setFixedSize(RADAR_RADIUS * 2 + 8, RADAR_RADIUS * 2 + 8)

        # Style de la vue
        self.view.setStyleSheet("""
            QGraphicsView {
                border: 3px solid #00aa88;
                border-radius: 10px;
                background: #000000;
            }
        """)

        self.controls = ControlPanel()

        h = QHBoxLayout()
        h.setSpacing(20)
        h.setContentsMargins(15, 15, 15, 15)
        h.addWidget(self.view)
        h.addWidget(self.controls)
        self.setLayout(h)

        # Style général
        self.setStyleSheet("QWidget { background-color: #050a10; }")

        # Connexions
        self.controls.plane_list.currentItemChanged.connect(self.on_plane_selected)
        self.controls.apply_btn.clicked.connect(self.apply_controls)
        self.controls.deviate_btn.clicked.connect(self.force_deviate)
        self.controls.land_btn.clicked.connect(self.initiate_landing)

        # État
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(UPDATE_INTERVAL_MS)
        self.last_dt = UPDATE_INTERVAL_MS / 1000.0

        self.score = 0
        self.events_count = 0
        self.landings = 0

        # Avions initiaux
        self.create_random_planes(6)

        # Timer pour ajouter des avions
        self.spawn_timer = QTimer()
        self.spawn_timer.timeout.connect(self.spawn_plane)
        self.spawn_timer.start(15000)  # Nouvel avion toutes les 15s

    def create_random_callsign(self):
        prefix = random.choice(["AF", "LH", "BA", "EZY", "DLH", "RYR", "UAE"])
        num = random.randint(100, 9999)
        return f"{prefix}{num}"

    def create_random_planes(self, n=5):
        for _ in range(n):
            angle = random.uniform(0, 360)
            r = random.uniform(RADAR_RADIUS * 0.6, RADAR_RADIUS - 50)
            x = cos(radians(angle)) * r
            y = sin(radians(angle)) * r

            p = PlaneItem(
                self.create_random_callsign(), x, y,
                heading=random.uniform(0, 360),
                speed_kmh=random.uniform(200, 700),
                altitude_m=random.uniform(2000, 9000),
                fuel_percent=random.uniform(40, 100)
            )
            self.scene.add_plane(p)
            self.controls.plane_list.addItem(p.callsign)

    def spawn_plane(self):
        if len(self.scene.planes) < 15:
            self.create_random_planes(1)

    def tick(self):
        dt = self.last_dt

        self.scene.sweep_angle = (self.scene.sweep_angle +
                                  SWEEP_SPEED_DEG_PER_SEC * dt) % 360

        events = self.scene.advance_simulation(dt)

        for event in events:
            if event[0] == 'proximity':
                _, a, b, d = event
                self.events_count += 1
                print(f"⚠ ALERTE: {a.callsign} - {b.callsign} (d={d:.1f})")
            elif event[0] == 'landing':
                _, plane = event
                self.landings += 1
                self.score += 100
                print(f"✓ Atterrissage réussi: {plane.callsign}")
                # Retirer de la liste
                for i in range(self.controls.plane_list.count()):
                    if self.controls.plane_list.item(i).text() == plane.callsign:
                        self.controls.plane_list.takeItem(i)
                        break
            elif event[0] == 'fuel_low':
                _, plane = event
                print(f"⚠ Carburant faible: {plane.callsign}")

        self.controls.events_label.setText(f"Alertes: {self.events_count}")
        self.controls.landed_label.setText(f"Atterrissages: {self.landings}")

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
            return

        p = self.find_plane_by_callsign(cs)
        if p:
            p.deviate_randomly()
            self.controls.heading_spin.setValue(int(p.heading))
            self.controls.speed_spin.setValue(int(p.speed_kmh))

    def initiate_landing(self):
        cs = self.controls.callsign_label.text()
        if cs == "Aucun":
            QMessageBox.warning(self, "Aucun avion", "Sélectionnez d'abord un avion.")
            return

        p = self.find_plane_by_callsign(cs)
        if p:
            # Orienter vers la piste
            p.change_altitude(300)
            p.change_speed(200)
            QMessageBox.information(self, "Atterrissage",
                                    f"{p.callsign} autorisé à atterrir.\n"
                                    f"Guidez-le vers la zone centrale.")


# ---- Exécution ----
if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
