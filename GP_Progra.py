from math import sin, cos, radians, sqrt, atan2, degrees
import random
import sys
from datetime import datetime
from PySide6.QtCore import (QPointF, QRectF, Qt, QTimer, QPropertyAnimation,
                            QEasingCurve, Property, QAbstractAnimation)
from PySide6.QtGui import (QBrush, QColor, QPainter, QPainterPath, QPen,
                           QLinearGradient, QRadialGradient, QFont, QPolygonF)
from PySide6.QtWidgets import (QApplication, QGraphicsItem, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget, QPushButton, QFormLayout, QSpinBox,
                               QListWidget, QListWidgetItem, QGroupBox, QMessageBox,
                               QGraphicsDropShadowEffect, QDialog, QTextEdit, QComboBox,
                               QSlider)

# Constantes
RADAR_RADIUS = 400
UPDATE_INTERVAL_MS = 40
SWEEP_SPEED_DEG_PER_SEC = 90
PROXIMITY_THRESHOLD = 30
LANDING_ZONE_SIZE = 80

# Paramètres selon difficulté
DIFFICULTY_SETTINGS = {
    'Facile': {
        'target_planes': 3,
        'spawn_interval': 25000,  # 25 secondes
        'storm_probability': 0.0002,
        'failure_probability': 0.0001,
        'conflict_time': 120,  # 2 minutes
    },
    'Moyen': {
        'target_planes': 5,
        'spawn_interval': 15000,  # 15 secondes
        'storm_probability': 0.0005,
        'failure_probability': 0.0003,
        'conflict_time': 90,  # 1.5 minutes
    },
    'Expert': {
        'target_planes': 8,
        'spawn_interval': 10000,  # 10 secondes
        'storm_probability': 0.001,
        'failure_probability': 0.0005,
        'conflict_time': 60,  # 1 minute
    }
}


# Fonctions utilitaires
def project_move(x, y, heading_deg, distance):
    # heading_deg : 0° = Est (droite), 90° = Sud (bas), 180° = Ouest (gauche), 270° = Nord (haut)
    angle = radians(heading_deg)
    nx = x + cos(angle) * distance
    ny = y + sin(angle) * distance
    return nx, ny


def distance(a: QPointF, b: QPointF):
    return sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)


def predict_position(plane, time_seconds):
    """Prédit la position d'un avion après un certain temps"""
    speed_m_s = (plane.speed_kmh * 1000) / 3600
    distance_pixels = (speed_m_s * time_seconds) / plane.scale_m_per_pixel
    nx, ny = project_move(plane.x(), plane.y(), plane.heading, distance_pixels)
    return QPointF(nx, ny)


def will_conflict(plane1, plane2, time_seconds, threshold=50):
    """Vérifie si deux avions seront en conflit dans le futur"""
    pos1 = predict_position(plane1, time_seconds)
    pos2 = predict_position(plane2, time_seconds)

    d = distance(pos1, pos2)
    alt_diff = abs(plane1.altitude_m - plane2.altitude_m)

    # Conflit si distance < threshold ET séparation verticale < 300m
    return d < threshold and alt_diff < 300


def suggest_avoidance(plane1, plane2):
    """Suggère une manœuvre d'évitement"""
    suggestions = []

    # Essayer de changer l'altitude
    if plane1.altitude_m < plane2.altitude_m - 300:
        suggestions.append(f"{plane1.callsign}: Descendre à {int(plane1.altitude_m - 500)}m")
    elif plane1.altitude_m > plane2.altitude_m + 300:
        suggestions.append(f"{plane1.callsign}: Monter à {int(plane1.altitude_m + 500)}m")
    else:
        suggestions.append(f"{plane1.callsign}: Monter à {int(plane1.altitude_m + 1000)}m")

    # Suggérer changement de cap
    angle_between = degrees(atan2(plane2.y() - plane1.y(), plane2.x() - plane1.x()))
    avoid_heading = (angle_between + 90) % 360
    suggestions.append(f"{plane1.callsign}: Virer au cap {int(avoid_heading)}°")

    return suggestions


