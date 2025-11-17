# -----------------------------
# MODÈLE : Aircraft (dataclass)
# -----------------------------

@dataclass
class Aircraft:
    id: str
    x: float
    y: float
    altitude: float
    speed: float
    heading: float
    fuel: float
    status: str = "normal"
    color: QColor = field(default_factory=lambda: QColor.fromHsv(random.randint(0,359), 200, 255))
    target_altitude: Optional[float] = None
    emergency: bool = False
    fuel_leak: bool = False
    engine_failure: bool = False
    weather_delay: bool = False

    landing_timer: float = 0.0
    descent_speed: float = 5.0   # vitesse de descente verticale en atterrissage (m/s)

    def update(self, dt):
        # consommation de carburant (lente mais toujours présente)
        if self.fuel > 0:
            self.fuel -= dt * (0.01 if not self.fuel_leak else 0.03)
        if self.fuel <= 0 and self.status != "landing":
            self.status = "landing"

        # si carburant très bas → forcer atterrissage
        if self.fuel <= 10 and self.status != "landing":
            self.status = "landing"

        # altitudes cibles
        if self.target_altitude is not None:
            if abs(self.altitude - self.target_altitude) < 50:
                self.altitude = self.target_altitude
                self.target_altitude = None
            elif self.altitude < self.target_altitude:
                self.altitude += dt * 300
            else:
                self.altitude -= dt * 300

        # effet météo (ralentissement)
        effective_speed = self.speed * (0.7 if self.weather_delay else 1.0)

        # gestion de l’atterrissage
        if self.status == "landing":
            # réduire la vitesse (km/h)
            if self.speed > MIN_LANDING_SPEED:
                self.speed -= dt * 20
            else:
                self.speed = MIN_LANDING_SPEED

            # descente plus rapide (m/s)
            if self.altitude > 0:
                self.altitude -= dt * self.descent_speed
                if self.altitude <= 0:
                    self.altitude = 0
                    self.speed = 0
                    self.status = "landed"

        # attente (holding)
        if self.status == "holding":
            self.heading += dt * 8
            self.heading %= 360

        # panne moteur
        if self.engine_failure:
            effective_speed *= 0.5

        # déplacement selon cap + vitesse
        distance = effective_speed * (dt / 3600)
        heading_rad = math.radians(90 - self.heading)
        dx = distance * math.cos(heading_rad)
        dy = distance * math.sin(heading_rad)
        self.x += dx
        self.y += dy

    # -------------------------
    # COMMANDES UTILISATEUR
    # -------------------------
    def set_heading(self, heading):
        self.heading = heading % 360

    def climb(self):
        if self.altitude < MAX_ALTITUDE:
            self.target_altitude = min(self.altitude + 1000, MAX_ALTITUDE)

    def descend(self):
        if self.altitude > 0:
            self.target_altitude = max(self.altitude - 1000, 0)
        if self.target_altitude == 0:
            self.status = "landing"

    def hold(self):
        self.status = "holding"

    def authorize_landing(self):
        self.status = "landing"

    def go_around(self):
        if self.status != "landed":
            self.status = "normal"
            self.altitude += 800
            self.speed = max(self.speed, 300)


# -----------------------------
# SIMULATION
# -----------------------------

