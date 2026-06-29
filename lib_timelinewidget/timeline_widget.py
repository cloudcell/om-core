"""Timeline Widget - Pure presentation layer.

Uses TimelineEngine for all data/logic operations.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from .models import SnapshotInfo, SnapshotType
from .engine import TimelineEngine
from .timelineconf import (
    TIMELINE_ROOT_OVERRIDE,
    TIMELINE_ROOT_COLOUR,
    TIMELINE_LINE_THICKNESS_OVERRIDE,
    TIMELINE_LINE_THICKNESS,
    TIMELINE_NODE_SIZE_OVERRIDE,
    TIMELINE_NODE_SIZE,
    TIMELINE_SINGLE_BRANCH_ONLY,
    TIMELINE_ANIMATE_TRANSITIONS,
    TIMELINE_DEBUG_TOOLTIPS,
    TIMELINE_DEBUG_MOUSE,
    TIMELINE_CANVAS_SHOW,
)


class TimelineWidget(QtWidgets.QWidget):
    """Timeline widget - presentation layer using TimelineEngine."""
    
    # Visual constants
    ROW_HEIGHT = 34
    SPINE_X = 20
    INDENT = 16
    TIMESTAMP_COLUMN_WIDTH = 150  # Width of timestamp area (at negative X)
    
    # Signals
    node_selected = QtCore.Signal(str)
    node_double_clicked = QtCore.Signal(str)
    restore_requested = QtCore.Signal(str)
    rename_requested = QtCore.Signal(str, str)
    create_snapshot_requested = QtCore.Signal()
    
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        
        # Engine handles all data/logic
        self._engine = TimelineEngine()
        
        # UI state only
        self._selected_id: Optional[str] = None
        self._font = QtGui.QFont("Inter", 10)
        self._expanded_branches: set = set()  # Track open fork indicators
        
        # Cache layout to avoid rebuilding on every mouse event
        self._cached_layout: Optional[List[_TreeNode]] = None
        self._layout_dirty = True
        
        # Position animation state
        # Stores (row, indent) tuples for each node at T0
        self._prev_layout_state: Dict[str, Tuple[int, int]] = {}
        # Stores fork indicator (x, y) positions at T0 for appearing node origin
        self._prev_fork_positions: Dict[str, Tuple[float, float]] = {}
        # Set of node IDs that are being removed (for exit animation)
        self._exiting_nodes: set = set()
        # Stores node colors at T0 for exit animation color preservation
        self._prev_node_colors: Dict[str, str] = {}
        # Track which specific fork is being collapsed (for sucking animation)
        self._sucking_fork_id: Optional[str] = None
        self._anim_progress: float = 1.0  # 0.0 = T0, 1.0 = T1
        self._anim_timer: Optional[QtCore.QTimer] = None
        
        # Setup
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding
        )
        self.setMouseTracking(True)
        
        # Context menu
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
    
    def _compute_node_colors(self, layout: List[_TreeNode]) -> Dict[str, str]:
        """Compute node colors with proper inheritance for a given layout."""
        node_colors: Dict[str, str] = {}
        root_colors: Dict[str, str] = {}
        node_to_root: Dict[str, str] = {}  # Maps node ID -> root node ID for that branch
        
        # Build id map for ancestry lookup
        id_to_node = {n.snapshot.snapshot_id: n for n in layout}
        
        for node in layout:
            snap = node.snapshot
            my_parent_id = snap.parent_id
            is_indicator = getattr(snap, 'is_alt_indicator', False)
            
            if is_indicator:
                # Indicators inherit from their parent
                if my_parent_id and my_parent_id in node_colors:
                    node_colors[snap.snapshot_id] = node_colors[my_parent_id]
                    node_to_root[snap.snapshot_id] = node_to_root.get(my_parent_id, my_parent_id)
                else:
                    node_colors[snap.snapshot_id] = "#555"
                    node_to_root[snap.snapshot_id] = "indicator"
            elif my_parent_id and my_parent_id in id_to_node:
                parent_node = id_to_node[my_parent_id]
                parent_snap = parent_node.snapshot
                parent_is_indicator = getattr(parent_snap, 'is_alt_indicator', False)
                parent_is_branch_point = getattr(parent_snap, 'is_branch_point', False)
                
                if parent_is_indicator:
                    # This is the FIRST node of a branch (child of indicator)
                    grandparent_id = parent_snap.parent_id
                    same_lane_as_grandparent = (grandparent_id and grandparent_id in id_to_node 
                                                and node.indent == id_to_node[grandparent_id].indent)
                    if same_lane_as_grandparent and grandparent_id in node_colors:
                        node_colors[snap.snapshot_id] = node_colors[grandparent_id]
                        root_colors[snap.snapshot_id] = node_colors[grandparent_id]
                        node_to_root[snap.snapshot_id] = node_to_root.get(grandparent_id, grandparent_id)
                    else:
                        color = self._engine.get_color_for_key(snap.description)
                        node_colors[snap.snapshot_id] = color
                        root_colors[snap.snapshot_id] = color
                        node_to_root[snap.snapshot_id] = snap.snapshot_id  # This node IS the root
                elif parent_is_branch_point:
                    # Parent is a fork point - check if on same lane as parent
                    same_lane_as_parent = node.indent == parent_node.indent
                    if same_lane_as_parent and my_parent_id in node_colors:
                        node_colors[snap.snapshot_id] = node_colors[my_parent_id]
                        root_colors[snap.snapshot_id] = node_colors[my_parent_id]
                        node_to_root[snap.snapshot_id] = node_to_root.get(my_parent_id, my_parent_id)
                    else:
                        color = self._engine.get_color_for_key(snap.description)
                        node_colors[snap.snapshot_id] = color
                        root_colors[snap.snapshot_id] = color
                        node_to_root[snap.snapshot_id] = snap.snapshot_id  # This node IS the root
                elif my_parent_id in node_to_root:
                    # Continue branch - inherit from parent's root
                    parent_root_id = node_to_root[my_parent_id]
                    if parent_root_id in root_colors:
                        node_colors[snap.snapshot_id] = root_colors[parent_root_id]
                    elif parent_root_id in node_colors:
                        node_colors[snap.snapshot_id] = node_colors[parent_root_id]
                    else:
                        color = self._engine.get_color_for_key(snap.description)
                        node_colors[snap.snapshot_id] = color
                    node_to_root[snap.snapshot_id] = parent_root_id
                elif my_parent_id in node_colors:
                    # Continue main path - inherit parent color, parent becomes root
                    node_colors[snap.snapshot_id] = node_colors[my_parent_id]
                    root_colors[my_parent_id] = node_colors[my_parent_id]
                    node_to_root[snap.snapshot_id] = my_parent_id
                    node_to_root[my_parent_id] = my_parent_id
                else:
                    # Parent color not available yet (animation/layout mismatch)
                    # Generate new color as fallback
                    color = self._engine.get_color_for_key(snap.description)
                    node_colors[snap.snapshot_id] = color
                    node_to_root[snap.snapshot_id] = snap.snapshot_id
            else:
                # Root node
                if TIMELINE_ROOT_OVERRIDE:
                    color = TIMELINE_ROOT_COLOUR
                else:
                    color = self._engine.get_color_for_key(snap.description)
                node_colors[snap.snapshot_id] = color
                root_colors[snap.snapshot_id] = color
                node_to_root[snap.snapshot_id] = snap.snapshot_id
        
        return node_colors
    
    def _get_cached_layout(self) -> List[_TreeNode]:
        """Get layout, rebuilding only if necessary."""
        # Don't rebuild during animation - would disrupt interpolated positions
        if TIMELINE_ANIMATE_TRANSITIONS and self._anim_progress < 1.0 and self._cached_layout is not None:
            return self._cached_layout
        
        if self._layout_dirty or self._cached_layout is None:
            if TIMELINE_DEBUG_MOUSE:
                print(f"[DEBUG] Rebuilding layout, dirty={self._layout_dirty}")
                print(f"[DEBUG] Widget expanded: {self._expanded_branches}")
            
            # Track previous IDs for exit animation
            prev_ids = set()
            
            # Capture current layout state before rebuild for animation
            # BUT: don't do this if already animating (would capture interpolated positions)
            if (TIMELINE_ANIMATE_TRANSITIONS and 
                self._cached_layout is not None and 
                self._anim_progress >= 1.0):  # Only if not currently animating
                # Store (row, indent) for each node to interpolate both axes
                self._prev_layout_state = {}
                self._prev_fork_positions = {}
                self._prev_node_colors = {}  # Store colors for exit animation
                for node in self._cached_layout:
                    self._prev_layout_state[node.snapshot.snapshot_id] = (node.row, node.indent)
                    # Capture fork indicator pixel positions for appearing node animation
                    snap = node.snapshot
                    if getattr(snap, 'is_alt_indicator', False):
                        x = self.SPINE_X + node.indent * self.INDENT
                        y = 10 + node.row * self.ROW_HEIGHT + self.ROW_HEIGHT // 2
                        self._prev_fork_positions[snap.snapshot_id] = (x, y)
                # Store current IDs to determine exiting nodes after rebuild
                prev_ids = {n.snapshot.snapshot_id for n in self._cached_layout}
                # Compute and store colors for current layout (for exit animation)
                self._prev_node_colors = self._compute_node_colors(self._cached_layout)
                self._start_position_animation()
            
            # Sync widget's expanded branches to engine before building
            self._engine._expanded_branches = self._expanded_branches
            if TIMELINE_DEBUG_MOUSE:
                print(f"[DEBUG] Engine expanded: {self._engine._expanded_branches}")
            self._cached_layout = self._engine.build_layout()
            
            # Determine which nodes disappeared (for exit animation)
            if TIMELINE_ANIMATE_TRANSITIONS and self._anim_progress < 1.0:
                new_ids = {n.snapshot.snapshot_id for n in self._cached_layout}
                self._exiting_nodes = prev_ids - new_ids
            self._layout_dirty = False
            if TIMELINE_DEBUG_MOUSE:
                print(f"[DEBUG] Layout rebuilt, {len(self._cached_layout)} nodes")
        return self._cached_layout
    
    # ===================================================================
    # Public API
    # ===================================================================
    
    def set_snapshots(self, snapshots: List[SnapshotInfo]) -> None:
        """Load snapshot data into engine."""
        self._engine.load_snapshots(snapshots)
        self._layout_dirty = True  # Force layout rebuild
        self._update_size()  # Update widget size for new content
        self.update()
    
    def get_snapshots(self) -> List[SnapshotInfo]:
        """Get current snapshot list from engine."""
        return self._engine.get_snapshots()
    
    def selected_id(self) -> Optional[str]:
        """Get currently selected snapshot ID."""
        return self._selected_id
    
    def set_selected(self, snapshot_id: Optional[str]) -> None:
        """Set selected snapshot."""
        self._selected_id = snapshot_id
        self.update()
    
    # ===================================================================
    # Structure Modification API (delegates to engine)
    # ===================================================================
    
    def restore_to_snapshot(self, snapshot_id: str, description: Optional[str] = None) -> Optional[str]:
        """Restore to snapshot - creates new snapshot at bottom of timeline.
        
        Returns new snapshot ID or None if restore failed.
        Note: Caller is responsible for updating its snapshot list and selecting the new node.
        """
        new_id = self._engine.restore_to_snapshot(snapshot_id, description)
        if new_id:
            self._selected_id = new_id
            self._layout_dirty = True  # Force layout rebuild on restore (branch promotion)
            self._update_size()  # Update widget size for new layout
            self.repaint()  # Immediate repaint
        return new_id
    
    def restructure_for_restore(self, snapshot_id: str, new_snapshot_id: str = None) -> bool:
        """Do branch restructuring for restore WITHOUT creating a new snapshot.
        
        This is used when the datastore already created the "Restored from" snapshot.
        We just need to restructure branches (move future snapshots to alt branch, etc.)
        
        Args:
            snapshot_id: ID of snapshot being restored to
            new_snapshot_id: ID of the newly created "Restored from" snapshot (should stay on main)
            
        Returns:
            True if successful, False if target not found
        """
        result = self._engine.restructure_for_restore(snapshot_id, new_snapshot_id)
        if result:
            self._layout_dirty = True  # Force layout rebuild on restore (branch promotion)
            self._update_size()  # Update widget size for new layout
            self.repaint()  # Immediate repaint
        return result
    
    def rename_snapshot(self, snapshot_id: str, new_description: str) -> bool:
        """Rename snapshot - delegates to engine."""
        return self._engine.rename_snapshot(snapshot_id, new_description)
    
    def create_snapshot(
        self, description: str,
        parent_id: Optional[str] = None,
        branch_name: str = "main",
        tags: Optional[List[str]] = None
    ) -> Optional[str]:
        """Create snapshot - delegates to engine."""
        new_id = self._engine.create_snapshot(description, parent_id, branch_name, tags)
        if new_id:
            self._selected_id = new_id
            self.update()
        return new_id
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete snapshot - delegates to engine."""
        return self._engine.delete_snapshot(snapshot_id)
    
    # ===================================================================
    # Rendering
    # ===================================================================
    
    def paintEvent(self, event: QtGui.QPaintEvent):
        """Render timeline using cached layout with interpolated positions."""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        
        # DEBUG: Draw border around canvas to visualize its size
        if TIMELINE_CANVAS_SHOW:
            painter.setPen(QtGui.QPen(QtGui.QColor("red"), 2))
            painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        
        # Use cached layout (which has interpolated positions during animation)
        layout = self._get_cached_layout()
        if not layout:
            painter.drawText(20, 30, "No snapshots to display")
            return

        # Negative X layout: shift painter right so timestamps can be drawn at negative X
        painter.translate(self.TIMESTAMP_COLUMN_WIDTH, 0)

        # Pre-calculate positions with SCALE + FADE + SHIFT animation
        # GENERATING fork: nodes scale up from 0, fade in, shift from fork position
        # SUCKING fork: nodes scale down to 0, fade out, shift to fork position
        
        # Build id map early for ancestry tracing
        id_to_node = {n.snapshot.snapshot_id: n for n in layout}
        
        generating_fork = None
        sucking_fork = None
        generating_fork_pos = None
        sucking_fork_pos = None
        
        if TIMELINE_ANIMATE_TRANSITIONS and self._anim_progress < 1.0:
            current_forks = {n.snapshot.snapshot_id for n in layout 
                           if getattr(n.snapshot, 'is_alt_indicator', False)}
            prev_forks = set(self._prev_fork_positions.keys())
            
            # GENERATING: forks in current but not in prev (unfolding)
            new_forks = current_forks - prev_forks
            if new_forks:
                generating_fork = new_forks.pop()
                if generating_fork in self._prev_fork_positions:
                    generating_fork_pos = self._prev_fork_positions[generating_fork]
            
            # SUCKING: only the specific fork being collapsed (not all closed forks)
            if self._sucking_fork_id and self._sucking_fork_id in prev_forks:
                sucking_fork = self._sucking_fork_id
                if sucking_fork in self._prev_fork_positions:
                    sucking_fork_pos = self._prev_fork_positions[sucking_fork]
        
        # Helper to check if node is under a given fork
        def is_under_fork(node_id: str, fork_parent_id: str) -> bool:
            if not fork_parent_id:
                return False
            visited = set()
            current = node_id
            while current and current not in visited:
                visited.add(current)
                if current == fork_parent_id:
                    return True
                # Get parent - try current layout first, then snapshots
                parent_id = None
                n = id_to_node.get(current)
                if n:
                    parent_id = n.snapshot.parent_id
                else:
                    # Node not in current layout (exiting), look up in snapshots
                    for snap in self._engine._snapshots:
                        if snap.snapshot_id == current:
                            parent_id = snap.parent_id
                            break
                if not parent_id:
                    break
                # For fork indicators, we need to check if their parent is under the fork
                # The fork indicator's "parent" is the node it branches from (e.g., snap_002)
                # So we continue with that parent
                current = parent_id
            return False
        
        for node in layout:
            target_row = node.row
            target_indent = node.indent
            target_x = self.SPINE_X + target_indent * self.INDENT
            target_y = 10 + target_row * self.ROW_HEIGHT + self.ROW_HEIGHT // 2
            
            # Default: no animation transform
            node._anim_x = target_x
            node._anim_y = target_y
            node._anim_scale = 1.0
            node._anim_fade = 1.0
            node._is_generating = False
            node._is_sucking = False
            
            if TIMELINE_ANIMATE_TRANSITIONS and self._anim_progress < 1.0:
                node_id = node.snapshot.snapshot_id
                
                # Check if under generating fork (appearing)
                if generating_fork and generating_fork_pos:
                    gen_parent = generating_fork.replace("alt_indicator_", "")
                    if is_under_fork(node_id, gen_parent):
                        node._is_generating = True
                        # Scale: 0 -> 1 (ease in cubic - slower at start, accelerates)
                        t = self._anim_progress
                        ease = t ** 3
                        node._anim_scale = ease
                        node._anim_fade = ease
                        # Position: shift from fork to target
                        fork_x, fork_y = generating_fork_pos
                        node._anim_x = fork_x + (target_x - fork_x) * ease
                        node._anim_y = fork_y + (target_y - fork_y) * ease
                        continue
                
                # Check if this is the fork indicator being collapsed (from - to +)
                # It should animate toward its parent's position like regular nodes
                if self._sucking_fork_id and node_id == self._sucking_fork_id:
                    # Fork indicator collapsing - find its parent (the node it branches from)
                    fork_parent_id = node_id.replace("alt_indicator_", "")
                    if fork_parent_id in id_to_node:
                        parent_node = id_to_node[fork_parent_id]
                        # Use parent's CURRENT interpolated position (dynamic target)
                        parent_x = getattr(parent_node, '_anim_x', 
                                          self.SPINE_X + parent_node.indent * self.INDENT)
                        parent_y = getattr(parent_node, '_anim_y',
                                          10 + parent_node.row * self.ROW_HEIGHT + self.ROW_HEIGHT // 2)
                        # Interpolate toward parent's current position
                        node._anim_x = target_x + (parent_x - target_x) * (1.0 - self._anim_progress)
                        node._anim_y = target_y + (parent_y - target_y) * (1.0 - self._anim_progress)
                        node._anim_scale = self._anim_progress
                        node._anim_fade = self._anim_progress
                
                # For fork indicators UNDER the sucking fork, chase the SUCKING FORK position
                if node_id.startswith("alt_indicator_") and node_id != self._sucking_fork_id and self._sucking_fork_id:
                    sucking_parent_id = self._sucking_fork_id.replace("alt_indicator_", "")
                    # Get this fork indicator's parent (the node it branches from)
                    indicator_parent_id = node_id.replace("alt_indicator_", "")
                    # Check if that parent node is under the sucking fork's parent
                    if is_under_fork(indicator_parent_id, sucking_parent_id) and node_id in self._prev_layout_state and self._sucking_fork_id in self._prev_fork_positions:
                        # Only animate if this fork indicator has LARGER indent than the sucking fork
                        prev_row, prev_indent = self._prev_layout_state[node_id]
                        sucking_row, sucking_indent = self._prev_layout_state.get(self._sucking_fork_id, (0, 0))
                        if prev_indent > sucking_indent:
                            # Get the sucking fork's FIXED position (where all nodes collapse to)
                            suck_x, suck_y = self._prev_fork_positions[self._sucking_fork_id]
                            # Get this indicator's PREVIOUS position
                            prev_x = self.SPINE_X + prev_indent * self.INDENT
                            prev_y = 10 + prev_row * self.ROW_HEIGHT + self.ROW_HEIGHT // 2
                            # Animate from previous position toward sucking fork
                            node._anim_x = prev_x + (suck_x - prev_x) * self._anim_progress
                            node._anim_y = prev_y + (suck_y - prev_y) * self._anim_progress
                            node.y = node._anim_y - self.ROW_HEIGHT // 2
                            node._anim_indent = (node._anim_x - self.SPINE_X) / self.INDENT if self.INDENT > 0 else target_indent
                            continue  # Skip regular interpolation
                
                # Regular interpolation for existing nodes
                if node_id in self._prev_layout_state:
                    prev_row, prev_indent = self._prev_layout_state[node_id]
                    prev_x = self.SPINE_X + prev_indent * self.INDENT
                    prev_y = 10 + prev_row * self.ROW_HEIGHT + self.ROW_HEIGHT // 2
                    # Simple linear interpolation for existing nodes
                    node._anim_x = prev_x + (target_x - prev_x) * self._anim_progress
                    node._anim_y = prev_y + (target_y - prev_y) * self._anim_progress
                    node.y = node._anim_y - self.ROW_HEIGHT // 2
                    node._anim_indent = (node._anim_x - self.SPINE_X) / self.INDENT if self.INDENT > 0 else target_indent
                else:
                    # Other new nodes (not under generating fork)
                    node.y = 10 + target_row * self.ROW_HEIGHT
                    node._anim_indent = target_indent
            else:
                node.y = 10 + target_row * self.ROW_HEIGHT
                node._anim_indent = target_indent
        
        # Build position map using animation coordinates
        positions = {}
        for node in layout:
            snap = node.snapshot
            # Use animation coordinates if available
            x = getattr(node, '_anim_x', self.SPINE_X + node.indent * self.INDENT)
            center_y = getattr(node, '_anim_y', node.y + self.ROW_HEIGHT // 2) - self.ROW_HEIGHT // 2 + self.ROW_HEIGHT // 2
            positions[snap.snapshot_id] = (x, center_y, node.indent)
        
        # Compute colors with proper inheritance (like perfect_timeline)
        node_colors: Dict[str, str] = {}
        root_colors: Dict[str, str] = {}  # Maps root node ID -> color for that branch
        node_to_root: Dict[str, str] = {}  # Maps node ID -> root node ID for that branch
        
        # Process nodes in order
        for node in layout:
            snap = node.snapshot
            my_parent_id = snap.parent_id
            is_indicator = getattr(snap, 'is_alt_indicator', False)
            
            if is_indicator:
                # Indicators inherit from their parent
                if my_parent_id and my_parent_id in node_colors:
                    node_colors[snap.snapshot_id] = node_colors[my_parent_id]
                    node_to_root[snap.snapshot_id] = node_to_root.get(my_parent_id, my_parent_id)
                else:
                    node_colors[snap.snapshot_id] = "#555"
                    node_to_root[snap.snapshot_id] = "indicator"
            elif my_parent_id and my_parent_id in id_to_node:
                parent_node = id_to_node[my_parent_id]
                parent_snap = parent_node.snapshot
                parent_is_indicator = getattr(parent_snap, 'is_alt_indicator', False)
                # Check if parent is a branch point (has alternatives)
                parent_is_branch_point = getattr(parent_snap, 'is_branch_point', False)
                
                if parent_is_indicator:
                    # This is the FIRST node of a branch (child of indicator)
                    # Check if on same lane as grandparent - if so, inherit
                    grandparent_id = parent_snap.parent_id
                    same_lane_as_grandparent = (grandparent_id and grandparent_id in id_to_node 
                                                and node.indent == id_to_node[grandparent_id].indent)
                    if same_lane_as_grandparent and grandparent_id in node_colors:
                        # Same lane - inherit grandparent's color
                        node_colors[snap.snapshot_id] = node_colors[grandparent_id]
                        root_colors[snap.snapshot_id] = node_colors[grandparent_id]
                        node_to_root[snap.snapshot_id] = node_to_root.get(grandparent_id, grandparent_id)
                    else:
                        # Different lane - get NEW color
                        color = self._engine.get_color_for_key(snap.description)
                        node_colors[snap.snapshot_id] = color
                        root_colors[snap.snapshot_id] = color
                        node_to_root[snap.snapshot_id] = snap.snapshot_id  # This node IS the root
                elif parent_is_branch_point:
                    # Parent is a fork point - check if on same lane as parent
                    same_lane_as_parent = node.indent == parent_node.indent
                    if same_lane_as_parent and my_parent_id in node_colors:
                        # Same lane - inherit parent's color
                        node_colors[snap.snapshot_id] = node_colors[my_parent_id]
                        root_colors[snap.snapshot_id] = node_colors[my_parent_id]
                        node_to_root[snap.snapshot_id] = node_to_root.get(my_parent_id, my_parent_id)
                    else:
                        # Different lane - get its OWN color
                        color = self._engine.get_color_for_key(snap.description)
                        node_colors[snap.snapshot_id] = color
                        root_colors[snap.snapshot_id] = color
                        node_to_root[snap.snapshot_id] = snap.snapshot_id  # This node IS the root
                elif my_parent_id in node_to_root:
                    # Continue branch - inherit from parent's root
                    parent_root_id = node_to_root[my_parent_id]
                    if parent_root_id in root_colors:
                        node_colors[snap.snapshot_id] = root_colors[parent_root_id]
                    elif parent_root_id in node_colors:
                        node_colors[snap.snapshot_id] = node_colors[parent_root_id]
                    else:
                        color = self._engine.get_color_for_key(snap.description)
                        node_colors[snap.snapshot_id] = color
                    node_to_root[snap.snapshot_id] = parent_root_id
                elif my_parent_id in node_colors:
                    # Continue main path - inherit parent color, parent becomes root
                    node_colors[snap.snapshot_id] = node_colors[my_parent_id]
                    root_colors[my_parent_id] = node_colors[my_parent_id]
                    node_to_root[snap.snapshot_id] = my_parent_id
                    node_to_root[my_parent_id] = my_parent_id
                else:
                    # Parent color not available yet - generate new color
                    color = self._engine.get_color_for_key(snap.description)
                    node_colors[snap.snapshot_id] = color
                    node_to_root[snap.snapshot_id] = snap.snapshot_id
            else:
                # Root node - use override color if enabled, otherwise get from description
                if TIMELINE_ROOT_OVERRIDE:
                    color = TIMELINE_ROOT_COLOUR
                else:
                    color = self._engine.get_color_for_key(snap.description)
                node_colors[snap.snapshot_id] = color
                root_colors[snap.snapshot_id] = color
                node_to_root[snap.snapshot_id] = snap.snapshot_id
                root_colors[snap.snapshot_id] = color
        
        # Store for tooltip access
        self._node_colors = node_colors
        self._root_colors = root_colors
        
        # Phase 1: Draw selection/hover background FIRST (so lines/nodes appear ON TOP)
        for node in layout:
            snap = node.snapshot
            _, center_y, _ = positions[snap.snapshot_id]
            is_selected = snap.snapshot_id == self._selected_id
            is_hovered = snap.snapshot_id == getattr(self, '_hovered_id', None)
            
            if is_selected or is_hovered:
                bg_color = "#e3f2fd" if is_selected else "#f5f5f5"  # Blue for selected, light gray for hover
                # Fill from negative X (timestamp area) to full widget width
                painter.fillRect(-self.TIMESTAMP_COLUMN_WIDTH, center_y - 15, self.width() + self.TIMESTAMP_COLUMN_WIDTH, 30, QtGui.QColor(bg_color))
        
        # Build helper: last node at each indent level
        last_at_indent: Dict[int, Tuple[float, str]] = {}  # indent -> (y, branch_name)
        
        # Phase 2: Draw main spine segments (apply thickness override here only)
        main_nodes = [(positions[n.snapshot.snapshot_id][1], n.snapshot.snapshot_id, n.snapshot) 
                      for n in layout if n.indent == 0]
        for i in range(len(main_nodes) - 1):
            y1, id1, snap1 = main_nodes[i]
            y2, id2, snap2 = main_nodes[i + 1]
            segment_color = node_colors.get(id2, "#555")
            # Main spine uses thickness override, branches use default
            line_width = TIMELINE_LINE_THICKNESS if TIMELINE_LINE_THICKNESS_OVERRIDE else 2
            painter.setPen(QtGui.QPen(QtGui.QColor(segment_color), line_width))
            
            # Calculate node sizes to stop line at edge (not cross into circle)
            node_size_1 = TIMELINE_NODE_SIZE if TIMELINE_NODE_SIZE_OVERRIDE else 8
            node_size_2 = TIMELINE_NODE_SIZE if TIMELINE_NODE_SIZE_OVERRIDE else 8
            radius_1 = node_size_1 // 2
            radius_2 = node_size_2 // 2
            
            # Draw line from edge of first node to edge of second node
            # Add small gap (2px) so thick line just touches without entering circle
            gap = 2
            painter.drawLine(self.SPINE_X, y1 + radius_1 + gap, self.SPINE_X, y2 - radius_2 - gap)
        
        # Calculate alpha for line fading during animation
        # Lines fade in for appearing nodes, fade out for disappearing
        line_alpha = int(255 * self._anim_progress) if (TIMELINE_ANIMATE_TRANSITIONS and self._anim_progress < 1.0) else 255
        
        # Phase 3: Draw branch connectors
        for i, node in enumerate(layout):
            snap = node.snapshot
            indent = node.indent
            if indent == 0:
                continue  # Main spine nodes don't need branch connectors
            
            parent_id = snap.parent_id
            is_indicator = getattr(snap, 'is_alt_indicator', False)
            node_x = self.SPINE_X + indent * self.INDENT
            _, center_y, _ = positions[snap.snapshot_id]
            
            if not parent_id or parent_id not in positions:
                continue
            
            parent_x, parent_y, parent_indent = positions[parent_id]
            
            # Check if this is an appearing node (lines should fade in)
            is_appearing = (TIMELINE_ANIMATE_TRANSITIONS and 
                           self._anim_progress < 1.0 and 
                           snap.snapshot_id not in self._prev_layout_state)
            
            if is_indicator:
                # Indicators at indent 1: L-connector from parent (main spine) to indicator
                line_color = node_colors.get(snap.snapshot_id, "#555")
                pen = QtGui.QPen(QtGui.QColor(line_color), 2)
                # if is_appearing:
                #     pen.setColor(QtGui.QColor(line_color.replace('#', '') + format(line_alpha, '02x')) if len(line_color) == 7 else line_color)
                # make sure we're using the right color
                if is_appearing:
                    line_color = line_color.replace('#', '') + format(line_alpha, '02x') if len(line_color) == 7 else line_color
                painter.setPen(pen)
                # Draw L-shaped connector with rounded inner corner (9 to 6 o'clock)
                path = QtGui.QPainterPath()
                corner_radius = 6  # Slightly smaller radius for fork nodes
                # Start from parent, go down to corner start
                path.moveTo(parent_x, parent_y + 4)
                path.lineTo(parent_x, center_y - corner_radius)
                # Rounded corner: arc from 9 o'clock (left) to 6 o'clock (down)
                path.arcTo(parent_x, center_y - corner_radius * 2,
                           corner_radius * 2, corner_radius * 2,
                           180, 90)
                # Continue horizontal to node
                path.lineTo(node_x - 6, center_y)
                painter.drawPath(path)
            else:
                # Regular branch nodes at indent >= 2
                prev_in_col = last_at_indent.get(indent)
                
                if prev_in_col and prev_in_col[1] == snap.branch_name:
                    # Same branch = vertical line continuing down
                    prev_y, _ = prev_in_col
                    line_color = node_colors.get(snap.snapshot_id, "#555")
                    pen = QtGui.QPen(QtGui.QColor(line_color), 2)
                    if is_appearing:
                        # Fade in the line
                        c = QtGui.QColor(line_color)
                        c.setAlpha(line_alpha)
                        pen.setColor(c)
                    painter.setPen(pen)
                    painter.drawLine(node_x, prev_y + 4, node_x, center_y - 4)
                else:
                    # New branch starting = L from parent indicator (fork node)
                    indicator_id = f"alt_indicator_{parent_id}"
                    if indicator_id in positions:
                        fork_x, fork_y, fork_indent = positions[indicator_id]
                        line_color = node_colors.get(snap.snapshot_id, "#555")
                        pen = QtGui.QPen(QtGui.QColor(line_color), 2)
                        if is_appearing:
                            # Fade in the line
                            c = QtGui.QColor(line_color)
                            c.setAlpha(line_alpha)
                            pen.setColor(c)
                        painter.setPen(pen)
                        # Draw L-shaped connector with rounded inner corner (9 to 6 o'clock)
                        path = QtGui.QPainterPath()
                        corner_radius = 8  # Larger radius for smoother curve
                        # Start from fork point, go down to start of curve
                        path.moveTo(fork_x, fork_y + 6)
                        path.lineTo(fork_x, center_y - corner_radius)
                        # Rounded corner: arc from 9 o'clock (left) to 6 o'clock (down)
                        # Arc center is at (fork_x + radius, center_y - radius)
                        path.arcTo(fork_x, center_y - corner_radius * 2,
                                   corner_radius * 2, corner_radius * 2,
                                   180, 90)
                        # Continue horizontal to node
                        path.lineTo(node_x - 4, center_y)
                        painter.drawPath(path)
            
            if not is_indicator:
                last_at_indent[indent] = (center_y, snap.branch_name)
        
        # Phase 4: Draw nodes
        for node in layout:
            snap = node.snapshot
            x, center_y, indent = positions[snap.snapshot_id]
            is_selected = snap.snapshot_id == self._selected_id
            is_indicator = getattr(snap, 'is_alt_indicator', False)
            is_current = snap.snapshot_id == self._engine.get_current_id()
            # Use the inherited color from node_colors (includes all descendants)
            color = node_colors.get(snap.snapshot_id, "#555")
            
            # Get animation attributes (scale and fade)
            anim_scale = getattr(node, '_anim_scale', 1.0)
            anim_fade = getattr(node, '_anim_fade', 1.0)
            is_generating = getattr(node, '_is_generating', False)
            fade_alpha = int(255 * anim_fade)
            
            # Node size: apply override only to main spine (indent == 0)
            if indent == 0 and TIMELINE_NODE_SIZE_OVERRIDE:
                node_size = TIMELINE_NODE_SIZE
            else:
                node_size = 8  # Default size for branch nodes
            
            if is_indicator:
                # Draw +/- indicator with scale and fade for generating
                is_expanded = getattr(snap, 'is_expanded', False)
                painter.save()
                painter.translate(x, center_y)
                painter.scale(anim_scale, anim_scale)
                painter.translate(-x, -center_y)
                
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                # Inherit color from the L-shaped connector (same as node_colors lookup)
                ind_color = QtGui.QColor(node_colors.get(snap.snapshot_id, "#555"))
                ind_color.setAlpha(fade_alpha)
                painter.setPen(QtGui.QPen(ind_color, 1.5))
                painter.drawEllipse(x - 6, center_y - 6, 12, 12)
                plus_color = QtGui.QColor("#333")
                plus_color.setAlpha(fade_alpha)
                painter.setPen(QtGui.QPen(plus_color, 2))
                painter.drawLine(x - 3, center_y, x + 3, center_y)
                if not is_expanded:
                    painter.drawLine(x, center_y - 3, x, center_y + 3)
                painter.restore()
                
                desc_color = QtGui.QColor("#555")
                desc_color.setAlpha(fade_alpha)
                painter.setPen(desc_color)
                font = QtGui.QFont("Inter", 9)
                painter.setFont(font)
                # Indicator description is already formatted as "(X)" or "(X) {lane}"
                painter.drawText(x + 20, center_y + 4, snap.description)
            else:
                # Draw regular node with scale and fade
                actual_node_size = node_size if (indent == 0 and TIMELINE_NODE_SIZE_OVERRIDE) else 8
                # Apply scale to node size
                scaled_size = actual_node_size * anim_scale
                radius = scaled_size // 2
                
                # Calculate outline thickness proportional to size
                size_delta = actual_node_size - 8
                outline_thickness = max(1.5, 2 + size_delta * 0.75)
                
                node_color = QtGui.QColor(color)
                node_color.setAlpha(fade_alpha)
                
                if is_selected:
                    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                    sel_color = QtGui.QColor(color)
                    sel_color.setAlpha(fade_alpha)
                    painter.setPen(QtGui.QPen(sel_color, outline_thickness + 0.5))
                    painter.drawEllipse(x - radius - 2, center_y - radius - 2, scaled_size + 4, scaled_size + 4)
                
                if is_current:
                    painter.setBrush(QtGui.QColor(node_color))
                else:
                    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.setPen(QtGui.QPen(node_color, outline_thickness))
                painter.drawEllipse(x - radius, center_y - radius, scaled_size, scaled_size)
                
                # Icon: color-coded delta/full
                # Color: black = manual, grey (#7f7f7f) = auto
                # Shape: ≋ = delta, ■ = full
                is_auto = snap.type == SnapshotType.AUTO
                is_delta = getattr(snap, 'is_delta', False)
                
                # Icon color based on manual/auto
                icon_color_hex = "#7f7f7f" if is_auto else "#000000"
                icon_color = QtGui.QColor(icon_color_hex)
                icon_color.setAlpha(fade_alpha)
                
                # Delta or full icon
                delta_full_icon = "≋" if is_delta else "■"
                
                # Draw icon with color
                text_x = x + 14 if indent < 2 else x + 20
                font = QtGui.QFont("Inter", 10)
                painter.setFont(font)
                
                painter.setPen(icon_color)
                painter.drawText(text_x, center_y + 4, delta_full_icon)
                
                # Draw separator and name in standard text color
                fm = QtGui.QFontMetrics(font)
                icon_width = fm.horizontalAdvance(delta_full_icon)
                text_color = QtGui.QColor("#1a1a1a")
                text_color.setAlpha(fade_alpha)
                painter.setPen(text_color)
                painter.drawText(text_x + icon_width, center_y + 4, " " + snap.description)

                # Time - align to right edge of visible area
                time_col = QtGui.QColor("#999")
                time_col.setAlpha(fade_alpha)
                painter.setPen(time_col)
                time_font = QtGui.QFont("Consolas", 8)
                painter.setFont(time_font)
                time_text = snap.created_at.strftime("%Y-%b-%d %H:%M:%S")
                fm = QtGui.QFontMetrics(time_font)
                # Timestamp at negative X (left of spine), right-aligned to origin
                time_x = -10 - fm.horizontalAdvance(time_text)
                painter.drawText(time_x, center_y + 4, time_text)
            
            painter.setFont(self._font)
        
        # Phase 5: Draw exiting nodes (collapsing cascade animation)
        # Each node interpolates from its initial position toward its parent's current position
        if TIMELINE_ANIMATE_TRANSITIONS and self._anim_progress < 1.0 and self._exiting_nodes:
            t = 1.0 - self._anim_progress  # 1.0 at start, 0.0 at end
            ease = 1 - (1 - t) ** 3  # ease out cubic
            
            # Cache for parent target positions (node_id -> (x, y))
            parent_targets: Dict[str, Tuple[float, float]] = {}
            
            def get_parent_target(node_id: str) -> Tuple[float, float]:
                """Get the target position for a node's parent (where this node is collapsing toward)."""
                if node_id in parent_targets:
                    return parent_targets[node_id]
                
                # Find parent from engine snapshots
                parent_id = None
                for snap in self._engine._snapshots:
                    if snap.snapshot_id == node_id:
                        parent_id = snap.parent_id
                        break
                
                # Check if this is a fork indicator UNDER the sucking fork - handle even if no parent_id
                if node_id.startswith("alt_indicator_") and self._sucking_fork_id:
                    sucking_parent_id = self._sucking_fork_id.replace("alt_indicator_", "")
                    # Get this fork indicator's parent (the node it branches from, e.g., snap_002)
                    indicator_parent_id = node_id.replace("alt_indicator_", "")
                    # Check if that parent node is under the sucking fork's parent (e.g., snap_001)
                    if is_under_fork(indicator_parent_id, sucking_parent_id) and self._sucking_fork_id in self._prev_fork_positions:
                        # Only animate if this fork indicator has LARGER indent than the sucking fork
                        if node_id in self._prev_layout_state and self._sucking_fork_id in self._prev_layout_state:
                            node_row, node_indent = self._prev_layout_state[node_id]
                            sucking_row, sucking_indent = self._prev_layout_state[self._sucking_fork_id]
                            if node_indent > sucking_indent:
                                suck_x, suck_y = self._prev_fork_positions[self._sucking_fork_id]
                                parent_targets[node_id] = (suck_x, suck_y)
                                return parent_targets[node_id]
                
                if not parent_id:
                    # No parent, fade in place
                    if node_id in self._prev_layout_state:
                        row, indent = self._prev_layout_state[node_id]
                        x = self.SPINE_X + indent * self.INDENT
                        y = 10 + row * self.ROW_HEIGHT + self.ROW_HEIGHT // 2
                        parent_targets[node_id] = (x, y)
                        return parent_targets[node_id]
                    return (0, 0)
                
                # Check if parent is the fork being collapsed - calculate its DYNAMIC position
                fork_parent_id = self._sucking_fork_id.replace('alt_indicator_', '') if self._sucking_fork_id else None
                if parent_id == fork_parent_id and self._sucking_fork_id in self._prev_fork_positions:
                    # Parent is the collapsing fork - calculate its current interpolated position
                    fork_x, fork_y = self._prev_fork_positions[self._sucking_fork_id]
                    # Get fork's parent (the node it branches from) for interpolation target
                    if fork_parent_id in id_to_node:
                        fork_parent_node = id_to_node[fork_parent_id]
                        parent_target_x = getattr(fork_parent_node, '_anim_x',
                                                  self.SPINE_X + fork_parent_node.indent * self.INDENT)
                        parent_target_y = getattr(fork_parent_node, '_anim_y',
                                                  10 + fork_parent_node.row * self.ROW_HEIGHT + self.ROW_HEIGHT // 2)
                        # Fork's current position: interpolated toward its parent
                        curr_fork_x = fork_x + (parent_target_x - fork_x) * (1.0 - self._anim_progress)
                        curr_fork_y = fork_y + (parent_target_y - fork_y) * (1.0 - self._anim_progress)
                        parent_targets[node_id] = (curr_fork_x, curr_fork_y)
                        return parent_targets[node_id]
                    else:
                        # Fork's parent not in layout, use static position
                        parent_targets[node_id] = (fork_x, fork_y)
                        return parent_targets[node_id]
                
                # Check if parent is in current layout (visible and being interpolated)
                if parent_id in id_to_node:
                    parent_node = id_to_node[parent_id]
                    # Get parent's current interpolated position
                    target_x = getattr(parent_node, '_anim_x', 
                                      self.SPINE_X + parent_node.indent * self.INDENT)
                    target_y = getattr(parent_node, '_anim_y', 
                                      10 + parent_node.row * self.ROW_HEIGHT + self.ROW_HEIGHT // 2)
                    parent_targets[node_id] = (target_x, target_y)
                    return parent_targets[node_id]
                
                # Parent is also exiting, recursively get its target
                if parent_id in self._exiting_nodes:
                    grandparent_target = get_parent_target(parent_id)
                    # Parent's current position is interpolated from its prev toward its target
                    if parent_id in self._prev_layout_state:
                        prev_row, prev_indent = self._prev_layout_state[parent_id]
                        prev_x = self.SPINE_X + prev_indent * self.INDENT
                        prev_y = 10 + prev_row * self.ROW_HEIGHT + self.ROW_HEIGHT // 2
                        target_x, target_y = grandparent_target
                        curr_x = prev_x + (target_x - prev_x) * (1.0 - ease)
                        curr_y = prev_y + (target_y - prev_y) * (1.0 - ease)
                        parent_targets[node_id] = (curr_x, curr_y)
                        return parent_targets[node_id]
                
                # Parent not found, fade in place
                if node_id in self._prev_layout_state:
                    row, indent = self._prev_layout_state[node_id]
                    x = self.SPINE_X + indent * self.INDENT
                    y = 10 + row * self.ROW_HEIGHT + self.ROW_HEIGHT // 2
                    parent_targets[node_id] = (x, y)
                    return parent_targets[node_id]
                return (0, 0)
            
            for node_id in self._exiting_nodes:
                if node_id not in self._prev_layout_state:
                    continue
                
                prev_row, prev_indent = self._prev_layout_state[node_id]
                prev_x = self.SPINE_X + prev_indent * self.INDENT
                prev_y = 10 + prev_row * self.ROW_HEIGHT + self.ROW_HEIGHT // 2
                
                # Get target position (parent's current position)
                target_x, target_y = get_parent_target(node_id)
                
                # Interpolate from previous position toward parent's current position
                curr_x = prev_x + (target_x - prev_x) * (1.0 - ease)
                curr_y = prev_y + (target_y - prev_y) * (1.0 - ease)
                
                # Scale: 1 -> 0, Fade: full -> 0
                curr_scale = ease
                fade_alpha = int(255 * ease)
                
                # Draw the shrinking/fading node
                # Check if this is a fork indicator being collapsed (under sucking fork hierarchy)
                is_collapsing_indicator = False
                if node_id.startswith("alt_indicator_") and self._sucking_fork_id:
                    # Check if this fork indicator's parent node is under the sucking fork's parent
                    sucking_parent_id = self._sucking_fork_id.replace("alt_indicator_", "")
                    indicator_parent_id = node_id.replace("alt_indicator_", "")
                    if is_under_fork(indicator_parent_id, sucking_parent_id):
                        is_collapsing_indicator = True
                
                # if is_collapsing_indicator:
                #     node_color_hex = "#000000"  # Black for collapsing fork indicators
                # else:
                node_color_hex = self._prev_node_colors.get(node_id, "#555")
                exit_color = QtGui.QColor(node_color_hex)
                exit_color.setAlpha(fade_alpha)
                painter.setPen(QtGui.QPen(exit_color, 2))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                
                scaled_radius = 4 * curr_scale
                painter.drawEllipse(curr_x - scaled_radius, curr_y - scaled_radius,
                                    scaled_radius * 2, scaled_radius * 2)
        
        painter.end()
    
    # ===================================================================
    # Event Handling
    # ===================================================================
    
    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Handle click - selection or branch toggle."""
        y = int(event.position().y())
        if TIMELINE_DEBUG_MOUSE:
            print(f"[DEBUG] mousePressEvent y={y}")
        
        layout = self._get_cached_layout()
        for node in layout:
            if node.y <= y <= node.y + self.ROW_HEIGHT:
                snap = node.snapshot
                if TIMELINE_DEBUG_MOUSE:
                    print(f"[DEBUG] Clicked on: {snap.snapshot_id}, is_alt_indicator={getattr(snap, 'is_alt_indicator', False)}")
                if getattr(snap, 'is_alt_indicator', False):
                    self.toggle_branch(snap.snapshot_id)  # Use widget's bloodline logic
                    self._layout_dirty = True  # Mark layout dirty for rebuild
                    self._update_size()  # Update size for scrollbars
                    self.repaint()  # Immediate repaint for responsiveness
                    if TIMELINE_DEBUG_MOUSE:
                        print(f"[DEBUG] Toggled branch, dirty=True")
                else:
                    self._selected_id = snap.snapshot_id
                    self.node_selected.emit(snap.snapshot_id)
                    self.repaint()
                    if TIMELINE_DEBUG_MOUSE:
                        print(f"[DEBUG] Selected: {snap.snapshot_id}")
                return
    
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        """Debug mouse release."""
        if TIMELINE_DEBUG_MOUSE:
            print(f"[DEBUG] mouseReleaseEvent")
        super().mouseReleaseEvent(event)
    
    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        """Handle double-click - also toggle branch for responsive clicking."""
        print(f"[DEBUG WIDGET] mouseDoubleClickEvent triggered")
        y = int(event.position().y())

        layout = self._get_cached_layout()
        print(f"[DEBUG WIDGET] layout has {len(layout)} nodes")
        for node in layout:
            if node.y <= y <= node.y + self.ROW_HEIGHT:
                snap = node.snapshot
                print(f"[DEBUG WIDGET] Hit node: {snap.snapshot_id}, is_alt_indicator={getattr(snap, 'is_alt_indicator', False)}")
                if getattr(snap, 'is_alt_indicator', False):
                    self.toggle_branch(snap.snapshot_id)  # Use widget's bloodline logic
                    self._layout_dirty = True
                    self._update_size()  # Update size for scrollbars
                    self.repaint()
                    print(f"[DEBUG WIDGET] Toggled branch from double-click")
                else:
                    # Double-click disabled - restore is too dangerous to trigger accidentally
                    # User must use context menu for explicit restore action
                    pass
                return
        print(f"[DEBUG WIDGET] No node hit at y={y}")
        event.accept()
    
    def _show_context_menu(self, pos: QtCore.QPoint):
        """Show context menu."""
        y = pos.y()
        
        layout = self._get_cached_layout()
        
        clicked = None
        for node in layout:
            if node.y <= y <= node.y + self.ROW_HEIGHT:
                clicked = node
                break
        
        if not clicked:
            return
        
        snap = clicked.snapshot
        if getattr(snap, 'is_alt_indicator', False):
            return
        
        menu = QtWidgets.QMenu(self)
        is_current = snap.snapshot_id == self._engine.get_current_id()
        
        # Check if this is the main branch leaf (can't restore to current state)
        is_main_leaf = self._is_main_branch_leaf(clicked, layout)
        
        # 1. Save checkpoint (only on current node)
        save_checkpoint = menu.addAction("Save checkpoint from current state")
        save_checkpoint.setEnabled(is_current)
        if is_current:
            save_checkpoint.triggered.connect(self.create_snapshot_requested.emit)
        
        # 2. Rename (always available)
        rename = menu.addAction("Rename...")
        rename.triggered.connect(lambda: self.rename_requested.emit(snap.snapshot_id, snap.description))
        
        menu.addSeparator()
        
        # 3. Restore (available for all snapshots — first, last, only, current)
        restore = menu.addAction("Restore to this snapshot")
        restore.triggered.connect(lambda: self.restore_requested.emit(snap.snapshot_id))
        
        menu.exec(self.mapToGlobal(pos))
    
    def toggle_branch(self, indicator_id: str) -> bool:
        """Toggle branch expansion with bloodline logic.
        
        Each fork can have at most ONE open child fork.
        When opening a fork would cause its parent to have >1 open children,
        close sibling forks to maintain the rule.
        """
        import sys
        if indicator_id in self._expanded_branches:
            sys.stderr.write(f"[TOGGLE] Closing {indicator_id}\n")
            self._expanded_branches.remove(indicator_id)
            # Track which fork is being collapsed for sucking animation
            self._sucking_fork_id = indicator_id
        else:
            sys.stderr.write(f"[TOGGLE] Opening {indicator_id}\n")
            # Clear sucking fork - we're expanding, not collapsing
            self._sucking_fork_id = None
            sys.stderr.write(f"[TOGGLE] Before: {self._expanded_branches}\n")
            if TIMELINE_SINGLE_BRANCH_ONLY:
                sys.stderr.write(f"[TOGGLE] SINGLE_BRANCH_ONLY active\n")
                # Get the branching point (parent) of this fork
                parent_id = indicator_id.replace("alt_indicator_", "")
                sys.stderr.write(f"[TOGGLE] New fork parent_id={parent_id}\n")
                
                # Build layout ONCE for consistent lane calculation
                current_layout = self._engine.build_layout()
                
                # Calculate the lane for the new fork using the layout
                new_fork_lane = self._get_fork_lane(indicator_id, current_layout)
                sys.stderr.write(f"[TOGGLE] New fork will be at lane: {new_fork_lane}\n")
                
                # BLOODLINE RULE: Only one fork open per lane level
                # Fold competing bloodlines at the same lane BEFORE opening new fork
                # Pass the same layout for consistent lane calculation
                self._fold_competing_bloodlines(new_fork_lane, current_layout)
                    
                sys.stderr.write(f"[TOGGLE] After cleanup: {self._expanded_branches}\n")
                    
            self._expanded_branches.add(indicator_id)
            sys.stderr.write(f"[TOGGLE] Final: {self._expanded_branches}\n")
        return True
    
    def _is_in_subtree(self, snapshot_id: str, ancestor_id: str) -> bool:
        """Check if snapshot_id is equal to or a descendant of ancestor_id."""
        if snapshot_id == ancestor_id:
            return True
        current = snapshot_id
        visited = set()
        while current and current not in visited:
            visited.add(current)
            for snap in self._engine._snapshots:
                if snap.snapshot_id == current and snap.parent_id:
                    if snap.parent_id == ancestor_id:
                        return True
                    current = snap.parent_id
                    break
            else:
                break
        return False
    
    def _get_depth_in_subtree(self, snapshot_id: str, ancestor_id: str) -> int:
        """Get depth of snapshot_id in subtree of ancestor_id. 0 if same, -1 if not in subtree."""
        if snapshot_id == ancestor_id:
            return 0
        depth = 0
        current = snapshot_id
        visited = set()
        while current and current not in visited:
            visited.add(current)
            depth += 1
            for snap in self._engine._snapshots:
                if snap.snapshot_id == current and snap.parent_id:
                    if snap.parent_id == ancestor_id:
                        return depth
                    current = snap.parent_id
                    break
            else:
                break
        return -1
    
    def _is_on_main_path(self, snapshot_id: str) -> bool:
        """Check if a snapshot is on the main path (follows main branch from root)."""
        # Build main path set
        main_path_ids = set()
        for snap in self._engine._snapshots:
            if snap.branch_name == "main":
                main_path_ids.add(snap.snapshot_id)
        return snapshot_id in main_path_ids
    
    def _get_fork_lane(self, fork_id: str, layout: Optional[List] = None) -> int:
        """Get lane level for a fork based on visual indent in layout.
        
        Lane = visual indent + 1
        
        The visual indent is determined by where the fork's branching point
        appears in the layout. This ensures the lane number in {}
        always matches the actual visual indentation level.
        """
        if fork_id == "alt_indicator_meta":
            return 0
        
        fork_parent = fork_id.replace("alt_indicator_", "")
        
        # Use provided layout or build new one
        nodes = layout if layout is not None else self._engine.build_layout()
        
        # Find the parent snapshot in the layout to get its indent
        for node in nodes:
            if node.snapshot.snapshot_id == fork_parent:
                # Fork indicator appears at parent's indent + 1
                return node.indent + 1
        
        # Default to lane 1 if parent not found
        return 1
    
    def _fold_competing_bloodlines(self, target_lane: int, layout: Optional[List] = None) -> set:
        """Close all forks at the target lane level (competing bloodlines).
        
        STRICT RULE: Only ONE fork can be open at each lane level globally.
        When opening a fork at lane N, ALL other forks at lane N are closed.
        
        Uses provided layout (or builds one) to calculate visual lanes consistently.
        
        Returns:
            Set of fork IDs that were closed
        """
        import sys
        closed = set()
        
        sys.stderr.write(f"\n[ENFORCER] ============================================\n")
        sys.stderr.write(f"[ENFORCER] FOLDING competing bloodlines at LANE {target_lane}\n")
        sys.stderr.write(f"[ENFORCER] Input: target_lane={target_lane}\n")
        
        # Show all expanded branches at start
        sys.stderr.write(f"[ENFORCER] Current _expanded_branches: {self._expanded_branches}\n")
        
        # Use provided layout or build new one for consistent lane calculation
        nodes = layout if layout is not None else self._engine.build_layout()
        
        # Build register of open forks by lane with detailed calculation
        sys.stderr.write(f"[ENFORCER] Building lane register...\n")
        lane_register = {}
        for eid in self._expanded_branches:
            fork_parent = eid.replace("alt_indicator_", "")
            eid_lane = self._get_fork_lane(eid, nodes)
            if eid_lane not in lane_register:
                lane_register[eid_lane] = []
            lane_register[eid_lane].append(eid)
            sys.stderr.write(f"[ENFORCER]   {eid} -> parent={fork_parent} -> lane={eid_lane}\n")
        
        sys.stderr.write(f"[ENFORCER] === LANE REGISTER ===\n")
        for lane, forks in sorted(lane_register.items()):
            sys.stderr.write(f"[ENFORCER]   Lane {lane}: {forks} (count={len(forks)})\n")
        
        # STRICT: Close ALL forks at target lane and ALL lanes >= target_lane
        # This ensures only one bloodline is open at any given depth
        sys.stderr.write(f"[ENFORCER] Closing all forks at lane >= {target_lane}...\n")
        for lane in list(lane_register.keys()):
            if lane >= target_lane:
                forks_at_lane = lane_register[lane]
                sys.stderr.write(f"[ENFORCER]   Found {len(forks_at_lane)} fork(s) at lane {lane}: {forks_at_lane}\n")
                
                # Close all forks at this lane
                for fork_id in forks_at_lane:
                    sys.stderr.write(f"[ENFORCER]   -> CLOSING {fork_id} at lane {lane}\n")
                    closed.add(fork_id)
                    self._expanded_branches.discard(fork_id)
                    sys.stderr.write(f"[ENFORCER]      _expanded_branches now: {self._expanded_branches}\n")
        
        sys.stderr.write(f"[ENFORCER] Result: closed {len(closed)} fork(s): {closed}\n")
        sys.stderr.write(f"[ENFORCER] Final _expanded_branches: {self._expanded_branches}\n")
        sys.stderr.write(f"[ENFORCER] ============================================\n\n")
        
        return closed
    
    def _get_fork_ancestor_chain(self, snapshot_id: str) -> set:
        """Get all fork IDs that are ancestors of this snapshot.
        
        Walk up the tree and collect IDs of open forks whose branching point
        (parent snapshot) is an ancestor of the given snapshot.
        """
        fork_ancestors = set()
        current_id = snapshot_id
        visited = set()
        
        while current_id and current_id not in visited:
            visited.add(current_id)
            
            # Check if there's an open fork whose branching point is current_id
            for fork_id in self._expanded_branches:
                fork_branch_point = fork_id.replace("alt_indicator_", "")
                if fork_branch_point == current_id:
                    fork_ancestors.add(fork_id)
            
            # Move up to parent
            parent_found = False
            for snap in self._engine._snapshots:
                if snap.snapshot_id == current_id and snap.parent_id:
                    current_id = snap.parent_id
                    parent_found = True
                    break
            if not parent_found:
                break
        
        return fork_ancestors
    
    def _is_main_branch_leaf(self, node, layout) -> bool:
        """Check if node is the leaf (last node) of the main branch.
        
        Main branch leaf = indent == 0 and no children on main branch.
        """
        # Must be on main spine (indent == 0)
        if node.indent != 0:
            return False
        
        # Check if any other node has this snapshot as parent
        snap_id = node.snapshot.snapshot_id
        for n in layout:
            if getattr(n.snapshot, 'parent_id', None) == snap_id:
                return False  # Has a child, so not a leaf
        
        return True
    
    def _get_content_width(self) -> int:
        """Calculate content width based on actual content (descriptions + layout)."""
        layout = self._get_cached_layout()
        if not layout:
            return 400
        max_indent = max((node.indent for node in layout), default=0)
        
        # Calculate max description width using font metrics
        # IMPORTANT: Must use same font as drawing code (Inter, 10pt)
        max_desc_width = 0
        font_metrics = QtGui.QFontMetrics(QtGui.QFont("Inter", 10))
        for node in layout:
            desc = getattr(node.snapshot, 'description', '')
            if desc:
                # Add space for node icon and padding
                text_width = font_metrics.horizontalAdvance(desc)
                max_desc_width = max(max_desc_width, text_width)
        
        # Content width = timestamp column + spine position + indent + node icon + description + padding
        # IMPORTANT: Must include TIMESTAMP_COLUMN_WIDTH because painter.translate() shifts everything right
        node_icon_space = 30  # Space for node circle and gap to text
        scrollbar_buffer = 30  # Extra space for padding and scrollbar margin
        content_width = (self.TIMESTAMP_COLUMN_WIDTH + self.SPINE_X + max_indent * self.INDENT + 
                        node_icon_space + max_desc_width + scrollbar_buffer)
        result = max(content_width, 500)
        return result
    
    def sizeHint(self) -> QtCore.QSize:
        """Suggest size based on content."""
        layout = self._get_cached_layout()
        if not layout:
            return QtCore.QSize(400, 200)

        # Calculate height based on number of nodes
        height = max(len(layout) * self.ROW_HEIGHT + 20, 200)

        # Use content width for consistent sizing
        width = self._get_content_width()

        return QtCore.QSize(width, height)

    def minimumSizeHint(self) -> QtCore.QSize:
        """Minimum size based on content - forces scrollbars when content exceeds viewport."""
        layout = self._get_cached_layout()
        if not layout:
            return QtCore.QSize(400, 200)

        # Same as sizeHint so widget is always at least as large as content
        height = max(len(layout) * self.ROW_HEIGHT + 20, 200)
        width = self._get_content_width()

        return QtCore.QSize(width, height)

    def _update_size(self):
        """Update widget size based on current layout."""
        # Force layout rebuild so we calculate size based on current data
        self._layout_dirty = True
        layout = self._get_cached_layout()
        if not layout:
            return
        
        # Calculate height based on number of nodes
        height = max(len(layout) * self.ROW_HEIGHT + 20, 200)
        
        # Use content width for consistent sizing
        width = self._get_content_width()
        
        # Set minimum size to force scroll area to show scrollbars when needed
        self.setMinimumWidth(width)
        self.resize(width, height)
        
        # Force scroll area to re-evaluate
        self.updateGeometry()
    
    def _start_position_animation(self, duration: int = 300):
        """Start animating node positions from T0 to T1."""
        # Stop any existing animation
        if self._anim_timer is not None:
            self._anim_timer.stop()
        
        self._anim_progress = 0.0
        self._anim_timer = QtCore.QTimer(self)
        
        start_time = QtCore.QDateTime.currentMSecsSinceEpoch()
        
        def on_frame():
            elapsed = QtCore.QDateTime.currentMSecsSinceEpoch() - start_time
            if elapsed >= duration:
                self._anim_progress = 1.0
                self._anim_timer.stop()
                self._prev_layout_state.clear()
                self._prev_fork_positions.clear()
                self._exiting_nodes.clear()
                self._sucking_fork_id = None  # Clear after animation completes
            else:
                t = elapsed / duration
                self._anim_progress = 1 - (1 - t) ** 3  # OutCubic easing
            self.repaint()
        
        self._anim_timer.timeout.connect(on_frame)
        self._anim_timer.start(16)  # ~60fps
    
    def _format_time(self, dt) -> str:
        """Format datetime (for backward compatibility)."""
        return dt.strftime("%Y-%b-%d %H:%M:%S")
    
    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        """Track hover for subtle visual feedback and show tooltips."""
        # Skip hover during animation to prevent interference
        if TIMELINE_ANIMATE_TRANSITIONS and self._anim_progress < 1.0:
            return
        
        y = int(event.position().y())
        prev_hovered = getattr(self, '_hovered_id', None)
        
        layout = self._get_cached_layout()
        for node in layout:
            if node.y <= y <= node.y + self.ROW_HEIGHT:
                snap = node.snapshot
                is_indicator = getattr(snap, 'is_alt_indicator', False)
                
                # Set hover for ANY node (including fork indicators)
                self._hovered_id = snap.snapshot_id
                if self._hovered_id != prev_hovered:
                    self.update()
                
                # Build and show tooltip (truncate description to 70 chars)
                desc = snap.description or ""
                if len(desc) > 70:
                    desc = desc[:70] + "..."
                
                if TIMELINE_DEBUG_TOOLTIPS:
                    # Detailed debug tooltip
                    tooltip_parts = [f"ID: {snap.snapshot_id}"]
                    tooltip_parts.append(f"Desc: {desc}")
                    if not is_indicator:
                        tooltip_parts.append(f"Branch: {snap.branch_name}")
                        tooltip_parts.append(f"Type: {snap.type.value}")
                    else:
                        tooltip_parts.append(f"Type: indicator")
                    parent_id = getattr(snap, 'parent_id', None)
                    if parent_id:
                        tooltip_parts.append(f"Parent: {parent_id}")
                    # Add color info
                    color_hex = getattr(self, '_node_colors', {}).get(snap.snapshot_id, "#555")
                    is_color_root = snap.snapshot_id in getattr(self, '_root_colors', {})
                    if is_color_root:
                        tooltip_parts.append(f"Color: {color_hex} (ROOT)")
                    else:
                        tooltip_parts.append(f"Color: {color_hex}")
                    self.setToolTip("\n".join(tooltip_parts))
                else:
                    # Simple tooltip - just description (truncated)
                    self.setToolTip(desc)
                return
        
        # Not hovering any row
        if prev_hovered is not None:
            self._hovered_id = None
            self.update()
            self.setToolTip("")
    
    def leaveEvent(self, event):
        """Clear hover when mouse leaves widget."""
        if getattr(self, '_hovered_id', None) is not None:
            self._hovered_id = None
            self.update()
            self.setToolTip("")
