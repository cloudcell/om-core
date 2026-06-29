"""Timeline Engine - Headless data and logic layer.

Manages snapshot tree structure, color inheritance, and CRUD operations.
No GUI dependencies - can be used headless (CLI, server, tests).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set, Tuple
from datetime import datetime, timezone
from collections import defaultdict
import uuid
import sys

from .models import SnapshotInfo, SnapshotType
from .timelineconf import TIMELINE_DEBUG_ROOT_FORK, TIMELINE_DEBUG_OPEN_FORKS_STATS, TIMELINE_FORK_METADATA


@dataclass
class _TreeNode:
    """Internal tree node for layout calculation."""
    snapshot: SnapshotInfo
    row: int
    indent: int  # 0 = main spine, 1+ = branch lanes
    is_main_path: bool = True
    y: int = 0
    alternative_count: int = 0


class TimelineEngine:
    """Headless engine for timeline data management.
    
    Responsibilities:
    - Store and manage snapshot tree structure
    - Compute color inheritance
    - Handle CRUD operations (restore, rename, create, delete)
    - Provide flat layout for visualization
    
    No GUI dependencies - pure data layer.
    """
    
    def __init__(self):
        self._snapshots: List[SnapshotInfo] = []
        self._current_id: Optional[str] = None
        self._expanded_branches: Set[str] = set()
        
        # Color management
        self._branch_color_map: Dict[str, str] = {}
        self._node_colors: Dict[str, str] = {}
        self._node_to_root: Dict[str, str] = {}  # node_id -> root_node_id
    
    # ===================================================================
    # Data Loading / Access
    # ===================================================================
    
    def load_snapshots(self, snapshots: List[SnapshotInfo]) -> None:
        """Load snapshot data."""
        self._snapshots = list(snapshots)
        # Find current (latest exact main branch)
        self._current_id = None
        for snap in reversed(self._snapshots):
            if snap.branch_name == "main":
                self._current_id = snap.snapshot_id
                break
        self._compute_colors()
    
    def get_snapshots(self) -> List[SnapshotInfo]:
        """Get current snapshot list for persistence."""
        return list(self._snapshots)
    
    def get_current_id(self) -> Optional[str]:
        """Get current snapshot ID."""
        return self._current_id
    
    def get_snapshot(self, snapshot_id: str) -> Optional[SnapshotInfo]:
        """Get specific snapshot by ID."""
        for snap in self._snapshots:
            if snap.snapshot_id == snapshot_id:
                return snap
        return None
    
    # ===================================================================
    # Tree Layout (for visualization)
    # ===================================================================
    
    def build_layout(self) -> List[_TreeNode]:
        """Build flat layout with branch expansion handled.
        
        Returns list of tree nodes ready for rendering.
        """
        if not self._snapshots:
            return []
        
        # Build lookup tables
        id_to_snap: Dict[str, SnapshotInfo] = {}
        children_map: Dict[str, List[SnapshotInfo]] = defaultdict(list)
        
        for snap in self._snapshots:
            id_to_snap[snap.snapshot_id] = snap
            if snap.parent_id:
                children_map[snap.parent_id].append(snap)
        
        # Find root
        root = None
        for snap in self._snapshots:
            if snap.parent_id is None:
                root = snap
                break
        if not root:
            root = self._snapshots[0]
        
        # Build main path - only follow exact "main" branch, not "main-alt-*"
        main_path: List[SnapshotInfo] = []
        current: Optional[SnapshotInfo] = root
        visited: Set[str] = set()
        
        while current and current.snapshot_id not in visited:
            visited.add(current.snapshot_id)
            main_path.append(current)
            children = children_map.get(current.snapshot_id, [])
            if children:
                # Find main branch child (exact match only)
                main_child = None
                for c in children:
                    if c.branch_name == "main":
                        main_child = c
                        break
                # If no main child, just end the main path
                current = main_child
            else:
                current = None
        
        # Debug: show main path
        print(f"[LAYOUT DEBUG] Main path ({len(main_path)} nodes):", file=sys.stderr)
        for snap in main_path:
            print(f"[LAYOUT DEBUG]   {snap.snapshot_id[:8]}: {snap.description[:30]} (branch={snap.branch_name})", file=sys.stderr)
        
        # Build flat list
        nodes: List[_TreeNode] = []
        row = 0
        y = 10
        
        # Helper to count all descendants in a branch (defined early for use by meta-fork)
        def count_descendants(snap_id: str, visited: set = None) -> int:
            if visited is None:
                visited = set()
            if snap_id in visited:
                return 0
            visited.add(snap_id)
            children = children_map.get(snap_id, [])
            count = len(children)
            for c in children:
                count += count_descendants(c.snapshot_id, visited)
            return count
        
        # DEBUG: Add virtual meta-fork as ultimate root (only if enabled)
        if TIMELINE_DEBUG_ROOT_FORK:
            meta_fork_id = "alt_indicator_meta"
            meta_is_expanded = meta_fork_id in self._expanded_branches
            
            if TIMELINE_DEBUG_OPEN_FORKS_STATS:
                meta_open_count = self._count_immediate_open_child_forks("meta_root")
                meta_desc = f"ROOT ({meta_open_count} open)"
            else:
                meta_desc = "ROOT"
            
            meta_fork = SnapshotInfo(
                snapshot_id=meta_fork_id,
                parent_id="meta_root",
                description=meta_desc,
                branch_name="meta",
                created_at=root.created_at,
                type=SnapshotType.BRANCH,
                is_alt_indicator=True,
            )
            meta_fork.alt_count = 0
            meta_fork.is_expanded = meta_is_expanded
            
            # Add the meta-fork node
            nodes.append(_TreeNode(
                snapshot=meta_fork,
                row=row,
                indent=0,
                is_main_path=False,
                y=y
            ))
            row += 1
            y += 34
        
        for node in main_path:
            children = children_map.get(node.snapshot_id, [])
            alt_children = [c for c in children if c not in main_path]
            # Count ALL descendants in alternative branches
            total_alt_count = 0
            for alt in alt_children:
                total_alt_count += 1 + count_descendants(alt.snapshot_id)
            
            # Mark node as branch point if it has alternatives
            node.is_branch_point = total_alt_count > 0
            
            # Add main path node
            tree_node = _TreeNode(
                snapshot=node,
                row=row,
                indent=0,
                is_main_path=True,
                y=y,
                alternative_count=total_alt_count
            )
            nodes.append(tree_node)
            row += 1
            y += 34  # ROW_HEIGHT
            
            # Add ONE branch indicator for all alternatives (if any exist)
            if alt_children:
                indicator_id = f"alt_indicator_{node.snapshot_id}"
                is_expanded = indicator_id in self._expanded_branches
                
                # Count immediate open child forks for debug display
                if TIMELINE_DEBUG_OPEN_FORKS_STATS:
                    open_child_count = self._count_immediate_open_child_forks(node.snapshot_id)
                    open_debug = f" ({open_child_count})"
                else:
                    open_debug = ""
                
                # Calculate lane using same logic as widget
                fork_lane = self._get_fork_lane(indicator_id, 0)
                
                # Build description: (X) format for alternative count
                if TIMELINE_FORK_METADATA:
                    fork_desc = f"({total_alt_count}) {{{fork_lane}}}{open_debug}"
                else:
                    fork_desc = f"({total_alt_count})"
                
                # Create single indicator for all alternatives
                indicator = SnapshotInfo(
                    snapshot_id=indicator_id,
                    parent_id=node.snapshot_id,
                    description=fork_desc,
                    branch_name="branches",
                    created_at=alt_children[0].created_at,
                    type=SnapshotType.BRANCH,
                    is_alt_indicator=True,
                )
                indicator.alt_count = total_alt_count
                indicator.is_expanded = is_expanded
                
                ind_node = _TreeNode(
                    snapshot=indicator,
                    row=row,
                    indent=1,
                    is_main_path=False,
                    y=y
                )
                nodes.append(ind_node)
                row += 1
                y += 34
                
                # Add expanded branch subtrees for ALL alternatives
                if is_expanded:
                    for alt in alt_children:
                        branch_nodes = self._build_branch_subtree(alt, children_map, row, y, indent=2)
                        nodes.extend(branch_nodes)
                        row += len(branch_nodes)
                        for n in branch_nodes:
                            y += 34
        
        return nodes
    
    def _build_branch_subtree(
        self, start: SnapshotInfo,
        children_map: Dict[str, List[SnapshotInfo]],
        start_row: int, start_y: int, indent: int,
        visited: Optional[Set[str]] = None
    ) -> List[_TreeNode]:
        """Build full subtree for a branch, including nested branches."""
        if visited is None:
            visited = set()
        
        nodes: List[_TreeNode] = []
        row = start_row
        y = start_y
        
        # Build linear path for this branch
        current: Optional[SnapshotInfo] = start
        path_nodes: List[SnapshotInfo] = []
        
        while current and current.snapshot_id not in visited:
            visited.add(current.snapshot_id)
            path_nodes.append(current)
            
            # Follow same branch
            children = children_map.get(current.snapshot_id, [])
            same_branch = [c for c in children if c.branch_name == current.branch_name]
            current = same_branch[0] if same_branch else None
        
        # Add path nodes with their alternative children
        for node in path_nodes:
            # Check for alternative children
            children = children_map.get(node.snapshot_id, [])
            alt_children = [c for c in children if c.snapshot_id not in visited 
                          and c.branch_name != node.branch_name]
            
            # Mark as branch point if has alternatives
            node.is_branch_point = len(alt_children) > 0
            
            # Add the node
            nodes.append(_TreeNode(
                snapshot=node,
                row=row,
                indent=indent,
                is_main_path=False,
                y=y
            ))
            row += 1
            y += 34
            
            if alt_children:
                # Count descendants in these alternatives
                def count_descendants(snap_id: str, visited2: set) -> int:
                    if snap_id in visited2:
                        return 0
                    visited2.add(snap_id)
                    children2 = children_map.get(snap_id, [])
                    count = len(children2)
                    for c in children2:
                        count += count_descendants(c.snapshot_id, visited2)
                    return count
                
                total_alt = sum(1 + count_descendants(c.snapshot_id, set()) for c in alt_children)
                
                # Create indicator for nested alternatives
                indicator_id = f"alt_indicator_{node.snapshot_id}"
                is_expanded = indicator_id in self._expanded_branches
                
                # Count immediate open child forks for debug display
                if TIMELINE_DEBUG_OPEN_FORKS_STATS:
                    open_child_count = self._count_immediate_open_child_forks(node.snapshot_id)
                    open_debug = f" ({open_child_count})"
                else:
                    open_debug = ""
                
                # Calculate lane using same logic as widget
                # Fork indicator appears at indent+1, so lane = indent+1
                fork_lane = self._get_fork_lane(indicator_id, indent)
                
                # Build description: (X) format for alternative count
                if TIMELINE_FORK_METADATA:
                    fork_desc = f"({total_alt}) {{{fork_lane}}}{open_debug}"
                else:
                    fork_desc = f"({total_alt})"
                
                indicator = SnapshotInfo(
                    snapshot_id=indicator_id,
                    parent_id=node.snapshot_id,
                    description=fork_desc,
                    branch_name="branches",
                    created_at=alt_children[0].created_at,
                    type=SnapshotType.BRANCH,
                    is_alt_indicator=True,
                )
                indicator.alt_count = total_alt
                indicator.is_expanded = is_expanded
                
                nodes.append(_TreeNode(
                    snapshot=indicator,
                    row=row,
                    indent=indent + 1,
                    is_main_path=False,
                    y=y
                ))
                row += 1
                y += 34
                
                # Recursively add expanded nested branches
                if is_expanded:
                    for alt in alt_children:
                        sub_nodes = self._build_branch_subtree(
                            alt, children_map, row, y, indent + 2, visited
                        )
                        nodes.extend(sub_nodes)
                        row += len(sub_nodes)
                        for n in sub_nodes:
                            y += 34
        
        return nodes
    
    def _count_immediate_open_child_forks(self, parent_snapshot_id: str) -> int:
        """Count how many immediate child forks are currently open.
        
        A fork is counted if its branching point (parent snapshot)
        is a strict descendant of parent_snapshot_id AND the fork is at
        a deeper lane level (visually nested under this fork).
        
        Special case: "meta_root" counts forks whose parent is on main path.
        """
        count = 0
        this_fork_id = f"alt_indicator_{parent_snapshot_id}"
        
        # Calculate lane (depth) for each open fork
        # Lane = number of expanded forks that contain this fork + 1
        def get_fork_lane(fork_id: str) -> int:
            """Calculate lane level: how many expanded forks contain this fork."""
            if fork_id == "alt_indicator_meta":
                return 0  # Meta-fork is at lane 0
            fork_parent = fork_id.replace("alt_indicator_", "")
            lane = 1  # Start at lane 1 for root-level forks
            # Count how many expanded forks contain this fork's parent
            for other_id in self._expanded_branches:
                if other_id == fork_id:
                    continue
                other_parent = other_id.replace("alt_indicator_", "")
                if self._is_in_subtree(fork_parent, other_parent):
                    lane += 1
            return lane
        
        # Special case: meta_root
        if parent_snapshot_id == "meta_root":
            count = 0
            for fork_id in self._expanded_branches:
                if fork_id == this_fork_id:
                    continue
                # Root-level forks are at lane 1
                if get_fork_lane(fork_id) == 1:
                    count += 1
            return count
        
        # Get parent fork's lane
        parent_lane = get_fork_lane(this_fork_id)
        
        # Count forks where:
        # 1. The fork's parent is a strict descendant of parent_snapshot_id (in the subtree)
        # 2. The fork's lane is greater than parent_lane (visually nested under this fork)
        for fork_id in self._expanded_branches:
            if fork_id == this_fork_id:
                continue
            fork_parent = fork_id.replace("alt_indicator_", "")
            # Check if this fork's parent is a strict descendant (in the subtree)
            is_desc = self._is_strict_descendant(fork_parent, parent_snapshot_id)
            fork_lane = get_fork_lane(fork_id)
            is_nested = fork_lane > parent_lane
            if not is_desc:
                continue
            if is_nested:
                count += 1
        
        return count
    
    def _is_strict_descendant(self, snapshot_id: str, ancestor_id: str) -> bool:
        """Check if snapshot_id is a STRICT descendant of ancestor_id (not equal)."""
        if snapshot_id == ancestor_id:
            return False
        current = snapshot_id
        visited = set()
        while current and current not in visited:
            visited.add(current)
            for snap in self._snapshots:
                if snap.snapshot_id == current and snap.parent_id:
                    if snap.parent_id == ancestor_id:
                        return True
                    current = snap.parent_id
                    break
            else:
                break
        return False
    
    def _is_in_subtree(self, snapshot_id: str, ancestor_id: str) -> bool:
        """Check if snapshot_id is equal to or a descendant of ancestor_id."""
        if snapshot_id == ancestor_id:
            return True
        current = snapshot_id
        visited = set()
        while current and current not in visited:
            visited.add(current)
            for snap in self._snapshots:
                if snap.snapshot_id == current and snap.parent_id:
                    if snap.parent_id == ancestor_id:
                        return True
                    current = snap.parent_id
                    break
            else:
                break
        return False
    
    def _get_fork_lane(self, fork_id: str, parent_indent: int = 0) -> int:
        """Calculate lane level for a fork based on visual indent.
        
        Lane = parent_indent + 1
        This MUST match the widget's calculation for bloodline enforcement.
        
        The lane reflects the actual visual indentation level where the fork
        indicator appears in the layout.
        """
        if fork_id == "alt_indicator_meta":
            return 0
        
        # Lane is simply the visual indent + 1
        # The fork indicator appears at parent_indent + 1
        return parent_indent + 1
    
    # ===================================================================
    # Color Management
    # ===================================================================
    
    def _nice_color(self, key: str) -> Tuple[int, int, int]:
        """Generate vivid deterministic color from key hash."""
        import colorsys
        import hashlib

        # Stable deterministic hash in [0, 1)
        digest = hashlib.sha1(key.encode("utf-8")).digest()
        hue_int = int.from_bytes(digest[:8], "big")
        h = (hue_int / float(1 << 64)) % 1.0

        # Keep colors vivid but not neon
        s = 0.62
        v = 0.88

        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return int(r * 255), int(g * 255), int(b * 255)
    
    def _get_node_color(self, snap: SnapshotInfo) -> str:
        """Get color for node based on description."""
        desc = snap.description
        if desc not in self._branch_color_map:
            r, g, b = self._nice_color(desc)
            self._branch_color_map[desc] = f"#{r:02x}{g:02x}{b:02x}"
        return self._branch_color_map[desc]
    
    def get_color_for_key(self, key: str) -> str:
        """Generate a color from a key (e.g., description). Used for color roots."""
        if key not in self._branch_color_map:
            r, g, b = self._nice_color(key)
            self._branch_color_map[key] = f"#{r:02x}{g:02x}{b:02x}"
        return self._branch_color_map[key]
    
    def _compute_colors(self) -> None:
        """Compute color inheritance for all nodes."""
        layout = self.build_layout()
        
        node_colors: Dict[str, str] = {}
        root_colors: Dict[str, str] = {}
        node_to_root: Dict[str, str] = {}
        
        # First pass: main path
        for idx, node in enumerate(layout):
            if node.indent == 0:
                snap = node.snapshot
                parent_id = getattr(snap, 'parent_id', None)
                
                # Check if parent is also on main path
                can_inherit = False
                if parent_id and parent_id in node_colors:
                    for p in layout:
                        if p.snapshot.snapshot_id == parent_id and p.indent == 0:
                            can_inherit = True
                            break
                
                if can_inherit:
                    node_colors[snap.snapshot_id] = node_colors[parent_id]
                    node_to_root[snap.snapshot_id] = node_to_root[parent_id]
                else:
                    node_colors[snap.snapshot_id] = self._get_node_color(snap)
                    root_colors[snap.snapshot_id] = node_colors[snap.snapshot_id]
                    node_to_root[snap.snapshot_id] = snap.snapshot_id
        
        # Second pass: branch nodes
        for idx, node in enumerate(layout):
            snap = node.snapshot
            indent = node.indent
            
            if getattr(snap, 'is_alt_indicator', False):
                node_colors[snap.snapshot_id] = "#555"
                node_to_root[snap.snapshot_id] = "indicator"
            elif indent > 0:
                my_parent_id = getattr(snap, 'parent_id', None)
                
                # Fork detection
                parent_is_fork = False
                parent_indent = -1
                if my_parent_id:
                    children_indents = set()
                    for n in layout:
                        if getattr(n.snapshot, 'parent_id', None) == my_parent_id:
                            children_indents.add(n.indent)
                    parent_is_fork = len(children_indents) > 1
                    
                    for p in layout:
                        if p.snapshot.snapshot_id == my_parent_id:
                            parent_indent = p.indent
                            break
                
                # Determine if color root
                is_color_root = False
                parent_is_indicator = False
                
                if my_parent_id:
                    for p in layout:
                        if p.snapshot.snapshot_id == my_parent_id:
                            if getattr(p.snapshot, 'is_alt_indicator', False):
                                parent_is_indicator = True
                            break
                
                if not my_parent_id:
                    is_color_root = True
                    reason = "no_parent"
                elif parent_is_fork and parent_indent != indent:
                    is_color_root = True
                    reason = "parent_is_fork"
                elif parent_is_indicator:
                    is_color_root = True
                    reason = "parent_is_indicator"
                elif parent_indent != indent:
                    is_color_root = True
                    reason = "indent_change"
                else:
                    reason = "inherit"
                
                if is_color_root:
                    color = self._get_node_color(snap)
                    root_colors[snap.snapshot_id] = color
                    node_colors[snap.snapshot_id] = color
                    node_to_root[snap.snapshot_id] = snap.snapshot_id
                    print(f"[COLOR DEBUG] Color root: {snap.snapshot_id[:8]} ({snap.description[:20]}) reason={reason} color={color}", file=sys.stderr)
                else:
                    print(f"[COLOR DEBUG] Inherit: {snap.snapshot_id[:8]} ({snap.description[:20]}) parent={my_parent_id[:8] if my_parent_id else None} parent_indent={parent_indent} my_indent={indent}", file=sys.stderr)
                    # Inherit from sibling or parent
                    sibling_root = None
                    for prev_idx in range(idx - 1, -1, -1):
                        prev = layout[prev_idx]
                        if prev.indent < indent:
                            break
                        if prev.indent == indent:
                            if getattr(prev.snapshot, 'is_alt_indicator', False):
                                break
                            if getattr(prev.snapshot, 'parent_id', None) == my_parent_id:
                                sibling_root = node_to_root.get(prev.snapshot.snapshot_id)
                                break
                    
                    if sibling_root and sibling_root in root_colors:
                        node_colors[snap.snapshot_id] = root_colors[sibling_root]
                        node_to_root[snap.snapshot_id] = sibling_root
                    elif my_parent_id and my_parent_id in root_colors:
                        node_colors[snap.snapshot_id] = root_colors[my_parent_id]
                        node_to_root[snap.snapshot_id] = my_parent_id
                    else:
                        color = self._get_node_color(snap)
                        node_colors[snap.snapshot_id] = color
                        node_to_root[snap.snapshot_id] = snap.snapshot_id
        
        self._node_colors = node_colors
        self._node_to_root = node_to_root
    
    def get_node_color(self, snapshot_id: str) -> str:
        """Get computed color for a node."""
        return self._node_colors.get(snapshot_id, "#555")
    
    # ===================================================================
    # CRUD Operations
    # ===================================================================
    
    def restore_to_snapshot(self, snapshot_id: str, description: Optional[str] = None) -> Optional[str]:
        """Restore to snapshot - creates new snapshot on restored branch.
        
        Logic from perfect_timeline.py:
        1. If target is non-main branch, promote it to main
        2. Move old main to alternative branch
        3. Create new snapshot as child of restored snapshot
        4. Current snapshot stays at bottom (end of timeline)
        
        Returns:
            New snapshot ID, or None if target not found
        """
        import uuid
        
        target = None
        for snap in self._snapshots:
            if snap.snapshot_id == snapshot_id:
                target = snap
                break
        
        if not target:
            return None
        
        # Get timestamps for ordering
        now = datetime.now(timezone.utc)
        
        # If restoring to non-main branch, promote it to main
        if target.branch_name != "main":
            old_main_branch = "main"
            new_main_branch = target.branch_name
            
            # Move current main to a new alternative branch
            alt_branch = self._find_next_alt_branch("main")
            for s in self._snapshots:
                if s.branch_name == old_main_branch:
                    s.branch_name = alt_branch
            
            # Promote target branch to main (all snapshots on that branch)
            for s in self._snapshots:
                if s.branch_name == new_main_branch:
                    s.branch_name = "main"
            
            # Also promote all ancestors of target that lead to root
            # This ensures the entire history chain becomes main
            current_id = target.parent_id
            visited = set()
            while current_id and current_id not in visited:
                visited.add(current_id)
                for s in self._snapshots:
                    if s.snapshot_id == current_id:
                        s.branch_name = "main"
                        current_id = s.parent_id
                        break
                else:
                    break
        
        # Handle future commits on main (snapshots after target)
        future_snaps = []
        # Ensure target.created_at has timezone for comparison
        target_time = target.created_at
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)
        
        for s in self._snapshots:
            s_time = s.created_at
            if s_time.tzinfo is None:
                s_time = s_time.replace(tzinfo=timezone.utc)
            if s.branch_name == "main" and s_time > target_time:
                future_snaps.append(s)
        
        if future_snaps:
            # Move future snapshots to alternative branch
            alt_branch = self._find_next_alt_branch("main")
            for s in future_snaps:
                s.branch_name = alt_branch
        
        # Restructure parent links so main branch forms a continuous spine
        self._restructure_main_branch(target)
        
        # Create new snapshot as child of restored target (at bottom of timeline)
        new_id = str(uuid.uuid4())
        new_desc = description or f"Restored from {target.description}"
        new_snap = SnapshotInfo(
            snapshot_id=new_id,
            parent_id=target.snapshot_id,
            description=new_desc,
            branch_name="main",  # New work continues on main
            created_at=now,
            type=SnapshotType.MANUAL,
        )
        
        self._snapshots.append(new_snap)
        self._current_id = new_id
        self._compute_colors()
        
        # After restore, collapse all root-level forks
        self._collapse_root_forks_after_restore(target.snapshot_id)
        
        return new_id
    
    def _collapse_root_forks_after_restore(self, target_snapshot_id: str):
        """After restore, collapse ALL root-level forks completely."""
        import sys
        
        # Build main path set
        main_path_ids = set()
        for snap in self._snapshots:
            if snap.branch_name == "main":
                main_path_ids.add(snap.snapshot_id)
        
        # Find all root-level forks (forks whose parent is on main path)
        root_forks = []
        for fork_id in list(self._expanded_branches):
            if fork_id == "alt_indicator_meta":
                continue  # Skip meta-fork
            fork_parent = fork_id.replace("alt_indicator_", "")
            if fork_parent in main_path_ids:
                root_forks.append(fork_id)
        
        sys.stderr.write(f"[RESTORE] Collapsing all {len(root_forks)} root forks after restore\n")
        
        # Close ALL root forks completely
        for fork_id in root_forks:
            sys.stderr.write(f"[RESTORE] Closing root fork {fork_id}\n")
            self._expanded_branches.discard(fork_id)
        
        sys.stderr.write(f"[RESTORE] Root forks after cleanup: {self._expanded_branches}\n")
    
    def restructure_for_restore(self, target_snapshot_id: str, new_snapshot_id: str = None) -> bool:
        """Do branch restructuring for restore WITHOUT creating a new snapshot.
        
        This is used when the datastore already created the "Restored from" snapshot.
        We just need to restructure branches (move future snapshots to alt branch, etc.)
        
        Args:
            target_snapshot_id: ID of snapshot being restored to
            new_snapshot_id: ID of newly created "Restored from" snapshot (should stay on main)
            
        Returns:
            True if successful, False if target not found
        """
        import sys
        
        target = None
        for snap in self._snapshots:
            if snap.snapshot_id == target_snapshot_id:
                target = snap
                break
        
        if not target:
            return False
        
        sys.stderr.write(f"[RESTRUCTURE] Restructuring for restore to {target_snapshot_id}\n")
        sys.stderr.write(f"[RESTRUCTURE] Engine has {len(self._snapshots)} snapshots\n")
        for s in self._snapshots:
            sys.stderr.write(f"[RESTRUCTURE]   {s.snapshot_id[:8]}: branch={s.branch_name}, desc={s.description[:30]}\n")
        
        # If restoring to non-main branch, promote it to main
        if target.branch_name != "main":
            old_main_branch = "main"
            new_main_branch = target.branch_name
            
            # Move current main to a new alternative branch
            # But preserve the newly created snapshot (new_snapshot_id) on main
            alt_branch = self._find_next_alt_branch("main")
            for s in self._snapshots:
                if s.branch_name == old_main_branch:
                    # Don't move the newly created "Restored from" snapshot
                    if new_snapshot_id and s.snapshot_id == new_snapshot_id:
                        sys.stderr.write(f"[RESTRUCTURE] Preserving new snapshot {s.snapshot_id[:8]} on main\n")
                        continue
                    s.branch_name = alt_branch
            
            # Promote target branch to main (all snapshots on that branch)
            for s in self._snapshots:
                if s.branch_name == new_main_branch:
                    s.branch_name = "main"
            
            # Update the parent of the newly created snapshot
            # It was created with parent=target (which was on alt), but now target is on main
            # So we need to update the parent to point to target's main branch ancestor
            if new_snapshot_id:
                for s in self._snapshots:
                    if s.snapshot_id == new_snapshot_id:
                        # The target is now on main, update parent to target
                        old_parent = s.parent_id
                        s.parent_id = target.snapshot_id
                        sys.stderr.write(f"[RESTRUCTURE] Updated new snapshot parent: {s.snapshot_id[:8]} parent {old_parent[:8]} -> {target.snapshot_id[:8]}\n")
                        break
            
            # Also promote all ancestors of target that lead to root
            current_id = target.parent_id
            visited = set()
            while current_id and current_id not in visited:
                visited.add(current_id)
                for s in self._snapshots:
                    if s.snapshot_id == current_id:
                        s.branch_name = "main"
                        current_id = s.parent_id
                        break
                else:
                    break
        
        # Handle future commits on main (snapshots after target)
        future_snaps = []
        # Ensure target.created_at has timezone for comparison
        target_time = target.created_at
        if target_time.tzinfo is None:
            target_time = target_time.replace(tzinfo=timezone.utc)
        
        for s in self._snapshots:
            s_time = s.created_at
            if s_time.tzinfo is None:
                s_time = s_time.replace(tzinfo=timezone.utc)
            if s.branch_name == "main" and s_time > target_time:
                future_snaps.append(s)
        
        snaps_moved_to_alt = []  # Track which snapshots were moved to alt branch
        
        # Debug: show what we found
        print(f"[ENGINE DEBUG] Target time: {target_time}", file=sys.stderr)
        print(f"[ENGINE DEBUG] All snapshots on main:", file=sys.stderr)
        for s in self._snapshots:
            if s.branch_name == "main":
                s_time = s.created_at.replace(tzinfo=timezone.utc) if s.created_at.tzinfo is None else s.created_at.astimezone(timezone.utc)
                print(f"[ENGINE DEBUG]   {s.snapshot_id[:8]}: time={s_time}, desc={s.description[:30]}", file=sys.stderr)
        print(f"[ENGINE DEBUG] Future snaps (after target): {len(future_snaps)}", file=sys.stderr)
        for s in future_snaps:
            s_time = s.created_at.replace(tzinfo=timezone.utc) if s.created_at.tzinfo is None else s.created_at.astimezone(timezone.utc)
            print(f"[ENGINE DEBUG]   {s.snapshot_id[:8]}: time={s_time}, desc={s.description[:30]}", file=sys.stderr)
        
        if future_snaps:
            # The newly created "Restored from" snapshot (new_snapshot_id) must stay on main.
            # Everything else is pre-restore work that belongs on an alternative branch.
            if new_snapshot_id:
                snaps_to_move = [s for s in future_snaps if s.snapshot_id != new_snapshot_id]
            else:
                # Fallback: when the caller cannot identify the new snapshot, keep the most
                # recent future snapshot on main and move the rest to alt.
                future_snaps.sort(key=lambda s: s.created_at.replace(tzinfo=timezone.utc) if s.created_at.tzinfo is None else s.created_at)
                snaps_to_move = future_snaps[:-1]
            if snaps_to_move:
                alt_branch = self._find_next_alt_branch("main")
                for s in snaps_to_move:
                    s.branch_name = alt_branch
                    snaps_moved_to_alt.append(s)
        
        # Restructure parent links so main branch forms a continuous spine
        self._restructure_main_branch(target, snaps_moved_to_alt)
        
        # After restore, collapse all root-level forks
        self._collapse_root_forks_after_restore(target.snapshot_id)
        
        # Update current ID to the target (the restored snapshot)
        self._current_id = target.snapshot_id
        
        self._compute_colors()
        
        # Debug: show all snapshots and their branches
        sys.stderr.write(f"[RESTRUCTURE] Final state:\n")
        for s in self._snapshots:
            sys.stderr.write(f"[RESTRUCTURE]   {s.snapshot_id[:8]}: branch={s.branch_name}, desc={s.description[:30]}\n")
        sys.stderr.write(f"[RESTRUCTURE] Complete\n")
        return True
    
    def _restructure_main_branch(self, restored_target: SnapshotInfo, snaps_moved_to_alt: list = None):
        """Rewire parent links so main branch forms continuous spine from root.
        
        After branch promotion, main branch nodes need proper parent chain
        to appear at indent 0 in the timeline.
        
        The original root (parent_id=None) is preserved as the starting point.
        Only snapshots moved to alt branch during this restore are rewired.
        """
        import sys
        snaps_moved_to_alt = snaps_moved_to_alt or []
        print(f"[ENGINE DEBUG] Restructuring main branch after restore to {restored_target.snapshot_id}", file=sys.stderr)
        
        # Get all main branch snapshots sorted by creation time
        # Normalize all times to UTC for consistent comparison
        def get_time(s):
            t = s.created_at
            if t.tzinfo is None:
                return t.replace(tzinfo=timezone.utc)
            return t.astimezone(timezone.utc)
        
        main_snaps = sorted(
            [s for s in self._snapshots if s.branch_name == "main"],
            key=get_time
        )
        
        print(f"[ENGINE DEBUG] Found {len(main_snaps)} main branch snapshots", file=sys.stderr)
        for s in main_snaps:
            print(f"[ENGINE DEBUG]  - {s.snapshot_id}: parent={s.parent_id}, desc={s.description[:30]}", file=sys.stderr)
        
        if not main_snaps:
            return
        
        # Build a map of snapshot_id -> main branch snapshot that comes before it
        main_chain_map = {}
        for i, snap in enumerate(main_snaps):
            # For each main snap, record the previous main snap as its ancestor
            if i > 0:
                main_chain_map[snap.snapshot_id] = main_snaps[i-1].snapshot_id
            else:
                main_chain_map[snap.snapshot_id] = None  # Root has no ancestor
        
        # Find the original root (parent_id=None) - it should stay as root
        root_snap = None
        for snap in main_snaps:
            if snap.parent_id is None:
                root_snap = snap
                break
        
        if root_snap is None:
            # No root found - use the first one as root
            root_snap = main_snaps[0]
            root_snap.parent_id = None
            print(f"[ENGINE DEBUG]  No root found, using {root_snap.snapshot_id[:8]} as root", file=sys.stderr)
            start_idx = 1
            prev_id = root_snap.snapshot_id
        else:
            print(f"[ENGINE DEBUG]  Preserving {root_snap.snapshot_id[:8]} as root", file=sys.stderr)
            # Find the index of root_snap to start rewiring from the next one
            start_idx = main_snaps.index(root_snap) + 1
            prev_id = root_snap.snapshot_id
        
        # Build set of main branch IDs for quick lookup
        main_ids = {s.snapshot_id for s in main_snaps}
        
        # Rewire the rest of the main chain only if needed
        # Only rewire if the current parent is not already in the main chain
        # (which would mean it's correctly positioned)
        for snap in main_snaps[start_idx:]:
            old_parent = snap.parent_id
            # Check if parent is already a valid main chain node
            if old_parent in main_ids:
                # Parent is already in main chain, keep original relationship
                print(f"[ENGINE DEBUG]  Kept main {snap.snapshot_id[:8]}: parent {old_parent[:8]} (valid main chain)", file=sys.stderr)
                prev_id = snap.snapshot_id
            else:
                # Parent not in main chain, rewire to previous main node
                snap.parent_id = prev_id
                print(f"[ENGINE DEBUG]  Rewired main {snap.snapshot_id[:8]}: parent {old_parent} -> {prev_id[:8]}", file=sys.stderr)
                prev_id = snap.snapshot_id
        
        # Rewire only the snapshots that were moved to alt branch during this restore
        # These should point to the restored target as their parent
        # BUT: if the snapshot's original parent is also being moved to the same alt branch,
        # preserve the original parent relationship to maintain color inheritance
        target_id = restored_target.snapshot_id
        moved_ids = {s.snapshot_id for s in snaps_moved_to_alt}
        for snap in snaps_moved_to_alt:
            original_parent_id = snap.parent_id
            # Check if original parent is also being moved to alt branch
            if original_parent_id in moved_ids:
                # Preserve original parent chain - both moved to same alt branch
                print(f"[ENGINE DEBUG]  Preserved parent chain for {snap.snapshot_id[:8]}: parent remains {original_parent_id[:8]}", file=sys.stderr)
            elif original_parent_id != target_id:
                # Rewire to point to restored target
                snap.parent_id = target_id
                print(f"[ENGINE DEBUG]  Rewired moved snap {snap.snapshot_id[:8]}: parent {original_parent_id} -> {target_id[:8]}", file=sys.stderr)
    
    def _find_next_alt_branch(self, base_branch: str) -> str:
        """Find next available alternative branch name."""
        existing = set(s.branch_name for s in self._snapshots)
        
        # Try base-alt first
        if f"{base_branch}-alt" not in existing:
            return f"{base_branch}-alt"
        
        # Then try numbered alternatives
        counter = 1
        while f"{base_branch}-alt-{counter}" in existing:
            counter += 1
        return f"{base_branch}-alt-{counter}"
    
    def rename_snapshot(self, snapshot_id: str, new_description: str) -> bool:
        """Rename a snapshot."""
        for snap in self._snapshots:
            if snap.snapshot_id == snapshot_id:
                snap.description = new_description
                self._compute_colors()
                return True
        return False
    
    def create_snapshot(
        self,
        description: str,
        parent_id: Optional[str] = None,
        branch_name: str = "main",
        tags: Optional[List[str]] = None
    ) -> Optional[str]:
        """Create new snapshot."""
        if parent_id is None:
            parent_id = self._current_id
        
        if parent_id is None:
            return None
        
        # Verify parent
        parent_found = any(s.snapshot_id == parent_id for s in self._snapshots)
        if not parent_found:
            return None

        new_id = str(uuid.uuid4())
        new_snap = SnapshotInfo(
            snapshot_id=new_id,
            parent_id=parent_id,
            description=description,
            branch_name=branch_name,
            created_at=datetime.now(timezone.utc),
            type=SnapshotType.MANUAL,
            tags=tags or []
        )
        
        self._snapshots.append(new_snap)
        self._current_id = new_id
        self._compute_colors()
        return new_id
    
    def update_snapshot_branch(self, snapshot_id: str, branch_name: str) -> bool:
        """Update snapshot branch in datastore."""
        self._ensure_engine()
        if not self._engine:
            return False
        
        return self._engine.update_snapshot_branch(snapshot_id, branch_name)
    
    def update_snapshot_parent(self, snapshot_id: str, new_parent_id: Optional[str]) -> bool:
        """Update snapshot parent_id and base_snapshot_id for delta snapshots.
        
        This is used during restructure operations to keep delta chains valid.
        """
        self._ensure_engine()
        if not self._engine:
            return False
        
        return self._engine.update_snapshot_parent(snapshot_id, new_parent_id)
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete snapshot and descendants."""
        target = None
        for snap in self._snapshots:
            if snap.snapshot_id == snapshot_id:
                target = snap
                break
        
        if not target:
            return False
        
        # Collect descendants
        to_delete = {snapshot_id}
        
        def collect(parent_id: str):
            for snap in self._snapshots:
                if snap.parent_id == parent_id:
                    to_delete.add(snap.snapshot_id)
                    collect(snap.snapshot_id)
        
        collect(snapshot_id)
        
        self._snapshots = [s for s in self._snapshots if s.snapshot_id not in to_delete]
        
        if self._current_id in to_delete:
            self._current_id = None
            for snap in reversed(self._snapshots):
                if snap.branch_name == "main":
                    self._current_id = snap.snapshot_id
                    break
        
        self._compute_colors()
        return True
    
    # ===================================================================
    # Branch Expansion
    # ===================================================================
    
    def toggle_branch(self, indicator_id: str) -> bool:
        """Toggle branch expansion."""
        if indicator_id in self._expanded_branches:
            self._expanded_branches.remove(indicator_id)
        else:
            self._expanded_branches.add(indicator_id)
        return True
    
    def expand_all(self) -> None:
        """Expand all branches."""
        for snap in self._snapshots:
            # Find all potential indicators (non-main branches)
            children = [s for s in self._snapshots if s.parent_id == snap.snapshot_id]
            alt_children = [c for c in children if c.branch_name != "main"]
            if alt_children:
                # Use parent-based indicator ID
                self._expanded_branches.add(f"alt_indicator_{snap.snapshot_id}")
    
    def collapse_all(self) -> None:
        """Collapse all branches."""
        self._expanded_branches.clear()