class Simulation(QObject):
    aircraft_added = Signal(Aircraft)
    aircraft_removed = Signal(str)
    aircraft_updated = Signal(Aircraft)
    collision_signal = Signal(str, str)
    score_updated = Signal(int)
    event_signal = Signal(str)

    emergency_signal = Signal(Aircraft)

    def __init__(self):
        super().__init__()
        self.aircraft_list: List[Aircraft] = []
        self.score = 0
        self.last_update = time.time()

        self.timer = QTimer()
        self.timer.setInterval(200)  # cycle simulation 200ms
        self.timer.timeout.connect(self.update_simulation)

        self.spawn_timer = QTimer()
        self.spawn_timer.setInterval(15000)  # apparition lente : 15s
        self.spawn_timer.timeout.connect(self.spawn_aircraft)

        self.event_timer = QTimer()
        self.event_timer.setInterval(20000)  # événements toutes les 20s
        self.event_timer.timeout.connect(self.random_event)

    def start(self):
        self.last_update = time.time()
        self.timer.start()
        self.spawn_timer.start()
        self.event_timer.start()

    def update_simulation(self):
        now = time.time()
        dt = now - self.last_update
        self.last_update = now

        # mise à jour des avions
        for ac in self.aircraft_list:
            ac.update(dt)
            self.aircraft_updated.emit(ac)

        # détection des collisions
        to_remove = set()
        for i in range(len(self.aircraft_list)):
            for j in range(i + 1, len(self.aircraft_list)):
                a = self.aircraft_list[i]
                b = self.aircraft_list[j]

                dx = a.x - b.x
                dy = a.y - b.y
                distance = math.sqrt(dx * dx + dy * dy)

                if distance < 0.08 and abs(a.altitude - b.altitude) < 50:
                    self.collision_signal.emit(a.id, b.id)
                    to_remove.add(a)
                    to_remove.add(b)

                elif distance < 0.3 and abs(a.altitude - b.altitude) < 150:
                    self.event(f"Quasi-collision entre {a.id} et {b.id}")
                    a.heading += 10
                    b.heading -= 10

        for ac in to_remove:
            if ac in self.aircraft_list:
                self.aircraft_list.remove(ac)
                self.aircraft_removed.emit(ac.id)

        # score (avion atterri)
        landed_now = [ac for ac in self.aircraft_list if ac.status == "landed"]
        for ac in landed_now:
            self.score += 1
            self.score_updated.emit(self.score)
            self.aircraft_list.remove(ac)
            self.aircraft_removed.emit(ac.id)
            self.event(f"{ac.id} a atterri (+1 point)")

    def spawn_aircraft(self):
        # apparition sur les bords, altitude <= 1000m
        edge = random.choice(["N", "S", "E", "W"])
        if edge == "N":
            x = random.uniform(-10, 10)
            y = -12
            heading = random.uniform(160, 200)
        elif edge == "S":
            x = random.uniform(-10, 10)
            y = 12
            heading = random.uniform(-20, 20)
        elif edge == "E":
            x = 12
            y = random.uniform(-10, 10)
            heading = random.uniform(250, 290)
        else:
            x = -12
            y = random.uniform(-10, 10)
            heading = random.uniform(70, 110)

        altitude = random.uniform(300, 1000)
        speed = random.uniform(250, 450)
        aircraft_id = random.choice(["AF", "LH", "EK", "BA"]) + str(random.randint(100, 9999))

        ac = Aircraft(
            id=aircraft_id,
            x=x,
            y=y,
            altitude=altitude,
            speed=speed,
            heading=heading,
            fuel=random.uniform(30, 100),
        )

        self.aircraft_list.append(ac)
        self.aircraft_added.emit(ac)
        self.event(f"{ac.id} est apparu (alt {int(ac.altitude)}m)")

    def random_event(self):
        if not self.aircraft_list:
            return
        ac = random.choice(self.aircraft_list)
        r = random.random()

        if r < 0.3:  # panne moteur
            ac.engine_failure = True
            ac.fuel *= 0.7
            ac.speed *= 0.7
            ac.status = "landing"
            self.event(f"Panne moteur : {ac.id}")

        elif r < 0.6:  # météo
            for x in random.sample(self.aircraft_list, min(3, len(self.aircraft_list))):
                x.status = "holding"
                x.weather_delay = True
            self.event("Mauvais temps : plusieurs avions mis en attente")

        elif r < 0.8:  # remise de gaz
            ac.go_around()
            self.event(f"Remise de gaz : {ac.id}")

        else:  # risque de collision
            if len(self.aircraft_list) >= 2:
                a, b = random.sample(self.aircraft_list, 2)
                a.heading += 5
                b.heading -= 5
                self.event(f"Risque de collision entre {a.id} et {b.id}")

    def event(self, text):
        self.event_signal.emit(f"[{time.strftime('%H:%M:%S')}] {text}")


# -----------------------------
# UI : éléments graphiques
# -----------------------------
class AircraftItem(QGraphicsItem):
    def __init__(self, aircraft: Aircraft, scale=1000):
        super().__init__()
        self.aircraft = aircraft
        self.scale = scale
        self.setZValue(5)

    def boundingRect(self):
        return QRectF(-10, -10, 120, 40)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.save()

        # rotation selon cap
        painter.rotate(-self.aircraft.heading)

        # dessin du point représentant l'avion
        painter.setBrush(self.aircraft.color)
        painter.drawEllipse(-6, -6, 12, 12)

        painter.restore()

        # texte à droite de l’avion
        info = f"{self.aircraft.id} | Alt {int(self.aircraft.altitude)}m | V {int(self.aircraft.speed)}"
        painter.drawText(10, 0, info)


