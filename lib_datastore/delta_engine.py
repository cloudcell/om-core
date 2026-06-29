"""Delta engine for incremental snapshot storage.

Computes and applies diffs between workspace states to minimize storage.
"""

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple


def _compute_checksum(obj: Any) -> str:
    """Compute MD5 checksum of a JSON-serializable object.
    
    Uses canonical JSON representation (sorted keys) for consistency.
    Uses default=str to match datastore serialization behavior.
    """
    json_str = json.dumps(obj, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.md5(json_str.encode('utf-8')).hexdigest()


def compute_delta(old_payload: Dict[str, Any], new_payload: Dict[str, Any], 
                  compute_checksums: bool = True) -> tuple[Dict[str, Any], Optional[str], Optional[str]]:
    """Compute delta (difference) between two payloads.
    
    Returns a tuple of (delta_dict, delta_checksum, payload_checksum):
    - delta_dict: Dict describing changes:
      - "_full": bool - if True, this is a full payload (no base)
      - "_base": str - snapshot_id of base payload (for delta chains)
      - "set": Dict - key-path -> new value for additions/modifications
      - "delete": List - key-paths of deleted items
      - "unchanged": bool - True if payloads are identical
    - delta_checksum: MD5 checksum of delta content (for corruption detection)
    - payload_checksum: MD5 checksum of expected reconstructed payload
    
    Key paths use dot notation: "workspace.cubes.cube1.data.A|B"
    """
    delta = {
        "_full": False,
        "set": {},
        "delete": [],
        "unchanged": False,
    }
    delta_checksum = None
    payload_checksum = None
    
    # Check for identical payloads
    if _deep_equal(old_payload, new_payload):
        delta["unchanged"] = True
        if compute_checksums:
            payload_checksum = _compute_checksum(old_payload)
            # Simulate JSON round-trip then compute checksum on result
            delta_json = json.dumps(delta, default=str, sort_keys=True, separators=(',', ':'))
            delta_after_roundtrip = json.loads(delta_json)
            delta_checksum = _compute_checksum(delta_after_roundtrip)
        return delta, delta_checksum, payload_checksum

    # Compute recursive diff
    _compute_diff_recursive(old_payload, new_payload, "", delta["set"], delta["delete"])

    # Compute checksums if enabled
    if compute_checksums:
        # Simulate JSON round-trip for storage consistency
        # This ensures checksums match what will be stored/loaded
        new_payload_json = json.dumps(new_payload, default=str, sort_keys=True, separators=(',', ':'))
        new_payload_roundtrip = json.loads(new_payload_json)
        payload_checksum = _compute_checksum(new_payload_roundtrip)
        
        delta_json = json.dumps(delta, default=str, sort_keys=True, separators=(',', ':'))
        delta_after_roundtrip = json.loads(delta_json)
        # Compute checksum on the round-tripped delta
        delta_checksum = _compute_checksum(delta_after_roundtrip)
    
    return delta, delta_checksum, payload_checksum


class DeltaChecksumError(Exception):
    """Raised when delta checksum verification fails."""
    pass


class PayloadChecksumError(Exception):
    """Raised when reconstructed payload checksum verification fails."""
    pass


def verify_delta(delta: Dict[str, Any], stored_checksum: Optional[str] = None) -> bool:
    """Verify delta integrity by checking its checksum.

    Args:
        delta: Delta dict to verify (already JSON round-tripped from storage)
        stored_checksum: The expected checksum (from DB), or None to skip verification

    Returns:
        True if checksum is valid or not present

    Raises:
        DeltaChecksumError: If checksum verification fails
    """
    # With new format, checksum is passed separately (from DB), not embedded in delta
    # The delta here is the raw content
    if stored_checksum is None:
        return True

    # Compute checksum on the raw delta content
    computed = _compute_checksum(delta)
    if computed != stored_checksum:
        raise DeltaChecksumError(
            f"Delta checksum mismatch: expected {stored_checksum}, got {computed}"
        )
    return True


def verify_payload(payload: Dict[str, Any], expected_checksum: str) -> bool:
    """Verify payload integrity by checking its checksum.
    
    Args:
        payload: Payload to verify
        expected_checksum: Expected checksum value
        
    Returns:
        True if checksum is valid
        
    Raises:
        PayloadChecksumError: If checksum verification fails
    """
    if expected_checksum is None:
        return True
    
    # JSON round-trip to ensure consistent checksum computation
    payload_json = json.dumps(payload, default=str, sort_keys=True, separators=(',', ':'))
    payload_roundtrip = json.loads(payload_json)
    computed = _compute_checksum(payload_roundtrip)
    if computed != expected_checksum:
        raise PayloadChecksumError(
            f"Payload checksum mismatch: expected {expected_checksum}, got {computed}"
        )
    return True


def apply_delta(base_payload: Dict[str, Any], delta: Dict[str, Any], 
                verify: bool = True, delta_checksum: Optional[str] = None) -> Dict[str, Any]:
    """Apply delta to base payload to reconstruct new payload.
    
    Args:
        base_payload: The original full payload
        delta: Delta dict from compute_delta()
        verify: If True, verify delta and payload checksums
        delta_checksum: Expected checksum of delta content (from DB), for verification
        
    Returns:
        Reconstructed payload
        
    Raises:
        DeltaChecksumError: If delta checksum verification fails
        PayloadChecksumError: If reconstructed payload checksum fails
    """
    # Strip _target_checksum before delta verification (it was added after checksum was computed)
    delta_for_verify = {k: v for k, v in delta.items() if k != "_target_checksum"}
    
    if verify:
        verify_delta(delta_for_verify, delta_checksum)
    
    if delta.get("_full"):
        # This delta contains the full payload
        payload = delta.get("payload", {})
        if verify:
            expected = delta.get("_target_checksum")
            if expected:
                verify_payload(payload, expected)
        return payload
    
    if delta.get("unchanged"):
        result = deepcopy(base_payload)
        if verify:
            expected = delta.get("_target_checksum")
            if expected:
                verify_payload(result, expected)
        return result
    
    # Start with deep copy of base
    result = deepcopy(base_payload)
    
    # Apply deletions
    for path in delta.get("delete", []):
        _delete_at_path(result, path)
    
    # Apply modifications/additions
    for path, value in delta.get("set", {}).items():
        _set_at_path(result, path, value)
    
    # JSON round-trip to ensure consistent structure
    result_json = json.dumps(result, default=str, sort_keys=True, separators=(',', ':'))
    result = json.loads(result_json)
    
    # Verify reconstructed payload checksum
    if verify:
        expected = delta.get("_target_checksum")
        if expected:
            verify_payload(result, expected)
    
    return result


def _compute_diff_recursive(
    old: Any,
    new: Any,
    path: str,
    set_dict: Dict[str, Any],
    delete_list: List[str]
) -> None:
    """Recursively compute differences between two values.
    
    Populates set_dict and delete_list with changes.
    """
    # Type mismatch or primitive value change
    if type(old) != type(new) or not isinstance(old, (dict, list)):
        if old != new:
            set_dict[path] = deepcopy(new)
        return
    
    # Both are dicts
    if isinstance(old, dict):
        old_keys = set(old.keys())
        new_keys = set(new.keys())
        
        # Deleted keys
        for key in old_keys - new_keys:
            delete_list.append(f"{path}.{key}" if path else key)
        
        # New or modified keys
        for key in new_keys:
            old_val = old.get(key)
            new_val = new[key]
            new_path = f"{path}.{key}" if path else key
            
            if key not in old_keys:
                # New key - set entire value
                set_dict[new_path] = deepcopy(new_val)
            elif not _deep_equal(old_val, new_val):
                # Modified - recurse
                _compute_diff_recursive(old_val, new_val, new_path, set_dict, delete_list)
        
        return
    
    # Both are lists
    if isinstance(old, list):
        # For lists, we do element-by-element comparison for small lists
        # or full replacement for large lists
        if len(old) != len(new) or len(old) > 100:
            # Full replacement for size changes or large lists
            set_dict[path] = deepcopy(new)
            return
        
        # Element-wise comparison for small lists
        changed = False
        for i, (old_item, new_item) in enumerate(zip(old, new)):
            item_path = f"{path}[{i}]"
            if not _deep_equal(old_item, new_item):
                _compute_diff_recursive(old_item, new_item, item_path, set_dict, delete_list)
                changed = True
        
        # If list items were added/removed (size check above handles main cases)
        if not changed and len(new) > len(old):
            for i in range(len(old), len(new)):
                set_dict[f"{path}[{i}]"] = deepcopy(new[i])
        
        return


def _deep_equal(a: Any, b: Any) -> bool:
    """Deep equality check for two values."""
    if type(a) != type(b):
        return False
    
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_deep_equal(a[k], b[k]) for k in a.keys())
    
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(_deep_equal(x, y) for x, y in zip(a, b))
    
    return a == b


