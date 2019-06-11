from datetime import datetime
import enum
from pathlib import Path
from typing import Any, Callable, cast, Dict, List, Optional, Tuple, Union

from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal, Qt, QEvent, pyqtBoundSignal, QTimer

from .common import Settings
from .declarative import hbox, label, Stretch, vbox


class MessageType(enum.Enum):
    INPUT = enum.auto()
    ERROR = enum.auto()
    PRINT = enum.auto()


class GenericTerminalInputBox(QtWidgets.QLineEdit):
    tab_pressed = pyqtSignal(bool)
    reset_ac_suggestions = pyqtSignal()
    reset_history_travel = pyqtSignal()
    history_up = pyqtSignal()
    history_down = pyqtSignal()

    # This has to be here, keyPressEvent does not capture tab press
    def event(self, raw_ev: QEvent) -> bool:
        if raw_ev.type() == QEvent.KeyPress:
            ev = cast(QtGui.QKeyEvent, raw_ev)
            if ev.key() == Qt.Key_Backtab \
                    and ev.modifiers() == Qt.ShiftModifier:
                self.tab_pressed.emit(True)
                return True
            elif ev.key() == Qt.Key_Tab and ev.modifiers() == Qt.NoModifier:
                self.tab_pressed.emit(False)
                return True
        return super().event(raw_ev)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.text() or event.key() in (Qt.Key_Left, Qt.Key_Right):
            QtWidgets.QLineEdit.keyPressEvent(self, event)
            self.reset_ac_suggestions.emit()
            self.reset_history_travel.emit()
        elif event.key() == Qt.Key_Up:
            self.history_up.emit()
        elif event.key() == Qt.Key_Down:
            self.history_down.emit()
        else:
            return super().keyPressEvent(event)


class GenericTerminalOutputBox(QtWidgets.QLineEdit):
    def __init__(self) -> None:
        super().__init__()
        self.animate = False
        self.timer = QTimer(self)
        self.timer.setInterval(5)
        self.timer.timeout.connect(self._add_character)
        self.buffer = ''

    def set_timer_interval(self, num: int) -> None:
        self.timer.setInterval(num)

    def _add_character(self) -> None:
        if not self.buffer:
            self.timer.stop()
            return
        super().setText(self.text() + self.buffer[0])
        self.buffer = self.buffer[1:]

    def setText(self, text: str) -> None:
        if not self.animate or not text:
            super().setText(text)
            return
        super().setText(text[0])
        if len(text) > 1:
            self.buffer = text[1:]
            self.timer.start()


class Log(QtWidgets.QScrollArea):
    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.content = QtWidgets.QFrame(self)
        self.content.setObjectName('log_container')
        self.setWidget(self.content)
        self.setWidgetResizable(True)
        self.content.setLayout(vbox(Stretch))

    def add_item(self, timestamp: datetime, msgtype: MessageType,
                 text: str) -> None:
        dt = timestamp.strftime('%H:%M:%S')
        if msgtype == MessageType.INPUT:
            return
        elif msgtype == MessageType.PRINT:
            msg = text
            name = 'log_print'
        elif msgtype == MessageType.ERROR:
            msg = f'Error: {text}'
            name = 'log_error'
        ts_lbl = label(dt, 'log_timestamp', parent=self)
        ts_lbl.setSizePolicy(QtWidgets.QSizePolicy.Maximum,
                             QtWidgets.QSizePolicy.Preferred)
        lbl = label(msg, name, word_wrap=True, parent=self)
        if self.content.layout().count() % 2 == 0:
            ts_lbl.setProperty('odd', True)
            lbl.setProperty('odd', True)
        row = hbox(ts_lbl, lbl)
        cast(QtWidgets.QVBoxLayout, self.content.layout()).addLayout(row)
        vsb = self.verticalScrollBar()

        def scroll_down(new_min: int, new_max: int) -> None:
            vsb.setValue(new_max)

        vsb.rangeChanged.connect(scroll_down)