# -----------------------------
# FENÊTRE PRINCIPALE
# -----------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simulateur ATC – Version Française")
        self.resize(1300, 800)

        self.sim = Simulation()
        self.aircraft_refs = {}

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0,0,0,0)
        self.setCentralWidget(container)

        # -------------------------
        # PANNEAU GAUCHE
        # -------------------------
        left_panel = QVBoxLayout()
        left_panel.setContentsMargins(20,20,20,20)

        self.score_label = QLabel("Score : 0")
        self.score_label.setStyleSheet("font-size: 18px; font-weight: bold; color: white;")

        self.event_list = QListWidget()
        self.event_list.setStyleSheet("background: rgba(0,0,0,0.4); color: white;")

        self.aircraft_list = QListWidget()
        self.aircraft_list.setStyleSheet("background: rgba(0,0,0,0.4); color: white;")

        left_panel.addWidget(self.score_label)
        left_panel.addWidget(QLabel("Événements :"))
        left_panel.addWidget(self.event_list)
        left_panel.addWidget(QLabel("Avions actifs :"))
        left_panel.addWidget(self.aircraft_list)

        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        left_widget.setFixedWidth(320)
        layout.addWidget(left_widget)

        # -------------------------
        # RADAR
        # -------------------------
        self.scene = QGraphicsScene(-15000, -15000, 30000, 30000)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)

        try:
            pix = QPixmap("assets/radar_background.jpg")
            if pix.isNull():
                self.view.setStyleSheet("background: black;")
            else:
                self.view.setBackgroundBrush(pix.scaled(1300,800, Qt.KeepAspectRatioByExpanding))
        except:
            self.view.setStyleSheet("background: black;")

        layout.addWidget(self.view, stretch=5)

        # -------------------------
        # PANNEAU DROIT (COMMANDES)
        # -------------------------
        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(20,20,20,20)

        self.selected_label = QLabel("Aucun avion sélectionné")
        right_panel.addWidget(self.selected_label)

        # boutons
        self.btn_climb = QPushButton("Monter")
        self.btn_descend = QPushButton("Descendre")
        self.btn_hold = QPushButton("Attente")
        self.btn_land = QPushButton("Autoriser atterrissage")
        self.btn_go_around = QPushButton("Remise de gaz")

        # cap
        right_panel.addWidget(QLabel("Changer cap :"))
        self.heading_input = QLineEdit()
        self.heading_input.setPlaceholderText("0–359°")
        self.btn_heading = QPushButton("Appliquer cap")

        for btn in [
            self.btn_climb, self.btn_descend, self.btn_hold,
            self.btn_land, self.btn_go_around,
            self.heading_input, self.btn_heading
        ]:
            right_panel.addWidget(btn)

        right_panel.addStretch()
        right_widget = QWidget()
        right_widget.setFixedWidth(300)
        right_widget.setLayout(right_panel)
        layout.addWidget(right_widget)

        ###################################
        # Connexions signaux → UI
        ###################################
        self.sim.aircraft_added.connect(self.add_aircraft)
        self.sim.aircraft_removed.connect(self.remove_aircraft)
        self.sim.aircraft_updated.connect(self.update_aircraft)
        self.sim.collision_signal.connect(self.on_collision)
        self.sim.score_updated.connect(self.update_score)
        self.sim.event_signal.connect(self.on_event)

        self.aircraft_list.itemSelectionChanged.connect(self.on_selection_changed)

        # commandes
        self.btn_climb.clicked.connect(lambda: self.issue_command("climb"))
        self.btn_descend.clicked.connect(lambda: self.issue_command("descend"))
        self.btn_hold.clicked.connect(lambda: self.issue_command("hold"))
        self.btn_land.clicked.connect(lambda: self.issue_command("land"))
        self.btn_go_around.clicked.connect(lambda: self.issue_command("go_around"))
        self.btn_heading.clicked.connect(lambda: self.issue_command("heading"))

        self.sim.start()

    ###################################
    # Mise à jour de l'UI
    ###################################

    def add_aircraft(self, ac):
        item = AircraftItem(ac)
        self.scene.addItem(item)
        self.aircraft_refs[ac.id] = item

        list_item = QListWidgetItem(ac.id)
        self.aircraft_list.addItem(list_item)

    def remove_aircraft(self, aircraft_id):
        if aircraft_id in self.aircraft_refs:
            item = self.aircraft_refs.pop(aircraft_id)
            self.scene.removeItem(item)

        for i in range(self.aircraft_list.count()):
            if self.aircraft_list.item(i).text() == aircraft_id:
                self.aircraft_list.takeItem(i)
                break

    def update_aircraft(self, ac):
        item = self.aircraft_refs.get(ac.id)
        if item:
            item.setPos(ac.x * 1000, ac.y * 1000)
            item.update()

    def on_event(self, text):
        self.event_list.insertItem(0, text)

    def on_collision(self, a, b):
        QMessageBox.critical(self, "Collision", f"{a} et {b} sont entrés en collision !")
        self.on_event(f"Collision entre {a} et {b}")

    def update_score(self, sc):
        self.score_label.setText(f"Score : {sc}")

    def on_selection_changed(self):
        items = self.aircraft_list.selectedItems()
        if not items:
            self.selected_label.setText("Aucun avion sélectionné")
            return
        ac = items[0].text()
        self.selected_label.setText(f"Avion sélectionné : {ac}")

    ###################################
    # COMMANDES UTILISATEUR
    ###################################
    def issue_command(self, cmd):
        items = self.aircraft_list.selectedItems()
        if not items:
            return

        ac_id = items[0].text()
        ac = next((x for x in self.sim.aircraft_list if x.id == ac_id), None)

        if not ac:
            return

        if cmd == "climb":
            ac.climb()
        elif cmd == "descend":
            ac.descend()
        elif cmd == "hold":
            ac.hold()
        elif cmd == "land":
            ac.authorize_landing()
        elif cmd == "go_around":
            ac.go_around()
        elif cmd == "heading":
            try:
                heading = int(self.heading_input.text())
                ac.set_heading(heading)
            except:
                pass


# -----------------------------
# FONCTION PRINCIPALE
# -----------------------------

def main():
    app = QApplication([])
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
