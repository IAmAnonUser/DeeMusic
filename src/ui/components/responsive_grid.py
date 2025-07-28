"""
Responsive grid layout component for DeeMusic.
Automatically adjusts the number of columns based on available width.
"""

from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QSizePolicy, QScrollArea
from PyQt6.QtCore import Qt, QTimer
import logging

logger = logging.getLogger(__name__)

class ResponsiveScrollArea(QScrollArea):
    """A QScrollArea that properly propagates resize events to its widget for responsive behavior."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
    def resizeEvent(self, event):
        """Override resize event to force the contained widget to resize immediately."""
        super().resizeEvent(event)
        
        # Force the widget to update its size immediately
        if self.widget():
            widget = self.widget()
            if hasattr(widget, 'updateGeometry'):
                # Calculate the available size for the widget (use viewport width)
                available_width = self.viewport().width()
                
                # If it's a ResponsiveGridWidget, trigger immediate relayout with correct width
                if isinstance(widget, ResponsiveGridWidget):
                    # Pass the correct available width to the grid
                    widget._force_immediate_relayout_with_width(available_width)
                else:
                    widget.updateGeometry()

class ResponsiveGridWidget(QWidget):
    """A widget that automatically adjusts grid columns based on available width."""
    
    def __init__(self, card_min_width=180, card_spacing=15, parent=None):
        super().__init__(parent)
        
        self.card_min_width = card_min_width  # Minimum width per card
        self.card_spacing = card_spacing      # Spacing between cards
        self.cards = []                       # Store all cards
        
        # Set size policy to allow shrinking
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        
        # Create main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Create grid widget and layout
        self.grid_widget = QWidget()
        # Set size policy to allow shrinking for the grid widget too
        self.grid_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setSpacing(self.card_spacing)
        
        self.main_layout.addWidget(self.grid_widget)
        self.main_layout.addStretch(1)
        
        # Track current column count
        self.current_columns = 0
        
        # Timer for debounced resize handling
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._relayout_cards)
        
        # Override width for scroll area scenarios
        self._override_width = None
        
    def _force_immediate_relayout(self):
        """Force an immediate relayout without debouncing - used by ResponsiveScrollArea."""
        logger.debug("ResponsiveGrid: Force immediate relayout requested")
        self._resize_timer.stop()  # Cancel any pending relayout
        self._relayout_cards()  # Do it now
        
    def _force_immediate_relayout_with_width(self, available_width):
        """Force an immediate relayout with a specific width override."""
        logger.debug(f"ResponsiveGrid: Force immediate relayout requested with width override: {available_width}")
        self._override_width = available_width
        self._resize_timer.stop()  # Cancel any pending relayout
        self._relayout_cards()  # Do it now
        self._override_width = None  # Clear override after use

    def add_card(self, card_widget):
        """Add a card to the responsive grid."""
        self.cards.append(card_widget)
        self._relayout_cards()
        
    def clear_cards(self):
        """Remove all cards from the grid."""
        for card in self.cards:
            self.grid_layout.removeWidget(card)
            card.setParent(None)
        self.cards.clear()
        self.current_columns = 0
        
        # Clear all column stretches when clearing cards
        self._clear_all_column_stretches()
        
    def set_cards(self, card_widgets):
        """Set all cards at once (more efficient than adding one by one)."""
        self.clear_cards()
        self.cards = card_widgets.copy()
        self._relayout_cards()
        
    def _calculate_optimal_columns(self, available_width):
        """Calculate the optimal number of columns based on available width."""
        if available_width <= 0:
            return 1
            
        # Account for layout margins and spacing
        margins = self.grid_layout.contentsMargins()
        effective_width = available_width - margins.left() - margins.right()
        
        logger.debug(f"ResponsiveGrid: Calculating columns for width={available_width}, effective={effective_width}, margins={margins.left()}+{margins.right()}")
        
        if effective_width <= self.card_min_width:
            logger.debug(f"ResponsiveGrid: Width too small ({effective_width} <= {self.card_min_width}), using 1 column")
            return 1
            
        # Calculate how many cards can fit with spacing
        # Formula: (n * card_width) + ((n-1) * spacing) <= effective_width
        # Solving for n: n <= (effective_width + spacing) / (card_width + spacing)
        max_columns = max(1, int((effective_width + self.card_spacing) / (self.card_min_width + self.card_spacing)))
        
        # Don't exceed the number of cards we have
        final_columns = min(max_columns, len(self.cards)) if self.cards else max_columns
        
        logger.debug(f"ResponsiveGrid: max_columns={max_columns}, cards={len(self.cards) if self.cards else 0}, final={final_columns}")
        
        return final_columns
    
    def _clear_all_column_stretches(self):
        """Clear all column stretch factors to ensure proper resizing."""
        # Clear stretches for all possible columns (generous upper bound)
        for i in range(50):  # Assume we'll never have more than 50 columns
            self.grid_layout.setColumnStretch(i, 0)
        
    def _relayout_cards(self):
        """Relayout all cards in the grid based on current width."""
        if not self.cards:
            return
            
        # Use override width if available (from scroll area), otherwise use widget width
        available_width = self._override_width if self._override_width is not None else self.width()
        if available_width <= 0:
            # If width is not available yet, defer the layout
            logger.debug("ResponsiveGrid: Width not available yet, deferring layout")
            return
            
        optimal_columns = self._calculate_optimal_columns(available_width)
        
        # Always relayout if columns changed, regardless of count (force update)
        if optimal_columns == self.current_columns and self.grid_layout.count() == len(self.cards):
            logger.debug(f"ResponsiveGrid: No change needed (columns={optimal_columns}, widgets={self.grid_layout.count()})")
            return
            
        logger.debug(f"ResponsiveGrid: Relaying cards with {optimal_columns} columns (was {self.current_columns})")
        
        # Clear all column stretches first to ensure clean state
        self._clear_all_column_stretches()
        
        # Remove all cards from layout (but keep them in self.cards)
        for card in self.cards:
            self.grid_layout.removeWidget(card)
            
        # Add cards back in new grid arrangement
        row, col = 0, 0
        for card in self.cards:
            self.grid_layout.addWidget(card, row, col)
            col += 1
            if col >= optimal_columns:
                col = 0
                row += 1
                
        self.current_columns = optimal_columns
        
        # Set column stretch to make cards expand evenly (only for active columns)
        for i in range(optimal_columns):
            self.grid_layout.setColumnStretch(i, 1)
        
        # Force geometry update to ensure proper resizing
        self.grid_widget.updateGeometry()
        self.updateGeometry()
        
        # Force immediate layout processing
        self.grid_widget.layout().update()
        self.layout().update()
        
        # Force a repaint to ensure visual update
        self.update()
        self.grid_widget.update()
            
    def resizeEvent(self, event):
        """Handle resize events to trigger relayout."""
        super().resizeEvent(event)
        
        # Log resize events for debugging
        old_width = event.oldSize().width() if event.oldSize().isValid() else 0
        new_width = event.size().width()
        logger.debug(f"ResponsiveGrid: Resize event {old_width} -> {new_width}")
        
        # Use a debounced approach to avoid excessive relayouts during window dragging
        # Check if we're in the main thread before using timer
        from PyQt6.QtCore import QThread
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and QThread.currentThread() == app.thread():
            self._resize_timer.stop()
            self._resize_timer.start(50)  # 50ms delay
        else:
            # We're in a worker thread, relayout immediately
            self._relayout_cards()
        
    def showEvent(self, event):
        """Handle show events to ensure proper layout."""
        super().showEvent(event)
        # Use a longer delay to allow page navigation to complete first
        if self.cards:
            # Check if we're in the main thread before using QTimer
            from PyQt6.QtCore import QThread
            from PyQt6.QtWidgets import QApplication
            # Check if we have a QApplication and are in the main thread
            app = QApplication.instance()
            if app and QThread.currentThread() == app.thread():
                QTimer.singleShot(100, self._relayout_cards)  # Reduced delay for better responsiveness
            else:
                # We're in a worker thread, relayout immediately
                self._relayout_cards() 