def _get_at_path(obj: Any, path: str) -> Any:
    """Get value at a dot-notation path."""
    parts = _parse_path(path)
    for part in parts:
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list):
            if isinstance(part, int) and 0 <= part < len(obj):
                obj = obj[part]
            else:
                return None
        else:
            return None
        if obj is None:
            return None
    return obj


def _set_at_path(obj: Any, path: str, value: Any) -> None:
    """Set value at a dot-notation path, creating intermediates as needed."""
    parts = _parse_path(path)
    
    # Navigate to parent of target
    for part in parts[:-1]:
        if isinstance(obj, dict):
            if part not in obj or not isinstance(obj[part], (dict, list)):
                # Create intermediate - guess type from next part
                next_part = parts[parts.index(part) + 1]
                obj[part] = {} if not isinstance(next_part, int) else []
            obj = obj[part]
        elif isinstance(obj, list):
            if isinstance(part, int) and part < len(obj):
                if not isinstance(obj[part], (dict, list)):
                    next_part = parts[parts.index(part) + 1]
                    obj[part] = {} if not isinstance(next_part, int) else []
                obj = obj[part]
            else:
                return  # Cannot set, path invalid
    
    # Set final value
    if parts:
        target = parts[-1]
        if isinstance(obj, dict):
            obj[target] = value
        elif isinstance(obj, list) and isinstance(target, int):
            if target < len(obj):
                obj[target] = value
            else:
                # Extend list if needed
                while len(obj) <= target:
                    obj.append(None)
                obj[target] = value


