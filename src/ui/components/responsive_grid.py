"""
Responsive grid layout component for DeeMusic.
Automatically adjusts the number of columns based on available width.
"""

from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QSizePolicy
from PyQt6.QtCore import Qt
import logging

logger = logging.getLogger(__name__)

class ResponsiveGridWidget(QWidget):
    """A widget that automatically adjusts grid columns based on available width."""
    
    def __init__(self, card_min_width=180, card_spacing=15, parent=None):
        super().__init__(parent)
        
        self.card_min_width = card_min_width  # Minimum width per card
        self.card_spacing = card_spacing      # Spacing between cards
        self.cards = []                       # Store all cards
        
        # Create main layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Create grid widget and layout
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setSpacing(self.card_spacing)
        
        self.main_layout.addWidget(self.grid_widget)
        self.main_layout.addStretch(1)
        
        # Track current column count
        self.current_columns = 0
        
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
        
        if effective_width <= self.card_min_width:
            return 1
            
        # Calculate how many cards can fit with spacing
        # Formula: (n * card_width) + ((n-1) * spacing) <= effective_width
        # Solving for n: n <= (effective_width + spacing) / (card_width + spacing)
        max_columns = max(1, int((effective_width + self.card_spacing) / (self.card_min_width + self.card_spacing)))
        
        # Don't exceed the number of cards we have
        return min(max_columns, len(self.cards)) if self.cards else max_columns
        
    def _relayout_cards(self):
        """Relayout all cards in the grid based on current width."""
        if not self.cards:
            return
            
        available_width = self.width()
        if available_width <= 0:
            # If width is not available yet, defer the layout
            return
            
        optimal_columns = self._calculate_optimal_columns(available_width)
        
        # Only relayout if column count changed
        if optimal_columns == self.current_columns and self.grid_layout.count() == len(self.cards):
            return
            
        logger.debug(f"ResponsiveGrid: Relaying cards with {optimal_columns} columns (was {self.current_columns})")
        
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
        
        # Set column stretch to make cards expand evenly
        for i in range(optimal_columns):
            self.grid_layout.setColumnStretch(i, 1)
            
        # Clear any extra column stretches from previous layouts
        for i in range(optimal_columns, self.grid_layout.columnCount()):
            self.grid_layout.setColumnStretch(i, 0)
            
    def resizeEvent(self, event):
        """Handle resize events to trigger relayout."""
        super().resizeEvent(event)
        self._relayout_cards()
        
    def showEvent(self, event):
        """Handle show events to ensure proper layout."""
        super().showEvent(event)
        # Use a small delay to ensure the widget has its final size
        if self.cards:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(10, self._relayout_cards) 