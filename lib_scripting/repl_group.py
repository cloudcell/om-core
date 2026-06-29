"""REPL Group Operations - Create, add, detach, delete, rename, list groups.

Commands for managing outline groups via the public command spine.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib_repl.repl_core import OpenMREPLCore


class REPLGroupMixin:
    """Mixin for group / outline operations."""

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    def _resolve_group_node_id(self: "OpenMREPLCore", dim_id: str, label_or_id: str) -> str | None:
        """Resolve a group label or id to a group node id within the dimension."""
        data = self.session.query("dimension_detail", dim_id=dim_id)
        if not data:
            return None
        outline = data.get("outline", [])
        return self._find_group_node_id_in_outline(outline, label_or_id)

    def _find_group_node_id_in_outline(self, nodes: list[dict], label_or_id: str) -> str | None:
        for node in nodes:
            if node.get("node_id") == label_or_id:
                return label_or_id
            if node.get("label") == label_or_id:
                return node.get("node_id")
            child_match = self._find_group_node_id_in_outline(
                node.get("children", []), label_or_id
            )
            if child_match:
                return child_match
        return None

    def _resolve_dimension_item_ids(
        self: "OpenMREPLCore", dim_id: str, labels: list[str]
    ) -> list[str]:
        """Resolve a list of item labels to stable item IDs."""
        if not labels:
            return []
        data = self.session.query("dimension_detail", dim_id=dim_id)
        if not data:
            raise ValueError("Could not read dimension details")
        items = data.get("items", [])
        item_map = {it["name"]: it["id"] for it in items}
        resolved = []
        for label in labels:
            if label in item_map:
                resolved.append(item_map[label])
                continue
            # Accept direct IDs as well
            if any(it["id"] == label for it in items):
                resolved.append(label)
                continue
            raise ValueError(f"Item not found in dimension: {label!r}")
        return resolved

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    def do_group(self: "OpenMREPLCore", arg: str) -> None:
        """
        Group / outline operations.

        Usage:
          group create <dim> <label> [parent=<group>] [item1 item2 ...]
          group add <dim> <group> <item1 item2 ...>
          group detach <dim> <item1 item2 ...>
          group delete <dim> <group>
          group rename <dim> <group> <new_label>
          group list <dim>
        """
        if not arg.strip():
            self._print_group_usage()
            return
        try:
            parts = shlex.split(arg)
        except ValueError as e:
            print(f"Error parsing arguments: {e}")
            return
        if not parts:
            self._print_group_usage()
            return
        sub = parts[0].lower()
        rest = parts[1:]
        if sub == "create":
            return self._do_group_create(rest)
        if sub == "add":
            return self._do_group_add(rest)
        if sub == "detach":
            return self._do_group_detach(rest)
        if sub == "delete":
            return self._do_group_delete(rest)
        if sub == "rename":
            return self._do_group_rename(rest)
        if sub == "list":
            return self._do_group_list(rest)
        print(f"Unknown group sub-command: {sub}")
        self._print_group_usage()

    def _print_group_usage(self: "OpenMREPLCore") -> None:
        print("Usage: group create|add|detach|delete|rename|list ...")

    def _do_group_create(self: "OpenMREPLCore", parts: list[str]) -> None:
        if len(parts) < 2:
            print("Usage: group create <dim> <label> [parent=<group>] [item1 item2 ...]")
            return
        dim_name = parts[0]
        label = parts[1]
        dim_id, _ = self._resolve_dimension_id(dim_name)
        if not dim_id:
            print(f"Error: Dimension '{dim_name}' not found")
            return
        parent_group_id: str | None = None
        item_labels: list[str] = []
        for token in parts[2:]:
            if token.startswith("parent="):
                parent_ref = token.split("=", 1)[1]
                parent_group_id = self._resolve_group_node_id(dim_id, parent_ref)
                if parent_group_id is None:
                    print(f"Error: Parent group '{parent_ref}' not found")
                    return
            else:
                item_labels.append(token)
        try:
            child_item_ids = (
                self._resolve_dimension_item_ids(dim_id, item_labels) if item_labels else None
            )
        except ValueError as e:
            print(f"Error: {e}")
            return
        result = self.session.execute(
            "create_group",
            dim_id=dim_id,
            label=label,
            parent_group_id=parent_group_id,
            child_item_ids=child_item_ids,
        )
        if result.success:
            print(f"Created group '{label}'")
        else:
            print(f"Error creating group: {result.error}")

    def _do_group_add(self: "OpenMREPLCore", parts: list[str]) -> None:
        if len(parts) < 3:
            print("Usage: group add <dim> <group> <item1 item2 ...>")
            return
        dim_name = parts[0]
        group_ref = parts[1]
        item_labels = parts[2:]
        dim_id, _ = self._resolve_dimension_id(dim_name)
        if not dim_id:
            print(f"Error: Dimension '{dim_name}' not found")
            return
        group_node_id = self._resolve_group_node_id(dim_id, group_ref)
        if not group_node_id:
            print(f"Error: Group '{group_ref}' not found")
            return
        try:
            item_ids = self._resolve_dimension_item_ids(dim_id, item_labels)
        except ValueError as e:
            print(f"Error: {e}")
            return
        result = self.session.execute(
            "move_items_to_group",
            dim_id=dim_id,
            item_ids=item_ids,
            group_node_id=group_node_id,
        )
        if result.success:
            print(f"Added {len(item_ids)} item(s) to group '{group_ref}'")
        else:
            print(f"Error adding items to group: {result.error}")

    def _do_group_detach(self: "OpenMREPLCore", parts: list[str]) -> None:
        if len(parts) < 2:
            print("Usage: group detach <dim> <item1 item2 ...>")
            return
        dim_name = parts[0]
        item_labels = parts[1:]
        dim_id, _ = self._resolve_dimension_id(dim_name)
        if not dim_id:
            print(f"Error: Dimension '{dim_name}' not found")
            return
        try:
            item_ids = self._resolve_dimension_item_ids(dim_id, item_labels)
        except ValueError as e:
            print(f"Error: {e}")
            return
        result = self.session.execute("ungroup_items", dim_id=dim_id, item_ids=item_ids)
        if result.success:
            print(f"Detached {len(item_ids)} item(s) from their parent group")
        else:
            print(f"Error detaching items: {result.error}")

    def _do_group_delete(self: "OpenMREPLCore", parts: list[str]) -> None:
        if len(parts) < 2:
            print("Usage: group delete <dim> <group>")
            return
        dim_name = parts[0]
        group_ref = parts[1]
        dim_id, _ = self._resolve_dimension_id(dim_name)
        if not dim_id:
            print(f"Error: Dimension '{dim_name}' not found")
            return
        group_node_id = self._resolve_group_node_id(dim_id, group_ref)
        if not group_node_id:
            print(f"Error: Group '{group_ref}' not found")
            return
        result = self.session.execute(
            "delete_group", dim_id=dim_id, group_node_id=group_node_id, cascade=True
        )
        if result.success:
            print(f"Deleted group '{group_ref}'")
        else:
            print(f"Error deleting group: {result.error}")

    def _do_group_rename(self: "OpenMREPLCore", parts: list[str]) -> None:
        if len(parts) < 3:
            print("Usage: group rename <dim> <group> <new_label>")
            return
        dim_name = parts[0]
        group_ref = parts[1]
        new_label = parts[2]
        dim_id, _ = self._resolve_dimension_id(dim_name)
        if not dim_id:
            print(f"Error: Dimension '{dim_name}' not found")
            return
        group_node_id = self._resolve_group_node_id(dim_id, group_ref)
        if not group_node_id:
            print(f"Error: Group '{group_ref}' not found")
            return
        result = self.session.execute(
            "rename_group_node",
            dim_id=dim_id,
            node_id=group_node_id,
            new_label=new_label,
        )
        if result.success:
            print(f"Renamed group '{group_ref}' to '{new_label}'")
        else:
            print(f"Error renaming group: {result.error}")

    def _do_group_list(self: "OpenMREPLCore", parts: list[str]) -> None:
        if len(parts) < 1:
            print("Usage: group list <dim>")
            return
        dim_name = parts[0]
        dim_id, _ = self._resolve_dimension_id(dim_name)
        if not dim_id:
            print(f"Error: Dimension '{dim_name}' not found")
            return
        data = self.session.query("dimension_detail", dim_id=dim_id)
        if not data:
            print(f"Error: Could not read dimension '{dim_name}'")
            return
        outline = data.get("outline", [])
        if not outline:
            print(f"Dimension '{dim_name}' has no outline")
            return
        print(f"Groups for '{dim_name}':")
        self._print_outline(outline, indent=2)

    def _print_outline(self, nodes: list[dict], indent: int = 0) -> None:
        for node in nodes:
            label = node.get("label", "")
            print(" " * indent + label)
            self._print_outline(node.get("children", []), indent + 2)

    # ------------------------------------------------------------------
    # Tab completion
    # ------------------------------------------------------------------

    def complete_group(
        self: "OpenMREPLCore", text: str, line: str, begidx: int, endidx: int
    ) -> list[str]:
        """Tab completion for the group command."""
        subcommands = ["create", "add", "detach", "delete", "rename", "list"]
        tokens = line.split()

        # Still completing the subcommand itself?
        if len(tokens) <= 1 or (len(tokens) == 2 and not line.endswith(" ")):
            return [s for s in subcommands if s.startswith(text)]

        sub = tokens[1].lower()
        if line.endswith(" "):
            # Starting a new argument: count fully-typed args after the subcommand
            arg_idx = len(tokens) - 2
        else:
            # Completing the partially-typed last argument
            arg_idx = len(tokens) - 3

        if sub == "list":
            return self._complete_dimension_names(text)
        if arg_idx == 0:
            return self._complete_dimension_names(text)

        dim_name = tokens[2] if len(tokens) > 2 else ""
        if not dim_name:
            return []
        if sub == "create":
            if text.startswith("parent="):
                return self._complete_parent_prefix(text, dim_name)
            return []
        if sub == "add":
            if arg_idx == 1:
                return self._complete_group_names(text, dim_name)
            return self._complete_item_names(text, dim_name)
        if sub == "detach":
            return self._complete_item_names(text, dim_name)
        if sub == "delete":
            return self._complete_group_names(text, dim_name)
        if sub == "rename":
            if arg_idx == 1:
                return self._complete_group_names(text, dim_name)
            return []
        return []

    def _complete_dimension_names(self: "OpenMREPLCore", text: str) -> list[str]:
        data = self.session.query("dimension_list")
        if not data:
            return []
        names = [d.get("name", "") for d in data.get("dimensions", []) if d.get("name")]
        return [n for n in names if n.startswith(text)]

    def _complete_group_names(self: "OpenMREPLCore", text: str, dim_name: str) -> list[str]:
        dim_id, _ = self._resolve_dimension_id(dim_name)
        if not dim_id:
            return []
        data = self.session.query("dimension_detail", dim_id=dim_id)
        if not data:
            return []
        labels = self._collect_group_labels(data.get("outline", []))
        return [n for n in labels if n.startswith(text)]

    def _collect_group_labels(self, nodes: list[dict]) -> list[str]:
        labels = []
        for node in nodes:
            if node.get("label"):
                labels.append(node["label"])
            labels.extend(self._collect_group_labels(node.get("children", [])))
        return labels

    def _complete_item_names(self: "OpenMREPLCore", text: str, dim_name: str) -> list[str]:
        dim_id, _ = self._resolve_dimension_id(dim_name)
        if not dim_id:
            return []
        data = self.session.query("dimension_detail", dim_id=dim_id)
        if not data:
            return []
        names = [it.get("name", "") for it in data.get("items", []) if it.get("name")]
        return [n for n in names if n.startswith(text)]

    def _complete_parent_prefix(self: "OpenMREPLCore", text: str, dim_name: str) -> list[str]:
        prefix = "parent="
        group_ref = text[len(prefix) :] if text.startswith(prefix) else ""
        groups = self._complete_group_names(group_ref, dim_name)
        return [prefix + g for g in groups]

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    def help_group(self: "OpenMREPLCore") -> None:
        print("\nGroup / outline operations")
        print("  group create <dim> <label> [parent=<group>] [item1 item2 ...]")
        print("  group add <dim> <group> <item1 item2 ...>")
        print("  group detach <dim> <item1 item2 ...>")
        print("  group delete <dim> <group>")
        print("  group rename <dim> <group> <new_label>")
        print("  group list <dim>")