def _delete_at_path(obj: Any, path: str) -> None:
    """Delete value at a dot-notation path."""
    parts = _parse_path(path)
    
    # Navigate to parent
    for part in parts[:-1]:
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list):
            if isinstance(part, int) and part < len(obj):
                obj = obj[part]
            else:
                return
        else:
            return
        if obj is None:
            return
    
    # Delete final key
    if parts:
        target = parts[-1]
        if isinstance(obj, dict) and target in obj:
            del obj[target]
        elif isinstance(obj, list) and isinstance(target, int) and target < len(obj):
            del obj[target]


def _parse_path(path: str) -> List[Any]:
    """Parse a dot-notation path into parts.
    
    Handles array indices: "workspace.cubes[0].name" -> ["workspace", "cubes", 0, "name"]
    """
    if not path:
        return []
    
    parts = []
    current = ""
    i = 0
    while i < len(path):
        char = path[i]
        if char == "." and current:
            parts.append(current)
            current = ""
        elif char == "[":
            if current:
                parts.append(current)
                current = ""
            # Parse index
            i += 1
            idx_str = ""
            while i < len(path) and path[i] != "]":
                idx_str += path[i]
                i += 1
            if idx_str.isdigit():
                parts.append(int(idx_str))
        elif char == "]":
            pass  # Skip closing bracket
        elif char == ".":
            # Skip dots that come after brackets or at start
            pass
        else:
            current += char
        i += 1
    
    if current:
        parts.append(current)
    
    return parts


class DeltaChain:
    """Manages a chain of delta snapshots for efficient storage."""
    
    def __init__(self, max_chain_length: int = 50):
        self.max_chain_length = max_chain_length
        self.base_snapshot_id: Optional[str] = None
        self.base_payload: Optional[Dict] = None
        self.deltas: List[Tuple[str, Dict]] = []  # [(snapshot_id, delta), ...]
        self._current_payload: Optional[Dict] = None
    
    def set_base(self, snapshot_id: str, payload: Dict[str, Any]) -> None:
        """Set the base full snapshot."""
        self.base_snapshot_id = snapshot_id
        self.base_payload = deepcopy(payload)
        self.deltas = []
        self._current_payload = deepcopy(payload)
    
    def add_delta(self, snapshot_id: str, new_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new snapshot as delta from current state.
        
        Returns the delta dict for storage (without embedded checksums).
        Checksums are stored separately in the DB.
        """
        if self._current_payload is None:
            # First delta - need full payload
            delta = {
                "_full": True,
                "payload": deepcopy(new_payload),
            }
            self._current_payload = deepcopy(new_payload)
            self.deltas.append((snapshot_id, delta, None, None))
            return delta
        
        # Compute actual delta
        delta, delta_checksum, payload_checksum = compute_delta(self._current_payload, new_payload)
        # Note: _base is stored in DB column, not in delta JSON
        # The caller is responsible for setting base_snapshot_id
        
        # Store delta with checksums for internal tracking
        self.deltas.append((snapshot_id, delta, delta_checksum, payload_checksum))
        self._current_payload = deepcopy(new_payload)
        
        # Check if we need to start a new chain (0 = no max)
        if self.max_chain_length > 0 and len(self.deltas) >= self.max_chain_length:
            # Force new base on next addition
            self.base_snapshot_id = None
        
        return delta
    
    def get_last_checksums(self) -> tuple[Optional[str], Optional[str]]:
        """Get the delta_checksum and payload_checksum for the last added delta.
        
        Returns:
            Tuple of (delta_checksum, payload_checksum)
        """
        if not self.deltas:
            return None, None
        _, _, delta_checksum, payload_checksum = self.deltas[-1]
        return delta_checksum, payload_checksum
    
    def reconstruct(self, up_to_index: int = -1) -> Dict[str, Any]:
        """Reconstruct payload up to given delta index.
        
        Args:
            up_to_index: Index in deltas list (-1 for all)
            
        Returns:
            Reconstructed payload
        """
        if self.base_payload is None:
            raise ValueError("No base payload set")
        
        if up_to_index < 0:
            up_to_index = len(self.deltas) - 1
        
        result = deepcopy(self.base_payload)
        
        for i in range(up_to_index + 1):
            _, delta, _, _ = self.deltas[i]
            if delta.get("_full"):
                result = deepcopy(delta["payload"])
            elif not delta.get("unchanged"):
                result = apply_delta(result, delta)
        
        return result
    
    def needs_new_base(self) -> bool:
        """Check if chain is full and needs a new base snapshot."""
        if self.base_snapshot_id is None:
            return True
        # 0 = no max chain length (disabled)
        if self.max_chain_length > 0 and len(self.deltas) >= self.max_chain_length:
            return True
        return False
