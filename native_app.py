import os
import sys
import threading

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

os.environ["JARVIS_TTS_SILENT"] = "1"

from brain import (
    clear_pending_safe,
    execute_pending_safe,
    get_conversation_context,
    get_provider_status_summary,
    has_pending_safe,
    process,
)
from brain import init as brain_init
from terminal import InputMode, extract_problems

DEBUG = os.getenv("JARVIS_DEBUG", "0").lower() in ("1", "true", "yes", "on")


class BrainWorker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._pending = None
        self._thread = None

    def submit(self, text: str):
        with self._lock:
            self._pending = text
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self):
        while True:
            with self._lock:
                if self._pending is None:
                    return
                text = self._pending
                self._pending = None
            try:
                reply = process(text)
                self.finished.emit(reply)
            except Exception as e:
                self.error.emit(str(e))


class JarvisMainWindow(QMainWindow):
    MODE_MAP = {
        "Text": InputMode.TEXT,
        "Paste": InputMode.PASTE,
        "Queue": InputMode.QUEUE,
    }

    MODE_REVERSE = {v: k for k, v in MODE_MAP.items()}

    def __init__(self):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S.")
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)

        self._worker = BrainWorker()
        self._worker.finished.connect(self._on_reply)
        self._worker.error.connect(self._on_error)

        self._mode = InputMode.TEXT
        self._queue_items: list[str] = []
        self._confirm_text = ""
        self._confirm_callback = None

        self._init_ui()
        self._create_menus()
        self._create_shortcuts()
        self._init_timer()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._create_toolbar()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_label = QLabel("Conversation")
        left_label.setStyleSheet("font-weight: 600; font-size: 13px; color: #666;")
        left_layout.addWidget(left_label)
        self._conversation = QTextEdit()
        self._conversation.setReadOnly(True)
        self._conversation.setStyleSheet("""
            QTextEdit {
                background: #1e1e1e; color: #d4d4d4;
                font-family: 'SF Mono', 'Menlo', monospace;
                font-size: 13px; border: 1px solid #333;
                border-radius: 4px; padding: 8px;
            }
        """)
        left_layout.addWidget(self._conversation, 1)
        splitter.addWidget(left_widget)

        right_panel = QTabWidget()
        right_panel.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #ccc; border-radius: 4px; }
            QTabBar::tab { padding: 6px 16px; min-width: 60px; }
        """)

        queue_tab = self._create_queue_tab()
        right_panel.addTab(queue_tab, "Queue")

        context_tab = self._create_context_tab()
        right_panel.addTab(context_tab, "Context")

        splitter.addWidget(right_panel)
        splitter.setSizes([600, 300])

        input_area = QWidget()
        input_layout = QHBoxLayout(input_area)
        input_layout.setContentsMargins(8, 6, 8, 8)

        self._input = QTextEdit()
        self._input.setPlaceholderText("Type a message...")
        self._input.setMaximumHeight(80)
        self._input.setStyleSheet("""
            QTextEdit {
                background: #252526; color: #d4d4d4;
                font-family: 'SF Mono', 'Menlo', monospace;
                font-size: 13px; border: 1px solid #3c3c3c;
                border-radius: 4px; padding: 6px;
            }
        """)
        input_layout.addWidget(self._input, 1)

        self._send_btn = QPushButton("Send")
        self._send_btn.setMinimumWidth(80)
        self._send_btn.setMinimumHeight(32)
        self._send_btn.setStyleSheet("""
            QPushButton {
                background: #0078d4; color: white; font-weight: 600;
                border: none; border-radius: 4px; padding: 6px 16px;
            }
            QPushButton:hover { background: #1a8ad4; }
            QPushButton:pressed { background: #0069b4; }
        """)
        self._send_btn.clicked.connect(self._on_send)
        input_layout.addWidget(self._send_btn)

        main_layout.addWidget(input_area)

        self._status = QStatusBar()
        self._status.showMessage("Ready")
        self.setStatusBar(self._status)

    def _create_toolbar(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        mode_label = QLabel("Mode:")
        mode_label.setStyleSheet("font-weight: 600; margin-right: 4px;")
        toolbar.addWidget(mode_label)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Text", "Paste", "Queue"])
        self._mode_combo.setMinimumWidth(120)
        self._mode_combo.setStyleSheet("""
            QComboBox {
                padding: 4px 8px; border: 1px solid #ccc;
                border-radius: 4px; min-height: 24px;
            }
        """)
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)
        toolbar.addWidget(self._mode_combo)

        toolbar.addSeparator()

        self._detection_badge = QLabel("")
        self._detection_badge.setStyleSheet("""
            QLabel {
                background: #ffd700; color: #333;
                padding: 2px 10px; border-radius: 10px;
                font-weight: 600; font-size: 12px;
            }
        """)
        self._detection_badge.setVisible(False)
        toolbar.addWidget(self._detection_badge)

        toolbar.addSeparator()

        self._context_indicator = QLabel("State: idle")
        self._context_indicator.setStyleSheet("color: #888; font-size: 12px; padding: 2px 8px;")
        toolbar.addWidget(self._context_indicator)

    def _create_queue_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)

        self._queue_list = QListWidget()
        self._queue_list.setStyleSheet("""
            QListWidget {
                background: #1e1e1e; color: #d4d4d4;
                font-family: 'SF Mono', 'Menlo', monospace;
                font-size: 12px; border: 1px solid #333;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self._queue_list, 1)

        btn_layout = QHBoxLayout()
        self._execute_btn = QPushButton("Execute All")
        self._execute_btn.clicked.connect(self._on_execute_queue)
        btn_layout.addWidget(self._execute_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._on_clear_queue)
        btn_layout.addWidget(self._clear_btn)

        layout.addLayout(btn_layout)
        return tab

    def _create_context_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)

        self._context_text = QPlainTextEdit()
        self._context_text.setReadOnly(True)
        self._context_text.setStyleSheet("""
            QPlainTextEdit {
                background: #1e1e1e; color: #d4d4d4;
                font-family: 'SF Mono', 'Menlo', monospace;
                font-size: 12px; border: 1px solid #333;
                border-radius: 4px; padding: 6px;
            }
        """)
        layout.addWidget(self._context_text, 1)
        return tab

    def _create_menus(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        edit_menu = menubar.addMenu("Edit")
        clear_action = QAction("Clear Conversation", self)
        clear_action.triggered.connect(self._on_clear_conversation)
        edit_menu.addAction(clear_action)

        modes_menu = menubar.addMenu("Modes")
        for name in ["Text", "Paste", "Queue"]:
            action = QAction(name, self)
            action.triggered.connect(lambda checked, n=name: self._set_mode_from_menu(n))
            modes_menu.addAction(action)

        queue_menu = menubar.addMenu("Queue")
        execute_action = QAction("Execute All", self)
        execute_action.setShortcut("Ctrl+Return")
        execute_action.triggered.connect(self._on_execute_queue)
        queue_menu.addAction(execute_action)

        clear_queue_action = QAction("Clear Queue", self)
        clear_queue_action.setShortcut("Ctrl+K")
        clear_queue_action.triggered.connect(self._on_clear_queue)
        queue_menu.addAction(clear_queue_action)

        help_menu = menubar.addMenu("Help")
        about_action = QAction("About Jarvis", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _create_shortcuts(self):
        QAction("Send", self, shortcut="Ctrl+Return", triggered=self._on_send)
        QAction("Send", self, shortcut="Meta+Return", triggered=self._on_send)

    def _init_timer(self):
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tick(self):
        ctx = get_conversation_context()
        if ctx is None:
            self._context_indicator.setText("State: initializing...")
            self._context_text.setPlainText("Context system not yet initialized.")
            return
        state = ctx.get("state", "idle").upper()
        self._context_indicator.setText(f"State: {state}")

        context_info = (
            f"State: {ctx.get('state', '?')}\n"
            f"Problem: {str(ctx.get('last_problem') or '')[:200] or 'none'}\n"
            f"Solution: {str(ctx.get('last_solution') or '')[:200] or 'none'}\n"
            f"Intent: {ctx.get('last_intent', '?')}\n"
            f"Provider: {ctx.get('last_provider', '?')}\n"
            f"Tools: {', '.join(ctx.get('last_tools', [])) or 'none'}\n"
            f"Fragment awaiting: {ctx.get('fragment_awaiting_context', False)}"
        )
        self._context_text.setPlainText(context_info)

    def _on_mode_changed(self, mode_name: str):
        self._mode = self.MODE_MAP.get(mode_name, InputMode.TEXT)
        self._status.showMessage(f"Mode: {mode_name}", 3000)

        if self._mode == InputMode.PASTE:
            self._input.setPlaceholderText("Paste content here. Empty line to send.")
        elif self._mode == InputMode.QUEUE:
            self._input.setPlaceholderText("Type to queue. Press Execute All to run.")
        else:
            self._input.setPlaceholderText("Type a message...")

    def _set_mode_from_menu(self, name: str):
        idx = self._mode_combo.findText(name)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)

    def _on_send(self):
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()

        if self._mode == InputMode.PASTE:
            self._handle_paste(text)
        elif self._mode == InputMode.QUEUE:
            self._handle_queue(text)
        else:
            self._send_to_brain(text)

    def _handle_paste(self, text: str):
        problems = extract_problems(text)
        if len(problems) >= 2:
            self._detection_badge.setText(f"{len(problems)} problems detected")
            self._detection_badge.setVisible(True)
            strategy, selected = self._prompt_strategy(len(problems))
            if strategy:
                self._execute_multi_problem(problems, strategy, selected)
            else:
                self._status.showMessage("Cancelled", 2000)
        else:
            self._detection_badge.setVisible(False)
            self._send_to_brain(text)

    def _handle_queue(self, text: str):
        if text.lower() in ("go", "run", "execute"):
            self._on_execute_queue()
            return
        if text.lower() == "clear":
            self._on_clear_queue()
            return
        self._queue_items.append(text)
        item = QListWidgetItem(f"{len(self._queue_items)}. {text[:80]}")
        self._queue_list.addItem(item)
        self._status.showMessage(f"Queued ({len(self._queue_items)} items)", 2000)

    def _send_to_brain(self, text: str):
        self._append_conversation("You", text)
        self._send_btn.setEnabled(False)
        self._send_btn.setText("...")
        self._status.showMessage("Thinking...")
        self._worker.submit(text)

    def _on_reply(self, reply: str):
        self._append_conversation("Jarvis", reply)
        self._send_btn.setEnabled(True)
        self._send_btn.setText("Send")
        usage = get_provider_status_summary()
        self._status.showMessage(usage if usage else "Ready")

        if has_pending_safe():
            self._show_confirmation_dialog()

    def _on_error(self, error: str):
        self._append_conversation("Error", error)
        self._send_btn.setEnabled(True)
        self._send_btn.setText("Send")
        self._status.showMessage("Error occurred", 5000)

    def _append_conversation(self, role: str, text: str):
        cursor = self._conversation.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        color = "#569cd6" if role == "You" else "#ce9178"
        prefix = f'<b style="color:{color}">{role}:</b> '
        formatted = f"{prefix}{text.replace(chr(10), '<br>')}<br><br>"
        cursor.insertHtml(formatted)
        self._conversation.setTextCursor(cursor)

    def _show_confirmation_dialog(self):
        ctx = get_conversation_context()
        problem = ctx.get("last_problem", "")[:100]
        msg = QMessageBox(self)
        msg.setWindowTitle("Jarvis — Confirmation Needed")
        msg.setText("Do you want to proceed?")
        msg.setInformativeText(f"Context: {problem}" if problem else "")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)

        result = msg.exec()
        if result == QMessageBox.StandardButton.Yes:
            reply = execute_pending_safe()
            if reply:
                self._append_conversation("Jarvis", str(reply))
        else:
            clear_pending_safe()
            self._append_conversation("Jarvis", "Okay, cancelled.")

    def _prompt_strategy(self, count: int):
        dialog = QDialog(self)
        dialog.setWindowTitle("Multi-Problem Detection")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout(dialog)

        label = QLabel(f"Detected {count} problems. How should I proceed?")
        label.setStyleSheet("font-size: 14px; font-weight: 600; margin-bottom: 8px;")
        layout.addWidget(label)

        self._strategy_var = "1"

        def make_choice(v):
            self._strategy_var = v
            dialog.accept()

        strategies = [
            ("1", "Sequential — ask before each"),
            ("2", "Auto — solve all without asking"),
            ("3", "Pick — select which to solve"),
            ("4", "First — solve only the first"),
        ]
        for value, desc in strategies:
            btn = QPushButton(f"[{value}] {desc}")
            btn.clicked.connect(lambda checked, v=value: make_choice(v))
            layout.addWidget(btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        layout.addWidget(cancel_btn)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            choice = self._strategy_var
            selected = None
            if choice == "3":
                picks, ok = QInputDialog.getText(
                    self, "Pick Problems",
                    "Problem numbers (e.g. 1,3,5):"
                )
                if ok and picks:
                    try:
                        selected = [int(x.strip()) for x in picks.split(",") if x.strip().isdigit()]
                    except (ValueError, TypeError):
                        pass
            return choice, selected
        return None, None

    def _execute_multi_problem(self, problems: list[str], strategy: str, selected: list[int] | None):
        if strategy == "pick" and selected:
            indices = [i - 1 for i in selected if 1 <= i <= len(problems)]
        elif strategy == "4":
            indices = [0]
        elif strategy in ("2", "auto"):
            indices = list(range(len(problems)))
        else:
            indices = list(range(len(problems)))

        for idx in indices:
            problem = problems[idx]
            preview = f"[{idx+1}/{len(problems)}] {problem[:100]}..."
            self._append_conversation("System", preview)

            if strategy in ("1", "sequential", "3", "pick") and strategy != "2":
                msg = QMessageBox(self)
                msg.setWindowTitle(f"Problem {idx+1}")
                msg.setText(f"Solve problem {idx+1}?")
                msg.setInformativeText(problem[:200])
                msg.setIcon(QMessageBox.Icon.Question)
                msg.setStandardButtons(
                    QMessageBox.StandardButton.Yes |
                    QMessageBox.StandardButton.No |
                    QMessageBox.StandardButton.Ignore
                )
                msg.button(QMessageBox.StandardButton.Ignore).setText("All")
                result = msg.exec()
                if result == QMessageBox.StandardButton.No:
                    self._append_conversation("System", "Skipped.")
                    continue
                elif result == QMessageBox.StandardButton.Ignore:
                    strategy = "2"

            self._send_to_brain(problem)

    def _on_execute_queue(self):
        if not self._queue_items:
            self._status.showMessage("Queue is empty", 2000)
            return
        items = list(self._queue_items)
        self._queue_items.clear()
        self._queue_list.clear()
        self._status.showMessage(f"Executing {len(items)} items...")
        for item in items:
            self._send_to_brain(item)

    def _on_clear_queue(self):
        self._queue_items.clear()
        self._queue_list.clear()
        self._status.showMessage("Queue cleared", 2000)

    def _on_clear_conversation(self):
        self._conversation.clear()
        self._status.showMessage("Conversation cleared", 2000)

    def _on_about(self):
        QMessageBox.about(
            self, "About Jarvis",
            "J.A.R.V.I.S. — AI Personal Assistant\n"
            "macOS Native App\n\n"
            "Mode: Text / Paste / Queue\n"
            "Multi-problem detection\n"
            "Interrupt confirmation"
        )

    def closeEvent(self, event):
        from tts import speak, wait_for_speech
        speak("Goodbye.")
        wait_for_speech()
        event.accept()


class JarvisApp:
    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setApplicationName("Jarvis")
        self._app.setOrganizationName("Jarvis")
        self._window = None

    def run(self):
        brain_init()
        self._window = JarvisMainWindow()
        self._window.show()
        sys.exit(self._app.exec())


if __name__ == "__main__":
    app = JarvisApp()
    app.run()
