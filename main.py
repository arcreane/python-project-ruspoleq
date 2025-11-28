from math import sin, cos, radians, sqrt, atan2, degrees
import random
import sys
from PySide6.QtCore import (QPointF, QRectF, Qt, QTimer, QPropertyAnimation,
                            QEasingCurve, Property, QAbstractAnimation)
from PySide6.QtGui import (QBrush, QColor, QPainter, QPainterPath, QPen,
                           QLinearGradient, QRadialGradient, QFont, QPolygonF)
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
TARGET_PLANE_COUNT = 5


# Fonctions utilitaires
def project_move(x, y, heading_deg, distance):
    angle = radians(-heading_deg + 90)
    nx = x + cos(angle) * distance
    ny = y + sin(angle) * distance
    return nx, ny


def distance(a: QPointF, b: QPointF):
    return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)


# ---- Orage ----
class StormItem(QGraphicsItem):
    def __init__(self, x, y):
        super().__init__()
        self.setPos(x, y)
        self.animation_phase = 0
        self.radius = 60
        self.strength = random.uniform(0.7, 1.0)

    def boundingRect(self) -> QRectF:
        r = self.radius + 20
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        # Animation de pulsation
        self.animation_phase = (self.animation_phase + 0.15) % 6.28
        pulse = 1.0 + 0.3 * sin(self.animation_phase)
        current_radius = self.radius * pulse

        # Nuage d'orage avec dégradé
        gradient = QRadialGradient(0, 0, current_radius)
        gradient.setColorAt(0, QColor(80, 80, 100, 150))
        gradient.setColorAt(0.5, QColor(50, 50, 70, 120))
        gradient.setColorAt(1, QColor(30, 30, 50, 0))

        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(0, 0), current_radius, current_radius)

        # Éclairs aléatoires
        if random.random() < 0.1:
            painter.setPen(QPen(QColor(255, 255, 100, 200), 3))
            for _ in range(3):
                angle = random.uniform(0, 360)
                length = random.uniform(20, 40)
                x1 = cos(radians(angle)) * 10
                y1 = sin(radians(angle)) * 10
                x2 = cos(radians(angle)) * length
                y2 = sin(radians(angle)) * length
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Symbole d'avertissement
        painter.setPen(QPen(QColor(255, 200, 0), 2))
        font = QFont("Arial", 20, QFont.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(-15, -15, 30, 30), Qt.AlignCenter, "⚡")

    def affects_plane(self, plane_pos: QPointF):
        """Vérifie si un avion est dans la zone d'effet de l'orage"""
        d = distance(self.pos(), plane_pos)
        return d < self.radius


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
        self.landing_mode = False
        self.in_storm = False

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
        if self.in_storm:
            # Clignotement en violet pour les avions dans l'orage
            self.pulse_phase = (self.pulse_phase + 0.3) % 6.28
            intensity = int(100 + 100 * abs(sin(self.pulse_phase)))
            color = QColor(intensity, 50, intensity)
        elif self.warning:
            self.pulse_phase = (self.pulse_phase + 0.2) % 6.28
            intensity = int(155 + 100 * abs(sin(self.pulse_phase)))
            color = QColor(intensity, 50, 50)
        elif self.landing_mode:
            color = QColor(100, 255, 100)
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
        if self.landing_mode:
            text += "\n🛬"
        if self.fuel_percent < 30:
            text += f"\n⚠ {int(self.fuel_percent)}%"
            painter.setPen(QPen(QColor(255, 100, 100)))
        if self.in_storm:
            painter.setPen(QPen(QColor(255, 100, 255)))

        painter.drawText(18, -5, text)

        # Cercle de sélection animé
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 200, 50), 2, Qt.DashLine))
            painter.drawEllipse(-20, -20, 40, 40)

    def advance(self, dt_sec):
        # Mode atterrissage automatique
        if self.landing_mode:
            # Calculer l'angle vers la piste (centre 0,0)
            target_angle = degrees(atan2(-self.x(), -self.y()))

            # Ajuster progressivement le cap vers la cible
            angle_diff = (target_angle - self.heading + 180) % 360 - 180
            turn_rate = 2.0  # degrés par frame
            if abs(angle_diff) > turn_rate:
                self.heading += turn_rate if angle_diff > 0 else -turn_rate
            else:
                self.heading = target_angle

            self.heading = self.heading % 360

            # Descente progressive
            if self.altitude_m > 200:
                self.altitude_m = max(200, self.altitude_m - 20)

            # Réduction de vitesse
            if self.speed_kmh > 180:
                self.speed_kmh = max(180, self.speed_kmh - 5)

        # Perturbations dues à l'orage
        if self.in_storm:
            # Changements erratiques
            self.heading = (self.heading + random.uniform(-5, 5)) % 360
            self.speed_kmh = max(100, min(800, self.speed_kmh + random.uniform(-30, 30)))
            self.altitude_m = max(500, min(12000, self.altitude_m + random.uniform(-50, 50)))

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

    def start_landing(self):
        """Active le mode atterrissage automatique"""
        self.landing_mode = True
        self.update()