# ---- Indicateur de conflit ----
class ConflictIndicator(QGraphicsItem):
    def __init__(self, x, y):
        super().__init__()
        self.setPos(x, y)
        self.animation_phase = 0

    def boundingRect(self) -> QRectF:
        return QRectF(-60, -60, 120, 120)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        self.animation_phase = (self.animation_phase + 0.2) % 6.28
        pulse = 1.0 + 0.4 * abs(sin(self.animation_phase))

        # Cercle de danger pulsant
        painter.setPen(QPen(QColor(255, 50, 50, 150), 3, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(0, 0), 40 * pulse, 40 * pulse)

        # Croix de danger
        painter.setPen(QPen(QColor(255, 100, 100), 4))
        size = 20
        painter.drawLine(-size, -size, size, size)
        painter.drawLine(-size, size, size, -size)


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

        self.animation_phase = (self.animation_phase + 0.15) % 6.28
        pulse = 1.0 + 0.3 * sin(self.animation_phase)
        current_radius = self.radius * pulse

        gradient = QRadialGradient(0, 0, current_radius)
        gradient.setColorAt(0, QColor(80, 80, 100, 150))
        gradient.setColorAt(0.5, QColor(50, 50, 70, 120))
        gradient.setColorAt(1, QColor(30, 30, 50, 0))

        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(0, 0), current_radius, current_radius)

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

        painter.setPen(QPen(QColor(255, 200, 0), 2))
        font = QFont("Arial", 20, QFont.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(-15, -15, 30, 30), Qt.AlignCenter, "⚡")

    def affects_plane(self, plane_pos: QPointF):
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

        gradient = QLinearGradient(0, 0, LANDING_ZONE_SIZE, LANDING_ZONE_SIZE)
        gradient.setColorAt(0, QColor(100, 100, 120, 180))
        gradient.setColorAt(1, QColor(60, 60, 80, 180))

        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(255, 200, 0), 2))
        painter.drawRect(0, 0, LANDING_ZONE_SIZE, LANDING_ZONE_SIZE)

        painter.setPen(QPen(QColor(255, 255, 255, 200), 2, Qt.DashLine))
        painter.drawLine(LANDING_ZONE_SIZE / 2, 0, LANDING_ZONE_SIZE / 2, LANDING_ZONE_SIZE)

        painter.setPen(QPen(Qt.white))
        font = QFont("Arial", 10, QFont.Bold)
        painter.setFont(font)
        painter.drawText(self.boundingRect(), Qt.AlignCenter, "PISTE")