class GenericTerminal(QtWidgets.QFrame):
    show_message = pyqtSignal(datetime, MessageType, str)

    def __init__(self,
                 parent: QtWidgets.QWidget, settings: Settings,
                 input_term_constructor: Callable[[], GenericTerminalInputBox],
                 output_term_constructor: Callable[[], GenericTerminalOutputBox],
                 help_command: str = '?', history_file: Optional[Path] = None
                 ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.help_command = help_command
        # Input field
        self.input_term = input_term_constructor()
        self.input_term.setFocus()
        cast(pyqtSignal, self.input_term.returnPressed).connect(
            self.parse_command)
        # Output field
        self.output_term = output_term_constructor()
        self.output_term.setDisabled(True)
        # Log
        self.log: List[Tuple[datetime, MessageType, str]] = []
        self.log_widget = Log(self)
        self.show_message.connect(self.log_widget.add_item)
        self.setLayout(vbox(self.log_widget, self.input_term,
                            self.output_term))
        self.log_widget.hide()
        # History
        self.history = ['']
        self.history_index = 0
        self.history_file = history_file
        if history_file is not None and history_file.exists():
            self.history.extend(
                reversed(history_file.read_text().splitlines()))
        self.input_term.reset_history_travel.connect(self.reset_history_travel)
        self.input_term.history_up.connect(self.history_up)
        self.input_term.history_down.connect(self.history_down)
        # Autocomplete
        self.ac_suggestions: List[str] = []
        self.ac_index = 0
        self.ac_reset_flag = True
        self.input_term.tab_pressed.connect(self.autocomplete)
        self.input_term.reset_ac_suggestions.connect(self.reset_ac_suggestions)
        # Each post in self.commands is (callback/signal, helptext[, options])
        # options is an optional dict with - surprise - options
        self.commands: Dict[str, Union[Tuple[Any, str],
                                       Tuple[Any, str, Dict]]] = {}
        # Settings
        settings.animate_terminal_output_changed.connect(
            self.set_animation)
        self.set_animation(settings.animate_terminal_output)
        settings.terminal_animation_interval_changed.connect(
            self.set_animation_interval)
        self.set_animation_interval(settings.terminal_animation_interval)

    def set_animation(self, animate: bool) -> None:
        self.output_term.animate = animate

    def set_animation_interval(self, interval: int) -> None:
        if interval < 1:
            self.error('Too low animation interval')
        self.output_term.set_timer_interval(max(1, interval))

    def add_to_log(self, msgtype: MessageType, msg: str) -> None:
        now = datetime.now()
        self.log.append((now, msgtype, msg))
        self.show_message.emit(now, msgtype, msg)

    def get_log(self) -> List[Tuple[datetime, MessageType, str]]:
        return self.log

    def get_formatted_log(self) -> str:
        def format_log_entry(msgtype: MessageType, msg: str) -> str:
            if msgtype == MessageType.INPUT:
                return '   >>  ' + msg
            elif msgtype == MessageType.ERROR:
                return '  <<   Error: ' + msg
            else:
                return '  <<   ' + msg
        text = '\n'.join(
            ts.strftime('%H:%M:%S') + format_log_entry(msgtype, msg)
            for ts, msgtype, msg in self.log
        )
        return text if text else '[empty log]'

    def setFocus(self) -> None:
        self.input_term.setFocus()

    def clear_input(self) -> None:
        self.input_term.setText('')

    def clear_output(self) -> None:
        self.output_term.setText('')

    def clear(self) -> None:
        self.clear_input()
        self.clear_output()

    def print_(self, msg: Any) -> None:
        self.output_term.setText(str(msg))
        self.add_to_log(MessageType.PRINT, str(msg))
        self.show()

    def error(self, msg: Any) -> None:
        self.output_term.setText(f'Error: {msg}')
        self.add_to_log(MessageType.ERROR, str(msg))
        self.show()

    def prompt(self, msg: str) -> None:
        self.input_term.setText(msg)
        self.input_term.setFocus()
        self.show()

    def command_parsing_injection(self, arg: str) -> bool:
        pass

    def parse_command(self) -> None:
        text = self.input_term.text().strip()
        if not text:
            return
        self.add_to_log(MessageType.INPUT, text)
        self.add_history(text)
        self.input_term.setText('')
        self.output_term.setText('')
        abort = self.command_parsing_injection(text)
        if abort:
            return
        command = text[0].lower()
        if command in self.commands:
            command_data = self.commands[command]
            # Keep the whitespace if the correct option is present and true
            if len(command_data) == 3 \
                    and command_data[2].get('keep whitespace', False):
                arg = text[1:]
            # Otherwise strip it away
            else:
                arg = text[1:].strip()
            # Run command
            run = self.commands[command][0]
            if isinstance(run, pyqtBoundSignal):
                run.emit(arg)
            else:
                run(arg)
        else:
            self.error(f'No such command ({self.help_command} for help)')

    # ==== History =============================== #
    def history_up(self) -> None:
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
        self.input_term.setText(self.history[self.history_index])

    def history_down(self) -> None:
        if self.history_index > 0:
            self.history_index -= 1
        self.input_term.setText(self.history[self.history_index])

    def add_history(self, text: str) -> None:
        self.history[0] = text
        self.history.insert(0, '')
        if self.history_file is not None:
            with self.history_file.open('a') as f:
                f.write(text + '\n')

    def reset_history_travel(self) -> None:
        self.history_index = 0
        self.history[self.history_index] = self.input_term.text()

    # ==== Autocomplete ========================== #
    def autocomplete(self, reverse: bool) -> None:
        """
        Main autocomplete functions.
        Is called whenever tab is pressed.
        """
        pass

    def run_autocompletion(self, text: str, reverse: bool) -> str:
        # Generate new suggestions if none exist
        if not self.ac_suggestions:
            self.ac_suggestions = self.get_ac_suggestions(text)

        # If there's only one possibility, set it and move on
        if len(self.ac_suggestions) == 1:
            text = self.ac_suggestions[0]
            self.reset_ac_suggestions()
        # Otherwise start scrolling through 'em
        elif self.ac_suggestions:
            if self.ac_reset_flag:
                if reverse:
                    self.ac_index = len(self.ac_suggestions)-1
                self.ac_reset_flag = False
            else:
                if reverse:
                    self.ac_index -= 1
                    if self.ac_index == -1:
                        self.ac_index = len(self.ac_suggestions)-1
                else:
                    self.ac_index += 1
                    if self.ac_index == len(self.ac_suggestions):
                        self.ac_index = 0
            text = self.ac_suggestions[self.ac_index]
        return text

    def get_ac_suggestions(self, prefix: str) -> List[str]:
        return []

    def reset_ac_suggestions(self) -> None:
        """
        Reset the list of suggestions if another button than tab
        has been pressed.
        """
        self.ac_suggestions = []
        self.ac_index = 0
        self.ac_reset_flag = True

    # ==== Useful commands ======================= #
    def cmd_help(self, arg: str) -> None:
        if not arg:
            self.print_(' '.join(sorted(self.commands)))
        elif arg in self.commands:
            self.print_(self.commands[arg][1])
        else:
            self.error('No such command')

    def cmd_toggle_log(self, arg: str) -> None:
        if arg:
            self.error('Toggle log does not take any arguments')
        else:
            self.log_widget.setVisible(not self.log_widget.isVisible())
