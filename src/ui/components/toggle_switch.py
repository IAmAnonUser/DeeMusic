"""
Custom Toggle Switch widget for DeeMusic.
"""

from PyQt6.QtWidgets import QCheckBox, QLabel, QHBoxLayout, QWidget
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFontMetrics

class ToggleSwitch(QWidget):
    """
    A custom toggle switch widget.
    It includes a label on the left and a QCheckBox styled as a switch on the right.
    """
    toggled = pyqtSignal(bool)

    def __init__(self, text="Dark Mode", parent=None):
        super().__init__(parent)
        self._is_on = False

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8) # Spacing between label and switch

        self.label = QLabel(text)
        self.label.setObjectName("ToggleSwitchLabel")

        self.switch = QCheckBox()
        self.switch.setObjectName("ToggleSwitchNative") # Use object name for QSS
        self.switch.setFocusPolicy(Qt.FocusPolicy.NoFocus) # Avoids focus rectangle
        self.switch.toggled.connect(self._on_internal_toggled)

        self.layout.addWidget(self.label)
        self.layout.addWidget(self.switch)

        # Set initial state (will be styled by QSS)
        self._update_visual_state()

    def _on_internal_toggled(self, checked):
        self._is_on = checked
        self._update_visual_state()
        self.toggled.emit(self._is_on)

    def isOn(self) -> bool:
        return self._is_on

    def setOn(self, is_on: bool, emit_signal=False):
        """Set the state of the switch."""
        if self._is_on != is_on:
            self._is_on = is_on
            self.switch.setChecked(is_on) # This will trigger _on_internal_toggled if state changes
            if not emit_signal: # Prevent double emission if setChecked already emitted
                 self._update_visual_state() 
            # If setChecked didn't emit (because state was already correct), but we want to force an emit:
            # This case is tricky. Usually setOn is for programmatic changes.
            # For now, assume setChecked handles signal emission correctly.

    def _update_visual_state(self):
        """
        Updates visual properties based on state.
        Actual appearance is mostly driven by QSS targeting the objectName.
        """
        # This method can be used if any non-QSS updates are needed
        pass

    def sizeHint(self) -> QSize:
        # Provide a reasonable size hint based on label and switch
        label_fm = QFontMetrics(self.label.font())
        label_width = label_fm.horizontalAdvance(self.label.text())
        label_height = label_fm.height()

        # Approximate switch size (QSS will define actual size)
        switch_width = 50 
        switch_height = 26

        width = label_width + self.layout.spacing() + switch_width
        height = max(label_height, switch_height)
        
        return QSize(width + 10, height + 4) # Add some padding

if __name__ == '__main__':
    from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout
    import sys

    app = QApplication(sys.argv)
    window = QMainWindow()
    central_widget = QWidget()
    layout = QVBoxLayout(central_widget)
    window.setCentralWidget(central_widget)

    toggle1 = ToggleSwitch("Dark Mode")
    toggle1.toggled.connect(lambda on: print(f"Toggle 1: {'On' if on else 'Off'}"))
    
    toggle2 = ToggleSwitch("Enable Feature X")
    toggle2.setOn(True) # Start in 'on' state
    toggle2.toggled.connect(lambda on: print(f"Toggle 2: {'On' if on else 'Off'}"))

    layout.addWidget(toggle1)
    layout.addWidget(toggle2)
    
    # Basic QSS for testing the QCheckBox styling approach
    app.setStyleSheet("""
        ToggleSwitchNative::groove {{
            background-color: #E0E0E0; /* Light grey track */
            border-radius: 13px;
            height: 26px;
            width: 50px;
        }}
        ToggleSwitchNative::indicator {{
            background-color: white;
            border: 1px solid #CCCCCC;
            border-radius: 11px; /* Makes it circular */
            width: 22px; /* Size of the knob */
            height: 22px;
            margin: 2px; /* Margin within the groove */
        }}
        ToggleSwitchNative::indicator:checked {{
            margin-left: 26px; /* Moves knob to the right when checked */
        }}
        ToggleSwitchNative[isChecked="true"]::groove {{ /* This custom property might not work directly, use :checked */
             background-color: #A238FF; /* Purple track when on */
        }}
        ToggleSwitchNative::groove:checked {{ /* Correct pseudo-state */
             background-color: #A238FF; /* Purple track when on */
        }}
    """)

    window.resize(300, 200)
    window.show()
    sys.exit(app.exec()) 