# ---- Avion avec système de pannes ----
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

        # Système de pannes et urgences
        self.emergency = None  # 'engine', 'medical', 'radio', None
        self.emergency_start_time = None
        self.mayday = False
        self.radio_failure_duration = 0

        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 255, 0, 100))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)

    def boundingRect(self) -> QRectF:
        return QRectF(-40, -40, 140, 80)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.save()

        painter.rotate(-self.heading)

        # Couleur selon l'état
        if self.mayday:
            # Clignotement rouge intense pour MAYDAY
            self.pulse_phase = (self.pulse_phase + 0.4) % 6.28
            intensity = int(200 + 55 * abs(sin(self.pulse_phase)))
            color = QColor(intensity, 0, 0)
        elif self.in_storm:
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
            alt_ratio = min(self.altitude_m / 10000, 1.0)
            color = QColor(int(100 + 155 * alt_ratio),
                           int(150 + 105 * alt_ratio), 255)

        # Dessin d'un avion réaliste (nez pointant vers la droite = 0°)
        path = QPainterPath()

        # Fuselage principal
        path.moveTo(-10, -3)
        path.lineTo(10, -3)
        path.lineTo(15, 0)
        path.lineTo(10, 3)
        path.lineTo(-10, 3)
        path.closeSubpath()

        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(140), 1.5))
        painter.drawPath(path)

        # Nez de l'avion (cockpit)
        nose = QPainterPath()
        nose.moveTo(10, -3)
        nose.lineTo(18, -1)
        nose.lineTo(18, 1)
        nose.lineTo(10, 3)
        nose.closeSubpath()

        painter.setBrush(QBrush(color.lighter(120)))
        painter.drawPath(nose)

        # Ailes principales
        wing_color = color.darker(110)
        painter.setBrush(QBrush(wing_color))

        # Aile supérieure
        top_wing = QPainterPath()
        top_wing.moveTo(-2, -3)
        top_wing.lineTo(-2, -15)
        top_wing.lineTo(2, -15)
        top_wing.lineTo(4, -3)
        top_wing.closeSubpath()
        painter.drawPath(top_wing)

        # Aile inférieure
        bottom_wing = QPainterPath()
        bottom_wing.moveTo(-2, 3)
        bottom_wing.lineTo(-2, 15)
        bottom_wing.lineTo(2, 15)
        bottom_wing.lineTo(4, 3)
        bottom_wing.closeSubpath()
        painter.drawPath(bottom_wing)

        # Empennage horizontal
        tail = QPainterPath()
        tail.moveTo(-10, -3)
        tail.lineTo(-12, -7)
        tail.lineTo(-9, -7)
        tail.lineTo(-8, -3)
        tail.closeSubpath()
        painter.drawPath(tail)

        tail2 = QPainterPath()
        tail2.moveTo(-10, 3)
        tail2.lineTo(-12, 7)
        tail2.lineTo(-9, 7)
        tail2.lineTo(-8, 3)
        tail2.closeSubpath()
        painter.drawPath(tail2)

        # Dérive verticale
        vertical_tail = QPainterPath()
        vertical_tail.moveTo(-10, -1)
        vertical_tail.lineTo(-14, -1)
        vertical_tail.lineTo(-13, -6)
        vertical_tail.lineTo(-9, -3)
        vertical_tail.closeSubpath()
        painter.setBrush(QBrush(wing_color.darker(105)))
        painter.drawPath(vertical_tail)

        # Trainée de condensation
        if self.altitude_m > 5000:
            trail_color = QColor(150, 200, 255, 80)
            painter.setPen(QPen(trail_color, 2, Qt.DashLine))
            painter.drawLine(-14, 0, -30, 0)

        painter.restore()

        # Informations textuelles
        painter.setPen(QPen(Qt.white))
        font = QFont("Consolas", 9, QFont.Bold)
        painter.setFont(font)

        text = f"{self.callsign}"
        painter.drawText(30, -10, text)

        info_font = QFont("Consolas", 8)
        painter.setFont(info_font)

        # Altitude
        alt_color = QColor(100, 255, 150)
        if self.altitude_m < 1000:
            alt_color = QColor(255, 200, 100)
        painter.setPen(QPen(alt_color))
        painter.drawText(30, 2, f"↕ {int(self.altitude_m)}m")

        # Vitesse
        speed_color = QColor(150, 200, 255)
        painter.setPen(QPen(speed_color))
        painter.drawText(30, 12, f"→ {int(self.speed_kmh)} km/h")

        # Indicateurs supplémentaires
        extra_y = 22
        painter.setFont(QFont("Consolas", 7))

        # MAYDAY - Priorité absolue
        if self.mayday:
            painter.setPen(QPen(QColor(255, 50, 50)))
            painter.setFont(QFont("Consolas", 9, QFont.Bold))
            painter.drawText(30, extra_y, "🆘 MAYDAY!")
            extra_y += 12
            painter.setFont(QFont("Consolas", 7))

            if self.emergency == 'engine':
                painter.drawText(30, extra_y, "⚠ Panne moteur")
            elif self.emergency == 'medical':
                painter.drawText(30, extra_y, "🏥 Urgence médicale")
            elif self.emergency == 'radio':
                painter.drawText(30, extra_y, "📻 Panne radio")
            extra_y += 10

        if self.landing_mode:
            painter.setPen(QPen(QColor(100, 255, 100)))
            painter.drawText(30, extra_y, "🛬 ATTERRISSAGE")
            extra_y += 10

        if self.fuel_percent < 30:
            painter.setPen(QPen(QColor(255, 100, 100)))
            painter.drawText(30, extra_y, f"⚠ Fuel {int(self.fuel_percent)}%")
            extra_y += 10

        if self.in_storm:
            painter.setPen(QPen(QColor(255, 100, 255)))
            painter.drawText(30, extra_y, "⚡ ORAGE")

        if self.isSelected():
            painter.setPen(QPen(QColor(255, 200, 50), 2, Qt.DashLine))
            painter.drawEllipse(-25, -20, 50, 40)

    def trigger_emergency(self, emergency_type):
        """Déclenche une urgence"""
        self.emergency = emergency_type
        self.emergency_start_time = datetime.now()
        self.mayday = True

        if emergency_type == 'engine':
            # Panne moteur : réduction de vitesse et descente forcée
            self.speed_kmh *= 0.6
        elif emergency_type == 'radio':
            # Panne radio : avion non contrôlable pendant 20 secondes
            self.radio_failure_duration = 20

    def advance(self, dt_sec):
        # Gestion panne radio
        if self.emergency == 'radio' and self.radio_failure_duration > 0:
            self.radio_failure_duration -= dt_sec
            if self.radio_failure_duration <= 0:
                self.emergency = None
                self.mayday = False

        # Mode atterrissage automatique
        if self.landing_mode:
            dx = -self.x()
            dy = -self.y()
            target_angle = degrees(atan2(dy, dx))

            angle_diff = (target_angle - self.heading + 180) % 360 - 180
            turn_rate = 2.0
            if abs(angle_diff) > turn_rate:
                self.heading += turn_rate if angle_diff > 0 else -turn_rate
            else:
                self.heading = target_angle

            self.heading = self.heading % 360

            if self.altitude_m > 200:
                self.altitude_m = max(200, self.altitude_m - 20)

            if self.speed_kmh > 180:
                self.speed_kmh = max(180, self.speed_kmh - 5)

        # Panne moteur : descente progressive
        if self.emergency == 'engine':
            self.altitude_m = max(0, self.altitude_m - 15 * dt_sec)
            self.speed_kmh = max(150, self.speed_kmh - 3 * dt_sec)

        # Perturbations dues à l'orage
        if self.in_storm:
            self.heading = (self.heading + random.uniform(-5, 5)) % 360
            self.speed_kmh = max(100, min(800, self.speed_kmh + random.uniform(-30, 30)))
            self.altitude_m = max(500, min(12000, self.altitude_m + random.uniform(-50, 50)))

        speed_m_s = (self.speed_kmh * 1000) / 3600
        distance_pixels = (speed_m_s * dt_sec) / self.scale_m_per_pixel

        x, y = self.x(), self.y()
        nx, ny = project_move(x, y, self.heading, distance_pixels)
        self.setPos(nx, ny)

        # Consommation de carburant (plus rapide si urgence)
        fuel_consumption = 0.01 if not self.mayday else 0.02
        self.fuel_percent = max(0, self.fuel_percent - fuel_consumption * dt_sec)

        self.update()

    def change_heading(self, new_heading_deg):
        # Ne pas permettre de changer le cap si panne radio
        if self.emergency == 'radio':
            return False
        self.heading = new_heading_deg % 360
        self.update()
        return True

    def change_speed(self, new_speed_kmh):
        if self.emergency == 'radio':
            return False
        # Limiter la vitesse si panne moteur
        if self.emergency == 'engine':
            new_speed_kmh = min(new_speed_kmh, self.speed_kmh)
        self.speed_kmh = max(50, min(900, new_speed_kmh))
        return True

    def change_altitude(self, new_alt_m):
        if self.emergency == 'radio':
            return False
        # Ne pas permettre de monter si panne moteur
        if self.emergency == 'engine' and new_alt_m > self.altitude_m:
            return False
        self.altitude_m = max(0, min(15000, new_alt_m))
        return True

    def deviate_randomly(self):
        if self.emergency == 'radio':
            return
        self.heading = (self.heading + random.uniform(-60, 60)) % 360
        self.speed_kmh = max(80, min(800, self.speed_kmh + random.uniform(-120, 120)))

    def start_landing(self):
        self.landing_mode = True
        self.update()


