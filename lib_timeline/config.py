"""Timeline configuration - debug and permission settings.

This module provides configuration for the timeline panel,
including debug modes that bypass permission checks.
"""

from __future__ import annotations

from typing import Callable, Optional
from PySide6 import QtWidgets, QtCore


class TimelineConfig:
    """Configuration singleton for timeline behavior.
    
    Attributes:
        DEBUG_ANYTHING_GOES: If True, bypasses all permission checks
        DEBUG_PRINT_PERMISSIONS: If True, prints permission requests to console
    """
    
    DEBUG_ANYTHING_GOES: bool = False
    DEBUG_PRINT_PERMISSIONS: bool = True
    
    @classmethod
    def set_debug_mode(cls, enabled: bool = True):
        """Enable/disable debug anything-goes mode.
        
        When enabled, all operations are auto-approved without asking TWS.
        """
        cls.DEBUG_ANYTHING_GOES = enabled
        print(f"[TimelineConfig] DEBUG_ANYTHING_GOES = {enabled}")


def create_permission_handler(
    operation: str,
    parent_widget: Optional[QtWidgets.QWidget] = None
) -> Callable[[str, Callable[[bool], None]], None]:
    """Create a permission handler that respects DEBUG_ANYTHING_GOES.
    
    Usage:
        panel.checkpoint_permission_requested.connect(
            create_permission_handler("checkpoint", panel)
        )
    
    Args:
        operation: Name of the operation (checkpoint, restore, new_session)
        parent_widget: Parent widget for confirmation dialogs
        
    Returns:
        Handler function suitable for connecting to permission signals
    """
    def handler(data: str, callback: Callable[[bool], None]):
        """Handle permission request."""
        
        if TimelineConfig.DEBUG_PRINT_PERMISSIONS:
            print(f"[TimelinePermission] {operation} requested: {data}")
        
        # DEBUG MODE: Auto-approve everything
        if TimelineConfig.DEBUG_ANYTHING_GOES:
            if TimelineConfig.DEBUG_PRINT_PERMISSIONS:
                print(f"[TimelinePermission] {operation} AUTO-APPROVED (DEBUG_ANYTHING_GOES)")
            callback(True)
            return
        
        # NORMAL MODE: Ask for confirmation
        if parent_widget is None:
            # No parent widget - auto-deny for safety
            print(f"[TimelinePermission] {operation} DENIED (no parent widget)")
            callback(False)
            return
        
        # Show confirmation dialog
        msg = QtWidgets.QMessageBox(parent_widget)
        msg.setWindowTitle(f"Confirm {operation.title()}")
        msg.setText(f"Allow {operation}?\n\n{data}")
        msg.setStandardButtons(
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        msg.setDefaultButton(QtWidgets.QMessageBox.No)
        
        reply = msg.exec()
        approved = reply == QtWidgets.QMessageBox.Yes
        
        if TimelineConfig.DEBUG_PRINT_PERMISSIONS:
            status = "APPROVED" if approved else "DENIED"
            print(f"[TimelinePermission] {operation} {status} by user")
        
        callback(approved)
    
    return handler


def create_new_session_handler(
    parent_widget: Optional[QtWidgets.QWidget] = None
) -> Callable[[Callable[[bool], None]], None]:
    """Create a permission handler for new session requests.
    
    Usage:
        panel.new_session_permission_requested.connect(
            create_new_session_handler(panel)
        )
    """
    def handler(callback: Callable[[bool], None]):
        """Handle new session permission request."""
        
        if TimelineConfig.DEBUG_PRINT_PERMISSIONS:
            print(f"[TimelinePermission] new_session requested")
        
        # DEBUG MODE: Auto-approve
        if TimelineConfig.DEBUG_ANYTHING_GOES:
            if TimelineConfig.DEBUG_PRINT_PERMISSIONS:
                print(f"[TimelinePermission] new_session AUTO-APPROVED (DEBUG_ANYTHING_GOES)")
            callback(True)
            return
        
        # NORMAL MODE: Ask for confirmation
        if parent_widget is None:
            print(f"[TimelinePermission] new_session DENIED (no parent widget)")
            callback(False)
            return
        
        msg = QtWidgets.QMessageBox(parent_widget)
        msg.setWindowTitle("Confirm New Session")
        msg.setText("Start a new session?\n\nAll current snapshots will be cleared.")
        msg.setStandardButtons(
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        msg.setDefaultButton(QtWidgets.QMessageBox.No)
        
        reply = msg.exec()
        approved = reply == QtWidgets.QMessageBox.Yes
        
        if TimelineConfig.DEBUG_PRINT_PERMISSIONS:
            status = "APPROVED" if approved else "DENIED"
            print(f"[TimelinePermission] new_session {status} by user")
        
        callback(approved)
    
    return handler


def install_debug_handlers(panel: QtWidgets.QWidget, parent: Optional[QtWidgets.QWidget] = None):
    """Install permission handlers with DEBUG_ANYTHING_GOES support.
    
    This is a convenience function to quickly set up the permission system
    with debug mode support.
    
    Usage in panel.py __main__:
        from lib_timeline.config import install_debug_handlers, TimelineConfig
        TimelineConfig.DEBUG_ANYTHING_GOES = True  # Enable debug mode
        install_debug_handlers(manager.get_panel(), window)
    
    Args:
        panel: The TimelinePanel instance
        parent: Parent widget for confirmation dialogs
    """
    # Check for required signals (duck typing - works with __main__.TimelinePanel)
    required_signals = [
        'checkpoint_permission_requested',
        'restore_permission_requested', 
        'new_session_permission_requested'
    ]
    for sig in required_signals:
        if not hasattr(panel, sig):
            raise TypeError(f"Panel missing required signal: {sig}")
    
    panel.checkpoint_permission_requested.connect(
        create_permission_handler("checkpoint", parent)
    )
    panel.restore_permission_requested.connect(
        create_permission_handler("restore", parent)
    )
    panel.new_session_permission_requested.connect(
        create_new_session_handler(parent)
    )
    
    mode = "DEBUG_ANYTHING_GOES" if TimelineConfig.DEBUG_ANYTHING_GOES else "NORMAL"
    print(f"[TimelineConfig] Permission handlers installed ({mode} mode)")