# ---- Scene radar améliorée ----
class RadarScene(QGraphicsScene):
    def __init__(self, radius: int):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.radius = radius
        self.planes = []
        self.storms = []
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

    def add_storm(self):
        """Ajoute un orage à une position aléatoire"""
        angle = random.uniform(0, 360)
        r = random.uniform(100, self.radius - 100)
        x = cos(radians(angle)) * r
        y = sin(radians(angle)) * r

        storm = StormItem(x, y)
        self.storms.append(storm)
        self.addItem(storm)
        return storm

    def remove_storm(self, storm: StormItem):
        if storm in self.storms:
            self.storms.remove(storm)
            self.removeItem(storm)

    def advance_simulation(self, dt_sec):
        events = []
        planes_to_remove = []

        for p in list(self.planes):
            p.advance(dt_sec)
            p.warning = False
            p.in_storm = False

            # Vérifier si l'avion est dans un orage
            for storm in self.storms:
                if storm.affects_plane(p.pos()):
                    p.in_storm = True
                    events.append(('storm', p))
                    break

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

            # Labels d'angle - NORD EN HAUT (270° = N)
            if a % 90 == 0:
                painter.setPen(QPen(QColor(100, 200, 255)))
                font = QFont("Arial", 10, QFont.Bold)
                painter.setFont(font)
                tx = cos(ang) * (self.radius - 30)
                ty = sin(ang) * (self.radius - 30)
                # Correction: 270° = N, 0° = E, 90° = S, 180° = O
                directions = {270: "N", 0: "E", 90: "S", 180: "O"}
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

        # Contrôle des orages
        storm_card = QGroupBox("⚡ Gestion Météo")
        storm_layout = QVBoxLayout()
        storm_card.setLayout(storm_layout)

        self.storm_btn = QPushButton("🌩️ Créer Orage")
        self.clear_storms_btn = QPushButton("☀️ Dissiper Orages")

        storm_layout.addWidget(self.storm_btn)
        storm_layout.addWidget(self.clear_storms_btn)

        self.storm_count_label = QLabel("Orages actifs: 0")
        self.storm_count_label.setStyleSheet("font-size: 12px; padding: 5px;")
        storm_layout.addWidget(self.storm_count_label)

        layout.addWidget(storm_card)

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
        self.controls.storm_btn.clicked.connect(self.create_storm)
        self.controls.clear_storms_btn.clicked.connect(self.clear_storms)

        # État
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(UPDATE_INTERVAL_MS)
        self.last_dt = UPDATE_INTERVAL_MS / 1000.0

        self.score = 0
        self.events_count = 0
        self.landings = 0

        # Avions initiaux
        self.create_random_planes(TARGET_PLANE_COUNT)

        # Timer pour ajouter des avions toutes les 20s
        self.spawn_timer = QTimer()
        self.spawn_timer.timeout.connect(self.spawn_plane)
        self.spawn_timer.start(20000)  # 20 secondes

        # Timer pour dissiper les orages après 30 secondes
        self.storm_timers = []

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
        """Ajoute un nouvel avion si nécessaire pour maintenir environ 5 avions"""
        if len(self.scene.planes) < TARGET_PLANE_COUNT:
            self.create_random_planes(1)

    def create_storm(self):
        """Crée un nouvel orage"""
        storm = self.scene.add_storm()
        self.update_storm_count()

        # Timer pour dissiper l'orage après 30 secondes
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.remove_storm(storm))
        timer.start(30000)  # 30 secondes
        self.storm_timers.append(timer)

        QMessageBox.information(self, "Orage détecté",
                                "⚡ Un orage s'est formé sur le radar!\n"
                                "Les avions dans la zone seront perturbés.")

    def remove_storm(self, storm):
        """Dissipe un orage"""
        self.scene.remove_storm(storm)
        self.update_storm_count()

    def clear_storms(self):
        """Dissipe tous les orages"""
        for storm in list(self.scene.storms):
            self.scene.remove_storm(storm)
        self.storm_timers.clear()
        self.update_storm_count()
        QMessageBox.information(self, "Météo", "☀️ Tous les orages ont été dissipés.")

    def update_storm_count(self):
        """Met à jour le compteur d'orages"""
        count = len(self.scene.storms)
        self.controls.storm_count_label.setText(f"Orages actifs: {count}")

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
            elif event[0] == 'storm':
                _, plane = event
                # Message seulement une fois par avion
                if not hasattr(plane, '_storm_warned'):
                    plane._storm_warned = True
                    print(f"⚡ {plane.callsign} traverse un orage!")

        # Réinitialiser les avertissements d'orage pour les avions hors orage
        for p in self.scene.planes:
            if not p.in_storm and hasattr(p, '_storm_warned'):
                delattr(p, '_storm_warned')

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
            if p.landing_mode:
                QMessageBox.information(self, "Atterrissage",
                                        f"{p.callsign} est déjà en approche finale.")
            else:
                p.start_landing()
                QMessageBox.information(self, "Atterrissage",
                                        f"✓ {p.callsign} passe en mode atterrissage automatique.\n"
                                        f"L'avion va se diriger automatiquement vers la piste,\n"
                                        f"descendre à 200m et réduire sa vitesse à 180 km/h.")


# ---- Exécution ----
if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