# ---- Scene radar avec détection de conflits ----
class RadarScene(QGraphicsScene):
    def __init__(self, radius: int):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.radius = radius
        self.planes = []
        self.storms = []
        self.conflict_indicators = []
        self.sweep_angle = 0.0
        self.landing_zone = LandingZoneItem()
        self.addItem(self.landing_zone)
        self.setBackgroundBrush(QBrush(QColor(5, 15, 25)))
        self.conflict_prediction_time = 90  # secondes

    def add_plane(self, plane: PlaneItem):
        self.planes.append(plane)
        self.addItem(plane)

    def remove_plane(self, plane: PlaneItem):
        if plane in self.planes:
            self.planes.remove(plane)
            self.removeItem(plane)

    def add_storm(self):
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

    def detect_future_conflicts(self):
        """Détecte les conflits futurs et retourne les suggestions"""
        conflicts = []
        suggestions = []

        # Nettoyer les anciens indicateurs
        for indicator in self.conflict_indicators:
            self.removeItem(indicator)
        self.conflict_indicators.clear()

        for i in range(len(self.planes)):
            for j in range(i + 1, len(self.planes)):
                p1, p2 = self.planes[i], self.planes[j]

                if will_conflict(p1, p2, self.conflict_prediction_time):
                    conflicts.append((p1, p2))

                    # Ajouter indicateur visuel
                    future_pos1 = predict_position(p1, self.conflict_prediction_time)
                    indicator = ConflictIndicator(future_pos1.x(), future_pos1.y())
                    self.addItem(indicator)
                    self.conflict_indicators.append(indicator)

                    # Générer suggestions
                    suggestions.extend(suggest_avoidance(p1, p2))

        return conflicts, suggestions

    def advance_simulation(self, dt_sec):
        events = []
        planes_to_remove = []

        for p in list(self.planes):
            p.advance(dt_sec)
            p.warning = False
            p.in_storm = False

            for storm in self.storms:
                if storm.affects_plane(p.pos()):
                    p.in_storm = True
                    events.append(('storm', p))
                    break

            if abs(p.x()) < LANDING_ZONE_SIZE / 2 and abs(p.y()) < LANDING_ZONE_SIZE / 2:
                if p.altitude_m < 500 and p.speed_kmh < 300:
                    planes_to_remove.append(p)
                    events.append(('landing', p))

            if p.fuel_percent < 20:
                events.append(('fuel_low', p))

            # Crash si altitude = 0 sans être sur la piste
            if p.altitude_m <= 0 and not (abs(p.x()) < LANDING_ZONE_SIZE / 2 and abs(p.y()) < LANDING_ZONE_SIZE / 2):
                planes_to_remove.append(p)
                events.append(('crash', p))

        # Détection de proximité immédiate
        for i in range(len(self.planes)):
            for j in range(i + 1, len(self.planes)):
                d = distance(self.planes[i].pos(), self.planes[j].pos())
                if d < PROXIMITY_THRESHOLD:
                    self.planes[i].warning = True
                    self.planes[j].warning = True
                    events.append(('proximity', self.planes[i], self.planes[j], d))

        for p in planes_to_remove:
            self.remove_plane(p)

        return events

    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        center = QPointF(0, 0)

        gradient = QRadialGradient(center, self.radius)
        gradient.setColorAt(0, QColor(5, 15, 25))
        gradient.setColorAt(0.8, QColor(5, 15, 25))
        gradient.setColorAt(1, QColor(0, 80, 120))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(0, 150, 200), 3))
        painter.drawEllipse(center, self.radius, self.radius)

        painter.setPen(QPen(QColor(0, 100, 150, 80), 1))
        for r in range(int(self.radius / 4), self.radius, int(self.radius / 4)):
            painter.drawEllipse(center, r, r)
            painter.setPen(QPen(QColor(100, 200, 255, 150)))
            font = QFont("Arial", 8)
            painter.setFont(font)
            painter.drawText(QPointF(5, -r + 5), f"{r}px")
            painter.setPen(QPen(QColor(0, 100, 150, 80), 1))

        painter.setPen(QPen(QColor(0, 80, 120, 60), 1))
        for a in range(0, 360, 30):
            ang = radians(a)
            x = cos(ang) * self.radius
            y = sin(ang) * self.radius
            painter.drawLine(center, QPointF(x, y))

            if a % 90 == 0:
                painter.setPen(QPen(QColor(100, 200, 255)))
                font = QFont("Arial", 10, QFont.Bold)
                painter.setFont(font)
                tx = cos(ang) * (self.radius - 30)
                ty = sin(ang) * (self.radius - 30)
                directions = {270: "N", 0: "E", 90: "S", 180: "O"}
                painter.drawText(QPointF(tx - 10, ty + 5), directions.get(a, ""))
                painter.setPen(QPen(QColor(0, 80, 120, 60), 1))

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

        painter.setPen(QPen(QColor(100, 255, 100), 2))
        painter.drawLine(-15, 0, 15, 0)
        painter.drawLine(0, -15, 0, 15)
        painter.drawEllipse(center, 5, 5)

        painter.restore()


