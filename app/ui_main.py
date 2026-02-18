import sys
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFrame, QTextEdit, QScrollArea, QSizePolicy,
    QDialog, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QFormLayout, QMessageBox, QGridLayout, QStackedLayout, QTabWidget
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QFont, QPalette, QColor, QFontDatabase

class TapeDeckUI(QMainWindow):
    # Signals for orchestration
    on_air_clicked = Signal(bool)
    rec_clicked = Signal(bool)
    channel_selected = Signal(str)
    open_folder_clicked = Signal()

    manage_channels_clicked = Signal()
    restart_clicked = Signal()
    power_clicked = Signal()

    def __init__(self, settings, channels):
        super().__init__()
        self.settings = settings
        self.channels = channels
        self.current_channel = settings.get("default_channel", "P3")
        self.layout_mode = settings.get("ui_layout", "classic")
        self.current_page = 0 # For channel grid
        self._current_breakpoint = None  # Track to avoid redundant rebuilds
        
        self.setWindowTitle("TapeDeck")
        self._load_fonts()

        if self.layout_mode == "classic":
            self.setFixedSize(960, 640)
        else:
            self.setMinimumSize(520, 480)
            self.resize(1000, 720)
            
        self.init_ui()
        self.apply_styles()

    def _load_fonts(self):
        """A1: Load Montserrat via QFontDatabase."""
        import os
        font_dir = os.path.join(os.path.dirname(__file__), "assets", "fonts")
        fonts = ["Montserrat-Regular.ttf", "Montserrat-SemiBold.ttf", "Montserrat-Bold.ttf"]
        loaded = False
        for f in fonts:
            path = os.path.join(font_dir, f)
            if os.path.exists(path):
                if QFontDatabase.addApplicationFont(path) != -1:
                    loaded = True
        
        if loaded:
            self.default_font_family = "Montserrat"
        else:
            self.default_font_family = "Segoe UI" # Fallback
        
        self.setFont(QFont(self.default_font_family, 10))

    def init_ui(self):
        # 1) Create all widgets first (Single Builder)
        self._create_widgets()
        
        # 2) Compose layout based on mode
        if self.layout_mode == "responsive":
            self._compose_responsive_layout()
        else:
            self._compose_classic_layout()

    def _create_widgets(self):
        """Unified widget creation to ensure identical functionality in all layouts."""
        # --- Top: Now Playing ---
        self.top_panel = QFrame()
        self.top_panel.setObjectName("topPanel")
        self.top_layout = QVBoxLayout(self.top_panel)
        self.top_layout.setSpacing(2)
        
        # B2: Now Playing Hierarchy (Primary Title, Secondary Station)
        self.lbl_channel_name = QLabel(f"{self.current_channel}")
        self.lbl_channel_name.setObjectName("playingChannel")
        
        self.lbl_track_artist = QLabel("Unknown")
        self.lbl_track_artist.setObjectName("trackArtist")
        
        self.lbl_track_title = QLabel("—")
        self.lbl_track_title.setObjectName("trackTitle")
        
        # In v2.0 responsive, Title is primary. Classic keeps order.
        self.top_layout.addWidget(self.lbl_track_title)
        self.top_layout.addWidget(self.lbl_track_artist)
        self.top_layout.addWidget(self.lbl_channel_name)

        # --- Middle: C3 Split Panels ---
        self.on_air_panel = QFrame()
        self.on_air_panel.setObjectName("onAirPanel")
        on_air_layout = QVBoxLayout(self.on_air_panel)
        self.btn_on_air = QPushButton("OFF AIR")
        self.btn_on_air.setCheckable(True)
        self.btn_on_air.setObjectName("onAirBtn")
        self.btn_on_air.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_on_air.clicked.connect(lambda checked: self.on_air_clicked.emit(checked))
        on_air_layout.addWidget(self.btn_on_air)
        
        self.rec_panel = QFrame()
        self.rec_panel.setObjectName("recPanel")
        self.rec_panel_layout = QVBoxLayout(self.rec_panel)
        
        self.rec_card = QFrame() # The inner card with timer
        self.rec_card.setObjectName("recCard")
        rec_card_layout = QHBoxLayout(self.rec_card)
        
        self.rec_dot = QLabel("●")
        self.rec_dot.setObjectName("recDotOff")
        
        self.lbl_rec_timer = QLabel("REC 00:00:00")
        self.lbl_rec_timer.setObjectName("recTimer")
        
        self.btn_rec = QPushButton("REC")
        self.btn_rec.setCheckable(True)
        self.btn_rec.setObjectName("recBtn")
        self.btn_rec.setEnabled(False)
        self.btn_rec.clicked.connect(lambda checked: self.rec_clicked.emit(checked))
        
        rec_card_layout.addWidget(self.rec_dot)
        rec_card_layout.addWidget(self.lbl_rec_timer)
        rec_card_layout.addStretch()
        rec_card_layout.addWidget(self.btn_rec)
        
        self.rec_panel_layout.addWidget(self.rec_card)

        # REC pulse
        self.rec_pulse_timer = QTimer()
        self.rec_pulse_timer.timeout.connect(self._toggle_rec_pulse)
        self.rec_pulse_visible = True

        # --- Channel Selector ---
        self.channel_container = QWidget()
        self.channel_buttons = []
        
        if self.layout_mode == "responsive":
            # D4: Channel Selector Grid with Pagination
            self.grid_container_layout = QVBoxLayout(self.channel_container)
            self.grid_container_layout.setContentsMargins(0, 0, 0, 0)
            
            self.grid_widget = QWidget()
            self.grid_layout = QGridLayout(self.grid_widget)
            self.grid_layout.setSpacing(10)
            
            # Pagination controls
            self.pagination_widget = QWidget()
            self.pagination_layout = QHBoxLayout(self.pagination_widget)
            self.btn_prev = QPushButton("◀ PREV")
            self.btn_next = QPushButton("NEXT ▶")
            self.lbl_page = QLabel("Page 1/1")
            self.lbl_page.setObjectName("pageLabel")
            self.pagination_layout.addStretch()
            self.pagination_layout.addWidget(self.btn_prev)
            self.pagination_layout.addWidget(self.lbl_page)
            self.pagination_layout.addWidget(self.btn_next)
            self.pagination_layout.addStretch()
            
            self.btn_prev.clicked.connect(self._prev_page)
            self.btn_next.clicked.connect(self._next_page)
            
            self.grid_container_layout.addWidget(self.grid_widget)
            self.grid_container_layout.addWidget(self.pagination_widget)
            
            self._refresh_channel_grid()

        # --- Log Panels ---
        # REC LOG
        self.rec_log_group = QWidget()
        self.rec_log_container = QVBoxLayout(self.rec_log_group)
        self.lbl_rec_title = QLabel("REC LOG")
        self.lbl_rec_title.setObjectName("logTitle")
        self.rec_log_container.addWidget(self.lbl_rec_title)
        
        self.rec_log_stack = QWidget()
        rec_log_stack_layout = QVBoxLayout(self.rec_log_stack)
        rec_log_stack_layout.setContentsMargins(0, 0, 0, 0)
        
        self.txt_rec_log = QTextEdit()
        self.txt_rec_log.setReadOnly(True)
        self.txt_rec_log.setObjectName("recLog")
        
        self.lbl_rec_placeholder = QLabel("No recording yet")
        self.lbl_rec_placeholder.setObjectName("placeholderText")
        self.lbl_rec_placeholder.setAlignment(Qt.AlignCenter)
        
        rec_log_stack_layout.addWidget(self.txt_rec_log)
        rec_log_stack_layout.addWidget(self.lbl_rec_placeholder)
        self.rec_log_container.addWidget(self.rec_log_stack)
        
        # TRACK HISTORY
        self.hist_group = QWidget()
        self.hist_container = QVBoxLayout(self.hist_group)
        self.lbl_hist_title = QLabel("TRACK HISTORY")
        self.lbl_hist_title.setObjectName("logTitle")
        self.hist_container.addWidget(self.lbl_hist_title)
        
        self.hist_stack = QWidget()
        hist_stack_layout = QVBoxLayout(self.hist_stack)
        hist_stack_layout.setContentsMargins(0, 0, 0, 0)
        
        self.txt_history = QTextEdit()
        self.txt_history.setReadOnly(True)
        self.txt_history.setObjectName("trackHistory")
        
        self.lbl_hist_placeholder = QLabel("Waiting for metadata")
        self.lbl_hist_placeholder.setObjectName("placeholderText")
        self.lbl_hist_placeholder.setAlignment(Qt.AlignCenter)
        
        hist_stack_layout.addWidget(self.txt_history)
        hist_stack_layout.addWidget(self.lbl_hist_placeholder)
        self.hist_container.addWidget(self.hist_stack)

        # --- Bottom Bar ---
        self.btn_open_folder = QPushButton("Open Folder")
        self.btn_open_folder.clicked.connect(self.open_folder_clicked.emit)
        

        
        self.btn_restart = QPushButton("Restart")
        self.btn_restart.setObjectName("restartButton")
        self.btn_restart.clicked.connect(self.restart_clicked.emit)
        
        self.btn_power = QPushButton("POWER OFF")
        self.btn_power.setObjectName("powerButton")
        self.btn_power.clicked.connect(self.power_clicked.emit)
        
        self.btn_manage_channels = QPushButton("Channels")
        self.btn_manage_channels.clicked.connect(self.manage_channels_clicked.emit)
        
        self.lbl_latency = QLabel("LATENCY: --")
        self.lbl_latency.setObjectName("latencyLabel")
        
        self.lbl_status = QLabel("STATUS: IDLE")
        self.lbl_status.setObjectName("statusLabel")

    def _compose_classic_layout(self):
        """Standard fixed 960x640 layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        main_layout.addWidget(self.top_panel)
        
        # Classic: reorder Now Playing to channel → artist → title
        while self.top_layout.count():
            self.top_layout.takeAt(0)
        self.top_layout.addWidget(self.lbl_channel_name)
        self.top_layout.addWidget(self.lbl_track_artist)
        self.top_layout.addWidget(self.lbl_track_title)

        # Classic: fixed sizes for controls
        self.btn_on_air.setFixedSize(200, 80)
        self.btn_on_air.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.rec_card.setFixedSize(250, 80)

        middle_layout = QHBoxLayout()
        middle_layout.addStretch()
        middle_layout.addWidget(self.btn_on_air)
        middle_layout.addWidget(self.rec_card)
        middle_layout.addStretch()
        main_layout.addLayout(middle_layout)

        main_layout.addWidget(self.channel_container, alignment=Qt.AlignCenter)

        self.logs_layout = QHBoxLayout()
        self.logs_layout.addWidget(self.rec_log_group, 2)
        self.logs_layout.addWidget(self.hist_group, 1)
        main_layout.addLayout(self.logs_layout)

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self.btn_open_folder)
        bottom_layout.addWidget(self.btn_restart)
        bottom_layout.addWidget(self.btn_power)
        bottom_layout.addWidget(self.btn_manage_channels)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.lbl_latency)
        bottom_layout.addWidget(self.lbl_status)
        main_layout.addLayout(bottom_layout)
        
        # Classic Specific: Build pill layout for channels
        self.channel_pills_layout = QHBoxLayout(self.channel_container)
        self.channel_pills_layout.setSpacing(10)
        self._build_channel_pills()
        for btn in self.channel_buttons:
            self.channel_pills_layout.addWidget(btn)

        self._update_placeholders()

    def _compose_responsive_layout(self):
        """Premium Responsive UI: QScrollArea + Fixed Bottom Bar."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        
        # ── Scrollable Content Area ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setObjectName("scrollArea")
        
        self.panel = QFrame()
        self.panel.setObjectName("studioPanel")
        self.panel_layout = QVBoxLayout(self.panel)
        self.panel_layout.setSpacing(16)
        self.panel_layout.setContentsMargins(28, 28, 28, 20)
        
        # Now Playing
        self.panel_layout.addWidget(self.top_panel)
        
        # Controls Container (ON AIR + REC — stacks dynamically)
        self.controls_container = QWidget()
        self.controls_layout = QHBoxLayout(self.controls_container)
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_layout.setSpacing(16)
        self.controls_layout.addWidget(self.on_air_panel, 1)
        self.controls_layout.addWidget(self.rec_panel, 1)
        self.panel_layout.addWidget(self.controls_container)

        # Channel Grid
        self.panel_layout.addWidget(self.channel_container)

        # Logs Tabs (ALWAYS below channel grid)
        self.logs_tabs = QTabWidget()
        self.logs_tabs.setObjectName("logsTabs")
        self.logs_tabs.addTab(self.rec_log_group, "REC LOG")
        self.logs_tabs.addTab(self.hist_group, "TRACK HISTORY")
        self.panel_layout.addWidget(self.logs_tabs)
        
        # Stretch at bottom so content doesn't float mid-panel
        self.panel_layout.addStretch(1)
        
        self.scroll_area.setWidget(self.panel)
        root_layout.addWidget(self.scroll_area, 1)  # Takes all available space


        # ── Fixed Bottom Bar ──
        self.bottom_bar = QFrame()
        self.bottom_bar.setObjectName("bottomBar")
        self.bottom_bar_layout = QHBoxLayout(self.bottom_bar)
        self.bottom_bar_layout.setContentsMargins(16, 8, 16, 8)
        self.bottom_bar_layout.setSpacing(10)
        self.bottom_bar_layout.addWidget(self.btn_open_folder)
        self.bottom_bar_layout.addWidget(self.btn_restart)
        self.bottom_bar_layout.addWidget(self.btn_power)
        self.bottom_bar_layout.addWidget(self.btn_manage_channels)
        self.bottom_bar_layout.addStretch()
        self.bottom_bar_layout.addWidget(self.lbl_latency)
        self.bottom_bar_layout.addWidget(self.lbl_status)
        root_layout.addWidget(self.bottom_bar, 0)  # Fixed height

        self._update_placeholders()

    def resizeEvent(self, event):
        """Triple Breakpoint: >=980 WIDE, 650-979 MEDIUM, <650 NARROW."""
        super().resizeEvent(event)
        if self.layout_mode != "responsive":
            return

        w = self.width()
        
        # Adaptive Padding
        if w >= 980:
            padding = 36
        elif w >= 650:
            padding = 24
        else:
            padding = 14
        self.panel_layout.setContentsMargins(padding, padding, padding, 12)
        self.panel_layout.setSpacing(12 if w < 650 else 16)
        
        # Panel max-width
        self.panel.setMaximumWidth(min(1200, max(500, w)))

        # Determine breakpoint
        mode = "wide" if w >= 980 else ("medium" if w >= 650 else "narrow")
        
        if mode == self._current_breakpoint:
            return  # No layout change needed
        self._current_breakpoint = mode
        
        # ── Controls Stacking ──
        # NARROW: Stack ON AIR above REC. Others side-by-side.
        stack_vertical = (mode == "narrow")
        self._swap_layout(self.controls_container,
                          [self.on_air_panel, self.rec_panel],
                          horizontal=not stack_vertical)

        # ── Channel Grid Columns ──
        cols = 5 if mode == "wide" else (4 if mode == "medium" else 2)
        if hasattr(self, "grid_layout"):
            self._refresh_channel_grid(columns=cols)

        # ── Bottom bar spacing ──
        self.bottom_bar_layout.setSpacing(6 if mode == "narrow" else 10)


    def _swap_layout(self, container, items, horizontal):
        """Replace a container's layout between QHBox and QVBox."""
        old = container.layout()
        if old:
            want = QHBoxLayout if horizontal else QVBoxLayout
            if isinstance(old, want):
                return  # Already correct
        new_layout = QHBoxLayout() if horizontal else QVBoxLayout()
        new_layout.setContentsMargins(0, 0, 0, 0)
        new_layout.setSpacing(16)
        for item in items:
            if isinstance(item, tuple):
                new_layout.addWidget(item[0], item[1])
            else:
                new_layout.addWidget(item)
        if old:
            QWidget().setLayout(old)  # Detach old layout
        container.setLayout(new_layout)

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._refresh_channel_grid()

    def _next_page(self):
        max_page = (len(self.channels["channels"]) - 1) // 20
        if self.current_page < max_page:
            self.current_page += 1
            self._refresh_channel_grid()

    def _refresh_channel_grid(self, columns=5):
        """D4: Populate 20-slot grid with pagination."""
        # Clear current grid
        for i in reversed(range(self.grid_layout.count())):
            item = self.grid_layout.itemAt(i)
            if item.widget():
                w = item.widget()
                self.grid_layout.removeWidget(w)
                w.deleteLater()
        
        self.channel_buttons.clear()
        
        all_channels = self.channels.get("channels", [])
        start_idx = self.current_page * 20
        page_channels = all_channels[start_idx:start_idx + 20]
        
        # Always 20 slots
        for i in range(20):
            row = i // columns
            col = i % columns
            
            if i < len(page_channels):
                ch = page_channels[i]
                btn = QPushButton(ch["name"])
                btn.setCheckable(True)
                btn.setObjectName("channelSlot")
                if ch["name"] == self.current_channel:
                    btn.setProperty("active", True)
                    btn.setChecked(True)
                else:
                    btn.setProperty("active", False)
                btn.clicked.connect(self._make_channel_handler(ch["name"]))
            else:
                # Placeholder slot
                btn = QPushButton("—")
                btn.setObjectName("emptySlot")
                btn.setEnabled(True) 
                btn.clicked.connect(self.manage_channels_clicked.emit)
            
            btn.setMinimumHeight(40)
            self.grid_layout.addWidget(btn, row, col)
            self.channel_buttons.append(btn)

        # Update page label
        total_pages = max(1, (len(all_channels) + 19) // 20)
        self.lbl_page.setText(f"Page {self.current_page + 1}/{total_pages}")
        self.btn_prev.setEnabled(self.current_page > 0)
        self.btn_next.setEnabled(self.current_page < total_pages - 1)
        self.pagination_widget.setVisible(total_pages > 1)

    def _build_channel_pills(self):
        """Legacy pill builder for classic mode."""
        for ch in self.channels["channels"]:
            btn = QPushButton(ch["name"])
            btn.setCheckable(True)
            btn.setObjectName("channelPill")
            if ch["name"] == self.current_channel:
                btn.setProperty("active", True)
                btn.setChecked(True)
            else:
                btn.setProperty("active", False)
            btn.clicked.connect(self._make_channel_handler(ch["name"]))
            self.channel_buttons.append(btn)

    def _make_channel_handler(self, name):
        def handler():
            if self.btn_rec.isChecked():
                self._sync_channel_selection()
                self.set_status("Stop REC before switching channel", error=True)
                return
            
            self.current_channel = name
            self._sync_channel_selection()
            self.lbl_channel_name.setText(name)
            self.channel_selected.emit(name)
        return handler

    def _sync_channel_selection(self):
        """Sync checked/active state on all visible channel buttons."""
        for btn in self.channel_buttons:
            is_active = btn.text() == self.current_channel
            btn.setChecked(is_active)
            btn.setProperty("active", is_active)
            btn.setStyle(btn.style())

    def set_active_channel(self, name):
        self.current_channel = name
        self._sync_channel_selection()
        self.lbl_channel_name.setText(name)

    def apply_styles(self):
        if self.layout_mode == "responsive":
            self._apply_warm_studio_styles()
        else:
            self._apply_classic_styles()

    def _apply_warm_studio_styles(self):
        """Advanced Responsive UI v2.0 Styling."""
        f = self.default_font_family
        style = f"""
            QMainWindow {{ background-color: #121212; color: #E0E0E0; font-family: '{f}'; }}
            QWidget {{ background-color: transparent; font-family: '{f}'; }}
            
            #studioPanel {{ 
                background: #121212;
            }}
            
            #topPanel {{ background-color: #181818; border-radius: 8px; padding: 20px; }}
            #trackTitle {{ font-size: 32px; font-weight: 700; color: #FFFFFF; line-height: 1.2; }}
            #trackArtist {{ font-size: 18px; color: #AAAAAA; font-weight: 400; }}
            #playingChannel {{ font-size: 12px; color: #666666; font-weight: 600; text-transform: uppercase; letter-spacing: 1.5px; }}
            
            #onAirPanel, #recPanel {{ background-color: #181818; border-radius: 8px; padding: 10px; }}
            
            QPushButton {{ 
                background-color: #252525; 
                border: none; 
                color: #BBBBBB; 
                padding: 12px; 
                border-radius: 4px; 
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{ background-color: #333333; color: #FFFFFF; }}
            QPushButton:checked {{ background-color: #404040; color: #FFFFFF; }}
            
            #onAirBtn {{ font-size: 24px; font-weight: 800; letter-spacing: 2px; }}
            #onAirBtn[active="true"] {{ background-color: #1B3B1B; color: #4CAF50; }}
            
            #recPanel {{ background-color: #181818; border-radius: 8px; padding: 10px; }}
            #recPanel[active="true"] {{ background-color: #1E1A1A; }}
            
            QPushButton {{ 
                background-color: #222222; 
                border: 1px solid #2A2A2A; 
                color: #888888; 
                padding: 10px; 
                border-radius: 4px; 
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{ background-color: #2A2A2A; color: #BBBBBB; }}
            QPushButton:checked {{ background-color: #333333; color: #FFFFFF; }}
            
            #onAirBtn {{ font-size: 24px; font-weight: 800; letter-spacing: 2px; padding: 16px; }}
            #onAirBtn:checked {{ background-color: #1B3B1B; color: #4CAF50; border-color: #2B4B2B; }}
            
            #recCard {{ background-color: #1c1c1c; border-radius: 6px; padding: 5px; }}
            #recDotOff {{ color: #222222; font-size: 24px; }}
            #recDotOn {{ color: #FF1744; font-size: 24px; }}
            
            #recTimer {{ font-family: 'Consolas', monospace; font-size: 18px; color: #444444; font-weight: 700; }}
            #recTimer[active="true"] {{ color: #FF1744; font-size: 21px; }}
            
            #recBtn:checked {{ color: #FF1744; background-color: #301010; border-color: #501010; }}
            
            #channelSlot {{ font-size: 10px; text-transform: uppercase; padding: 6px; letter-spacing: 0.5px; }}
            #channelSlot[active="true"] {{ background-color: #1B2B1B; color: #4CAF50; border: 1px solid #2B4B2B; }}
            #emptySlot {{ color: #333333; border: 1px dashed #222222; background: transparent; }}
            
            #pageLabel {{ color: #444444; font-size: 11px; font-weight: 600; margin: 0 10px; }}
            
            #logTitle {{ qproperty-visible: false; height: 0px; }} /* Hidden in tabbed mode */
            
            QTextEdit {{ 

                background-color: #0A0A0A; 
                border: none;
                color: #666666; 
                font-family: 'Consolas', monospace; 
                font-size: 10px; 
                padding: 8px;
            }}
            
            #restartButton, #powerButton {{ font-size: 10px; color: #444444; background: transparent; padding: 4px; text-transform: uppercase; }}
            #restartButton:hover {{ color: #888888; }}
            #powerButton:hover {{ color: #FF5252; }}
            
            #latencyLabel {{ color: #333333; font-size: 10px; font-weight: 600; }}
            #statusLabel {{ font-weight: 800; font-size: 10px; color: #444444; letter-spacing: 1px; }}
            
            #scrollArea {{ background: transparent; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ background: #121212; width: 4px; border: none; }}
            QScrollBar::handle:vertical {{ background: #222222; border-radius: 2px; }}
            
            #bottomBar {{ background-color: #0A0A0A; border-top: 1px solid #181818; }}
            
            #logsTabs {{ background: transparent; margin-top: 10px; }}
            #logsTabs::pane {{ border-top: 1px solid #181818; background: transparent; }}
            #logsTabs > QTabBar::tab {{
                background: transparent; color: #444444; border: none;
                padding: 6px 12px; font-size: 10px; font-weight: 700;
                letter-spacing: 1px; text-transform: uppercase;
                margin-right: 15px;
            }}
            #logsTabs > QTabBar::tab:selected {{ color: #BBBBBB; border-bottom: 2px solid #BBBBBB; }}
            #logsTabs > QTabBar::tab:hover {{ color: #888888; }}

        """
        self.setStyleSheet(style)

    def _apply_classic_styles(self):
        style = """
            QMainWindow { background-color: #121212; color: #e0e0e0; }
            QLabel { color: #b0b0b0; font-family: 'Segoe UI', sans-serif; }
            
            #topPanel { background-color: #1a1a1a; border-radius: 10px; padding: 20px; border: 1px solid #252525; }
            #playingChannel { font-size: 10px; font-weight: bold; color: #555; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 4px; }
            #trackArtist { font-size: 36px; font-weight: 800; color: #ffffff; line-height: 1.0; }
            #trackTitle { font-size: 20px; color: #777777; font-weight: 400; }
            
            QPushButton { background-color: #222222; border: 1px solid #333; color: #bbbbbb; padding: 8px 12px; border-radius: 5px; font-weight: 500; }
            QPushButton:hover { background-color: #2a2a2a; border-color: #444; color: #eeeeee; }
            QPushButton:pressed { background-color: #1a1a1a; }
            QPushButton:checked { background-color: #333333; border-color: #555; color: #ffffff; }
            
            #onAirBtn { font-size: 16px; font-weight: bold; letter-spacing: 1px; }
            #onAirBtn:checked { background-color: #0d4a13; color: #afffaf; border-color: #1b5e20; }
            
            #recCard { background-color: #1a1a1a; border-radius: 10px; border: 1px solid #252525; }
            #recDotOff { color: #1a1a1a; font-size: 24px; }
            #recDotOn { color: #ff1744; font-size: 24px; }
            
            #recTimer { font-family: 'Consolas', 'Courier New', monospace; font-size: 15px; color: #666; font-weight: bold; }
            
            #recBtn { font-weight: bold; padding: 5px 20px; border-radius: 4px; text-transform: uppercase; font-size: 11px; }
            #recBtn:checked { background-color: #7f0000; color: #ffcccc; border-color: #b71c1c; }
            
            #channelPill { padding: 4px 14px; border-radius: 14px; font-size: 11px; color: #555; border: 1px solid transparent; background-color: transparent; }
            #channelPill:hover { color: #888; background-color: #1a1a1a; }
            #channelPill:checked { background-color: #252525; color: #00ff00; font-weight: bold; border: 1px solid #333; }
            #channelPill[active="true"] { color: #00ff00; border: 1px solid #004400; background-color: #0a1a0a; }
            
            #logTitle { font-size: 10px; font-weight: 800; color: #333; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 2px; }
            
            QTextEdit { background-color: #080808; border: 1px solid #1a1a1a; color: #00ca00; font-family: 'Consolas', monospace; font-size: 11px; border-radius: 4px; padding: 5px; }
            #trackHistory { color: #888; }
            
            #placeholderText { color: #333; font-style: italic; font-size: 11px; }
            
            #restartButton { background-color: #222; color: #888; font-size: 10px; text-transform: uppercase; }
            #restartButton:hover { background-color: #333; color: #ccc; }
            
            #powerButton { background-color: #2a1111; color: #663333; font-size: 10px; font-weight: 800; text-transform: uppercase; border: 1px solid #331111; }
            #powerButton:hover { background-color: #441111; color: #f88; border-color: #662222; }
            
            #latencyLabel { color: #333; font-size: 10px; font-weight: bold; }
            #statusLabel { font-weight: 800; font-size: 10px; color: #444; letter-spacing: 1px; }
        """
        self.setStyleSheet(style)

    def set_on_air(self, state):
        self.btn_on_air.setChecked(state)
        self.btn_on_air.setText("ON AIR" if state else "OFF AIR")
        self.btn_rec.setEnabled(state)

    def set_rec_state(self, state):
        self.btn_rec.setChecked(state)
        self.btn_rec.setText("STOP" if state else "REC")
        
        # Update timer contrast (D)
        self.lbl_rec_timer.setProperty("active", state)
        self.lbl_rec_timer.setStyle(self.lbl_rec_timer.style())
        
        self.rec_panel.setProperty("active", state)
        self.rec_panel.setStyle(self.rec_panel.style())

        if state:
            self.rec_dot.setObjectName("recDotOn")
            self.rec_pulse_timer.start(800)
        else:
            self.rec_dot.setObjectName("recDotOff")
            self.rec_pulse_timer.stop()
            self.rec_dot.setGraphicsEffect(None) 
        
        # Force style update for the dot
        self.rec_dot.setStyle(self.rec_dot.style())

        
        # Lock/Unlock channel buttons
        for btn in self.channel_buttons:
            btn.setEnabled(not state)

    def _toggle_rec_pulse(self):
        self.rec_pulse_visible = not self.rec_pulse_visible
        if self.rec_pulse_visible:
            self.rec_dot.setStyleSheet("color: #ff1744;")
        else:
            self.rec_dot.setStyleSheet("color: #600;") # Dimm red

    def refresh_channels(self, channels):
        """Refresh channels for both grid (responsive) and pills (classic)."""
        self.channels = channels
        
        if self.layout_mode == "responsive":
            self._refresh_channel_grid()
        else:
            # Classic: rebuild pills
            for btn in self.channel_buttons:
                self.channel_pills_layout.removeWidget(btn)
                btn.deleteLater()
            self.channel_buttons.clear()
            self._build_channel_pills()
            for btn in self.channel_buttons:
                self.channel_pills_layout.addWidget(btn)
        
        # If current channel no longer exists, reset
        if not any(ch["name"] == self.current_channel for ch in self.channels.get("channels", [])):
             if self.channels.get("channels"):
                 new_ch = self.channels["channels"][0]["name"]
                 self.set_active_channel(new_ch)
                 self.channel_selected.emit(new_ch)
             else:
                 self.set_active_channel("None")
                 self.lbl_channel_name.setText("NONE")
        
    def _update_placeholders(self):
        rec_empty = self.txt_rec_log.toPlainText().strip() == ""
        self.txt_rec_log.setVisible(not rec_empty)
        self.lbl_rec_placeholder.setVisible(rec_empty)
        
        hist_empty = self.txt_history.toPlainText().strip() == ""
        self.txt_history.setVisible(not hist_empty)
        self.lbl_hist_placeholder.setVisible(hist_empty)

    def update_rec_timer(self, time_str):
        self.lbl_rec_timer.setText(f"REC {time_str}")

    def update_metadata(self, artist, title):
        self.lbl_track_artist.setText(artist)
        self.lbl_track_artist.setProperty("italic", artist == "Unknown")
        self.lbl_track_artist.setStyle(self.lbl_track_artist.style())
        
        self.lbl_track_title.setText(title)
        self.lbl_track_title.setProperty("italic", title == "—")
        self.lbl_track_title.setStyle(self.lbl_track_title.style())

    def append_rec_log(self, text):
        self.txt_rec_log.append(text)
        self._update_placeholders()

    def append_history(self, text):
        self.txt_history.append(text)
        self._update_placeholders()

    def set_status(self, text, error=False):
        color = "#ff1744" if error else "#666"
        self.lbl_status.setText(f"STATUS: {text.upper()}")
        self.lbl_status.setStyleSheet(f"color: {color};")


class ChannelManagerDialog(QDialog):
    test_url_requested = Signal(str) # Emits URL to test

    def __init__(self, channels, parent=None):
        super().__init__(parent)
        self.channels = channels.copy()
        self.setWindowTitle("Manage Channels")
        self.setFixedSize(600, 400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Name", "URL"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        
        self.load_table()
        
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add")
        self.btn_edit = QPushButton("Edit")
        self.btn_delete = QPushButton("Delete")
        self.btn_test = QPushButton("Test URL")
        self.btn_close = QPushButton("Close")
        
        self.lbl_test_result = QLabel("")
        self.lbl_test_result.setObjectName("testResult")
        
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addWidget(self.btn_test)
        btn_layout.addStretch()
        btn_layout.addWidget(self.lbl_test_result)
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)
        
        self.btn_add.clicked.connect(self.handle_add)
        self.btn_edit.clicked.connect(self.handle_edit)
        self.btn_delete.clicked.connect(self.handle_delete)
        self.btn_test.clicked.connect(self.handle_test)
        self.btn_close.clicked.connect(self.accept)
        
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #ccc; }
            QTableWidget { background-color: #121212; color: #eee; gridline-color: #333; }
            QHeaderView::section { background-color: #2a2a2a; color: #ccc; padding: 5px; border: 1px solid #333; }
            QPushButton { background-color: #2a2a2a; border: 1px solid #444; color: #ccc; padding: 5px 15px; }
            QPushButton:hover { background-color: #3a3a3a; }
            #testResult { font-weight: bold; margin-right: 10px; }
        """)

    def load_table(self):
        self.table.setRowCount(0)
        for ch in self.channels.get("channels", []):
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(ch["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(ch["url"]))

    def handle_add(self):
        name, url, ok = ChannelEditDialog.get_channel(self)
        if ok:
            if any(ch["name"] == name for ch in self.channels["channels"]):
                QMessageBox.warning(self, "Error", "Channel name must be unique.")
                return
            self.channels["channels"].append({"name": name, "url": url})
            self.load_table()

    def handle_edit(self):
        row = self.table.currentRow()
        if row < 0: return
        old_name = self.table.item(row, 0).text()
        old_url = self.table.item(row, 1).text()
        
        name, url, ok = ChannelEditDialog.get_channel(self, old_name, old_url)
        if ok:
            # Check unique if name changed
            if name != old_name and any(ch["name"] == name for ch in self.channels["channels"]):
                QMessageBox.warning(self, "Error", "Channel name must be unique.")
                return
            
            for ch in self.channels["channels"]:
                if ch["name"] == old_name:
                    ch["name"] = name
                    ch["url"] = url
                    break
            self.load_table()

    def handle_delete(self):
        row = self.table.currentRow()
        if row < 0: return
        name = self.table.item(row, 0).text()
        
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete channel '{name}'?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.channels["channels"] = [ch for ch in self.channels["channels"] if ch["name"] != name]
            self.load_table()

    def handle_test(self):
        row = self.table.currentRow()
        if row < 0: return
        url = self.table.item(row, 1).text()
        self.lbl_test_result.setText("TESTING...")
        self.lbl_test_result.setStyleSheet("color: #aaa;")
        self.test_url_requested.emit(url)

    def set_test_result(self, success):
        if success:
            self.lbl_test_result.setText("OK")
            self.lbl_test_result.setStyleSheet("color: #00ff00;")
        else:
            self.lbl_test_result.setText("FAILED")
            self.lbl_test_result.setStyleSheet("color: #ff1744;")


class ChannelEditDialog(QDialog):
    def __init__(self, parent=None, name="", url=""):
        super().__init__(parent)
        self.setWindowTitle("Edit Channel")
        self.setFixedSize(400, 150)
        layout = QFormLayout(self)
        
        self.txt_name = QLineEdit(name)
        self.txt_url = QLineEdit(url)
        
        layout.addRow("Name:", self.txt_name)
        layout.addRow("URL:", self.txt_url)
        
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Save")
        self.btn_cancel = QPushButton("Cancel")
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addRow(btn_layout)
        
        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        
        self.setStyleSheet("""
            QDialog { background-color: #252525; color: #ccc; }
            QLineEdit { background-color: #121212; color: #eee; border: 1px solid #444; padding: 5px; }
            QPushButton { background-color: #333; border: 1px solid #555; color: #ccc; padding: 5px 15px; }
        """)

    @staticmethod
    def get_channel(parent=None, name="", url=""):
        dialog = ChannelEditDialog(parent, name, url)
        if dialog.exec() == QDialog.Accepted:
            return dialog.txt_name.text().strip(), dialog.txt_url.text().strip(), True
        return "", "", False