# ---- Dialogue de statistiques ----
class StatsDialog(QDialog):
    def __init__(self, stats, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📊 Statistiques de la Session")
        self.setModal(True)
        self.resize(600, 500)

        layout = QVBoxLayout()

        title = QLabel("🎮 RAPPORT DE SESSION")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #00ff88;
            padding: 15px;
            background: #1a3a4a;
            border-radius: 8px;
        """)
        layout.addWidget(title)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)

        # Générer le rapport
        report = f"""
═══════════════════════════════════════════════════
        📊 STATISTIQUES DÉTAILLÉES
═══════════════════════════════════════════════════

⏱️  DURÉE DE SESSION
    Temps total: {stats['duration']:.1f} secondes ({stats['duration'] // 60:.0f}min {stats['duration'] % 60:.0f}s)
    Difficulté: {stats['difficulty']}

✈️  AVIONS GÉRÉS
    Total d'avions apparus: {stats['total_planes']}
    Atterrissages réussis: {stats['landings']} ✓
    Crashes: {stats['crashes']} ✗
    Taux de réussite: {stats['success_rate']:.1f}%

⚠️  INCIDENTS
    Alertes de proximité: {stats['proximity_alerts']}
    Conflits prédits évités: {stats['conflicts_avoided']}
    Urgences MAYDAY: {stats['emergencies']}
        - Pannes moteur: {stats['engine_failures']}
        - Urgences médicales: {stats['medical_emergencies']}
        - Pannes radio: {stats['radio_failures']}

🌩️  MÉTÉO
    Orages rencontrés: {stats['storms_encountered']}
    Avions affectés par orages: {stats['planes_in_storms']}

📈  PERFORMANCE
    Score final: {stats['score']} points
    Actions de contrôle: {stats['control_actions']}
    Efficacité: {stats['efficiency']:.1f}%

🏆  ÉVALUATION FINALE
    {stats['evaluation']}

═══════════════════════════════════════════════════
        """

        text_edit.setPlainText(report)
        text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #0a1520;
                color: #e0e0e0;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                border: 2px solid #2a5570;
                border-radius: 8px;
                padding: 10px;
            }
        """)

        layout.addWidget(text_edit)

        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #2a5a7a;
                color: white;
                border: 2px solid #3a7a9a;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #3a7a9a;
            }
        """)
        layout.addWidget(close_btn)

        self.setLayout(layout)
        self.setStyleSheet("QDialog { background-color: #050a10; }")


# ---- Panneau de contrôle étendu ----
class ControlPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.apply_styles()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)
        self.setLayout(layout)

        # Titre
        title = QLabel("🛫 CONTRÔLE AÉRIEN")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #00ff88;
                padding: 8px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a3a4a, stop:1 #0d1f2a);
                border-radius: 8px;
                border: 2px solid #00aa66;
            }
        """)
        layout.addWidget(title)

        # Contrôles de simulation
        sim_card = QGroupBox("⚙️ Simulation")
        sim_layout = QVBoxLayout()
        sim_card.setLayout(sim_layout)

        # Difficulté
        diff_layout = QHBoxLayout()
        diff_label = QLabel("Difficulté:")
        self.difficulty_combo = QComboBox()
        self.difficulty_combo.addItems(['Facile', 'Moyen', 'Expert'])
        self.difficulty_combo.setCurrentText('Moyen')
        diff_layout.addWidget(diff_label)
        diff_layout.addWidget(self.difficulty_combo)
        sim_layout.addLayout(diff_layout)

        # Vitesse de simulation
        speed_layout = QHBoxLayout()
        speed_label = QLabel("Vitesse:")
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setMinimum(1)
        self.speed_slider.setMaximum(4)
        self.speed_slider.setValue(1)
        self.speed_slider.setTickPosition(QSlider.TicksBelow)
        self.speed_label = QLabel("x1")
        speed_layout.addWidget(speed_label)
        speed_layout.addWidget(self.speed_slider)
        speed_layout.addWidget(self.speed_label)
        sim_layout.addLayout(speed_layout)

        # Boutons pause/stop
        btn_layout = QHBoxLayout()
        self.pause_btn = QPushButton("⏸ Pause")
        self.stop_btn = QPushButton("⏹ Stop")
        btn_layout.addWidget(self.pause_btn)
        btn_layout.addWidget(self.stop_btn)
        sim_layout.addLayout(btn_layout)

        layout.addWidget(sim_card)

        # Liste des avions
        list_label = QLabel("📡 Avions")
        list_label.setStyleSheet("font-weight: bold; color: #88ddff; font-size: 11px;")
        layout.addWidget(list_label)

        self.plane_list = QListWidget()
        self.plane_list.setMaximumHeight(120)
        layout.addWidget(self.plane_list)

        # Suggestions de conflits
        self.suggestions_label = QLabel("💡 Suggestions")
        self.suggestions_label.setStyleSheet("font-weight: bold; color: #ffaa00; font-size: 11px;")
        layout.addWidget(self.suggestions_label)

        self.suggestions_list = QListWidget()
        self.suggestions_list.setMaximumHeight(80)
        layout.addWidget(self.suggestions_list)

        # Contrôles avion
        card = QGroupBox("⚙ Contrôles")
        form = QFormLayout()
        form.setSpacing(5)
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

        btn_layout2 = QHBoxLayout()
        self.apply_btn = QPushButton("✓")
        self.deviate_btn = QPushButton("⚠")
        self.land_btn = QPushButton("🛬")
        btn_layout2.addWidget(self.apply_btn)
        btn_layout2.addWidget(self.deviate_btn)
        btn_layout2.addWidget(self.land_btn)
        form.addRow(btn_layout2)

        layout.addWidget(card)

        # Contrôle des orages
        storm_card = QGroupBox("⚡ Météo")
        storm_layout = QVBoxLayout()
        storm_card.setLayout(storm_layout)

        btn_layout3 = QHBoxLayout()
        self.storm_btn = QPushButton("🌩️")
        self.clear_storms_btn = QPushButton("☀️")
        btn_layout3.addWidget(self.storm_btn)
        btn_layout3.addWidget(self.clear_storms_btn)
        storm_layout.addLayout(btn_layout3)

        self.storm_count_label = QLabel("Orages: 0")
        self.storm_count_label.setStyleSheet("font-size: 11px; padding: 3px;")
        storm_layout.addWidget(self.storm_count_label)
        layout.addWidget(storm_card)

        # Statistiques
        stats = QGroupBox("📊 Stats")
        v = QVBoxLayout()
        v.setSpacing(3)
        stats.setLayout(v)

        self.score_label = QLabel("Score: 0")
        self.events_label = QLabel("Alertes: 0")
        self.landed_label = QLabel("Atterris: 0")
        self.time_label = QLabel("Temps: 0:00")

        for label in [self.score_label, self.events_label, self.landed_label, self.time_label]:
            label.setStyleSheet("font-size: 11px; padding: 2px;")

        v.addWidget(self.score_label)
        v.addWidget(self.events_label)
        v.addWidget(self.landed_label)
        v.addWidget(self.time_label)

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
                margin-top: 8px;
                padding-top: 12px;
                font-weight: bold;
                color: #88ddff;
                font-size: 11px;
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
                padding: 6px 10px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3a7a9a, stop:1 #2a5a7a);
                border-color: #4a9aba;
            }
            QPushButton:pressed {
                background: #1a3a4a;
            }
            QSpinBox, QComboBox {
                background-color: #152530;
                border: 2px solid #2a5570;
                border-radius: 4px;
                padding: 5px;
                color: #ffffff;
            }
            QSpinBox:focus, QComboBox:focus {
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
            QSlider::groove:horizontal {
                background: #1a3a4a;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #3a7a9a;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
        """)


# ---- Fenêtre principale ----
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🛫 Simulateur de Tour de Contrôle Aérien - Version Avancée")

        # Configuration de la fenêtre en plein écran
        self.showMaximized()

        # Attendre que la fenêtre soit affichée pour obtenir la vraie taille
        QApplication.processEvents()

        # Calculer la taille du radar basée sur la taille réelle de la fenêtre
        available_width = self.width() - 500  # Largeur - panneau de contrôle - marges
        available_height = self.height() - 50  # Hauteur - marges
        radar_size = min(available_width, available_height)

        self.scene = RadarScene(radar_size // 2)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing |
                                 QPainter.SmoothPixmapTransform)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Ne pas fixer la taille, utiliser une taille minimum
        self.view.setMinimumSize(radar_size, radar_size)
        self.view.setMaximumSize(radar_size, radar_size)

        self.view.setStyleSheet("""
            QGraphicsView {
                border: 3px solid #00aa88;
                border-radius: 10px;
                background: #000000;
            }
        """)

        self.controls = ControlPanel()
        self.controls.setMinimumWidth(380)
        self.controls.setMaximumWidth(420)

        h = QHBoxLayout()
        h.setSpacing(20)
        h.setContentsMargins(15, 15, 15, 15)
        h.addWidget(self.view, 1, Qt.AlignCenter)
        h.addWidget(self.controls, 0, Qt.AlignTop)
        self.setLayout(h)

        self.setStyleSheet("QWidget { background-color: #050a10; }")

        # Connexions
        self.controls.plane_list.currentItemChanged.connect(self.on_plane_selected)
        self.controls.apply_btn.clicked.connect(self.apply_controls)
        self.controls.deviate_btn.clicked.connect(self.force_deviate)
        self.controls.land_btn.clicked.connect(self.initiate_landing)
        self.controls.storm_btn.clicked.connect(self.create_storm)
        self.controls.clear_storms_btn.clicked.connect(self.clear_storms)
        self.controls.pause_btn.clicked.connect(self.toggle_pause)
        self.controls.stop_btn.clicked.connect(self.stop_simulation)
        self.controls.speed_slider.valueChanged.connect(self.change_speed)
        self.controls.difficulty_combo.currentTextChanged.connect(self.change_difficulty)

        # État
        self.paused = False
        self.simulation_speed = 1
        self.difficulty = 'Moyen'
        self.start_time = datetime.now()

        # Statistiques
        self.score = 0
        self.events_count = 0
        self.landings = 0
        self.crashes = 0
        self.total_planes_spawned = 0
        self.control_actions = 0
        self.conflicts_avoided = 0
        self.emergencies_count = 0
        self.engine_failures = 0
        self.medical_emergencies = 0
        self.radio_failures = 0
        self.storms_encountered = 0
        self.planes_in_storms_count = 0

        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(UPDATE_INTERVAL_MS)
        self.last_dt = UPDATE_INTERVAL_MS / 1000.0

        # Timer de temps écoulé
        self.time_timer = QTimer()
        self.time_timer.timeout.connect(self.update_time)
        self.time_timer.start(1000)

        # Avions initiaux
        self.create_random_planes(DIFFICULTY_SETTINGS[self.difficulty]['target_planes'])

        # Timer pour ajouter des avions
        self.spawn_timer = QTimer()
        self.spawn_timer.timeout.connect(self.spawn_plane)
        self.spawn_timer.start(DIFFICULTY_SETTINGS[self.difficulty]['spawn_interval'])

        self.storm_timers = []

        # Timer pour événements aléatoires
        self.event_timer = QTimer()
        self.event_timer.timeout.connect(self.random_events)
        self.event_timer.start(1000)  # Vérifier chaque seconde

    def change_difficulty(self, difficulty):
        """Change la difficulté en cours de partie"""
        self.difficulty = difficulty
        settings = DIFFICULTY_SETTINGS[difficulty]

        # Ajuster le temps de prédiction des conflits
        self.scene.conflict_prediction_time = settings['conflict_time']

        # Redémarrer le timer de spawn avec le nouvel intervalle
        self.spawn_timer.stop()
        self.spawn_timer.start(settings['spawn_interval'])

    def change_speed(self, value):
        """Change la vitesse de simulation"""
        self.simulation_speed = value
        self.controls.speed_label.setText(f"x{value}")

    def toggle_pause(self):
        """Pause/Reprend la simulation"""
        self.paused = not self.paused
        if self.paused:
            self.controls.pause_btn.setText("▶ Reprendre")
            self.timer.stop()
            self.spawn_timer.stop()
            self.event_timer.stop()
            self.time_timer.stop()
        else:
            self.controls.pause_btn.setText("⏸ Pause")
            self.timer.start(UPDATE_INTERVAL_MS)
            self.spawn_timer.start(DIFFICULTY_SETTINGS[self.difficulty]['spawn_interval'])
            self.event_timer.start(1000)
            self.time_timer.start(1000)

    def stop_simulation(self):
        """Arrête la simulation et affiche les statistiques"""
        self.timer.stop()
        self.spawn_timer.stop()
        self.event_timer.stop()
        self.time_timer.stop()

        # Calculer les statistiques
        duration = (datetime.now() - self.start_time).total_seconds()
        success_rate = (self.landings / max(1, self.total_planes_spawned)) * 100
        efficiency = min(100, (self.score / max(1, duration)) * 10)

        # Évaluation
        if success_rate >= 90 and self.crashes == 0:
            evaluation = "🏆 EXCELLENT! Contrôleur aérien exemplaire!"
        elif success_rate >= 70:
            evaluation = "👍 BIEN! Bonne gestion du trafic aérien."
        elif success_rate >= 50:
            evaluation = "😐 MOYEN. Quelques améliorations nécessaires."
        else:
            evaluation = "❌ INSUFFISANT. Entraînez-vous davantage."

        stats = {
            'duration': duration,
            'difficulty': self.difficulty,
            'total_planes': self.total_planes_spawned,
            'landings': self.landings,
            'crashes': self.crashes,
            'success_rate': success_rate,
            'proximity_alerts': self.events_count,
            'conflicts_avoided': self.conflicts_avoided,
            'emergencies': self.emergencies_count,
            'engine_failures': self.engine_failures,
            'medical_emergencies': self.medical_emergencies,
            'radio_failures': self.radio_failures,
            'storms_encountered': self.storms_encountered,
            'planes_in_storms': self.planes_in_storms_count,
            'score': self.score,
            'control_actions': self.control_actions,
            'efficiency': efficiency,
            'evaluation': evaluation
        }

        dialog = StatsDialog(stats, self)
        dialog.exec()

    def update_time(self):
        """Met à jour le temps écoulé"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        self.controls.time_label.setText(f"Temps: {minutes}:{seconds:02d}")

    def random_events(self):
        """Génère des événements aléatoires (pannes, urgences, orages)"""
        if self.paused or len(self.scene.planes) == 0:
            return

        settings = DIFFICULTY_SETTINGS[self.difficulty]

        # Orage aléatoire
        if random.random() < settings['storm_probability']:
            self.create_storm()
            self.storms_encountered += 1

        # Panne/urgence aléatoire sur un avion
        if random.random() < settings['failure_probability']:
            plane = random.choice(self.scene.planes)
            if not plane.mayday:  # Ne pas ajouter d'urgence si déjà en urgence
                emergency_type = random.choice(['engine', 'medical', 'radio'])
                plane.trigger_emergency(emergency_type)

                self.emergencies_count += 1
                if emergency_type == 'engine':
                    self.engine_failures += 1
                    msg = f"🚨 MAYDAY! {plane.callsign} - Panne moteur!"
                elif emergency_type == 'medical':
                    self.medical_emergencies += 1
                    msg = f"🚨 MAYDAY! {plane.callsign} - Urgence médicale à bord!"
                else:
                    self.radio_failures += 1
                    msg = f"🚨 MAYDAY! {plane.callsign} - Panne radio (20s)!"

                QMessageBox.critical(self, "URGENCE", msg)

    def create_random_callsign(self):
        prefix = random.choice(["AF", "LH", "BA", "EZY", "DLH", "RYR", "UAE", "KLM", "SWR"])
        num = random.randint(100, 9999)
        return f"{prefix}{num}"

    def create_random_planes(self, n=5):
        for _ in range(n):
            angle = random.uniform(0, 360)
            r = random.uniform(self.scene.radius * 0.6, self.scene.radius - 50)
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
            self.total_planes_spawned += 1

    def spawn_plane(self):
        """Ajoute un nouvel avion selon les paramètres de difficulté"""
        target = DIFFICULTY_SETTINGS[self.difficulty]['target_planes']
        if len(self.scene.planes) < target:
            self.create_random_planes(1)

    def create_storm(self):
        storm = self.scene.add_storm()
        self.update_storm_count()

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.remove_storm(storm))
        timer.start(30000)
        self.storm_timers.append(timer)

    def remove_storm(self, storm):
        self.scene.remove_storm(storm)
        self.update_storm_count()

    def clear_storms(self):
        for storm in list(self.scene.storms):
            self.scene.remove_storm(storm)
        self.storm_timers.clear()
        self.update_storm_count()

    def update_storm_count(self):
        count = len(self.scene.storms)
        self.controls.storm_count_label.setText(f"Orages: {count}")

    def tick(self):
        if self.paused:
            return

        dt = self.last_dt * self.simulation_speed

        self.scene.sweep_angle = (self.scene.sweep_angle +
                                  SWEEP_SPEED_DEG_PER_SEC * dt) % 360

        # Détection de conflits futurs
        conflicts, suggestions = self.scene.detect_future_conflicts()

        # Afficher les suggestions
        self.controls.suggestions_list.clear()
        if suggestions:
            for suggestion in suggestions[:5]:  # Limiter à 5 suggestions
                self.controls.suggestions_list.addItem(suggestion)
            self.conflicts_avoided += len(conflicts)

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
                if plane.mayday:
                    self.score += 200  # Bonus pour atterrissage d'urgence
                print(f"✓ Atterrissage réussi: {plane.callsign}")
                for i in range(self.controls.plane_list.count()):
                    if self.controls.plane_list.item(i).text() == plane.callsign:
                        self.controls.plane_list.takeItem(i)
                        break
            elif event[0] == 'crash':
                _, plane = event
                self.crashes += 1
                self.score -= 500
                print(f"✗ CRASH: {plane.callsign}")
                QMessageBox.warning(self, "CRASH", f"💥 {plane.callsign} s'est écrasé!")
                for i in range(self.controls.plane_list.count()):
                    if self.controls.plane_list.item(i).text() == plane.callsign:
                        self.controls.plane_list.takeItem(i)
                        break
            elif event[0] == 'fuel_low':
                _, plane = event
                print(f"⚠ Carburant faible: {plane.callsign}")
            elif event[0] == 'storm':
                _, plane = event
                if not hasattr(plane, '_storm_warned'):
                    plane._storm_warned = True
                    self.planes_in_storms_count += 1
                    print(f"⚡ {plane.callsign} traverse un orage!")

        for p in self.scene.planes:
            if not p.in_storm and hasattr(p, '_storm_warned'):
                delattr(p, '_storm_warned')

        self.controls.events_label.setText(f"Alertes: {self.events_count}")
        self.controls.landed_label.setText(f"Atterrissages: {self.landings}")
        self.controls.score_label.setText(f"Score: {self.score}")

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
            success = True
            success &= p.change_heading(self.controls.heading_spin.value())
            success &= p.change_speed(self.controls.speed_spin.value())
            success &= p.change_altitude(self.controls.alt_spin.value())

            if success:
                self.score += 1
                self.control_actions += 1
                self.controls.score_label.setText(f"Score: {self.score}")
            else:
                QMessageBox.warning(self, "Contrôle impossible",
                                    f"{p.callsign} ne répond pas (panne radio)")

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
                                        f"L'avion va se diriger automatiquement vers la piste.")


# ---- Exécution ----
if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())