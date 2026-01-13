import json
import copy
from flask import session

class DecisionEngine:
    def __init__(self, base_path="decision_trees"):
        self.base_path = base_path
        self.flow = None
        self.current = None

    def start_flow(self, caller, category, flow_name):
        path = f"{self.base_path}/{caller}/{category}/{flow_name}.json"
        with open(path, "r", encoding="utf-8") as f:
            self.flow = json.load(f)
        self.current = self.flow["start"]
        
        # Ensure context exists
        if "flow_context" not in session:
            session["flow_context"] = {}

    def _get_formatted_text(self, text):
        """Helper to replace {variables} in strings using session context."""
        if not text:
            return ""
        context = session.get("flow_context", {})
        try:
            return text.format(**context)
        except (KeyError, ValueError):
            # If a variable is missing, return text as-is to prevent crash
            return text

    def current_node(self):
        if not self.flow or self.current is None:
            return None
        
        # Deep copy to allow text formatting without altering the master flow
        node = copy.deepcopy(self.flow["nodes"][self.current])

        # Format Title and Description for display
        if "title" in node:
            node["title"] = self._get_formatted_text(node["title"])
        if "description" in node:
            node["description"] = self._get_formatted_text(node["description"])
        
        # Format Choice Labels
        if node.get("type") == "choice":
            for choice in node.get("choices", []):
                choice["label"] = self._get_formatted_text(choice["label"])

        return node

    def advance(self, choice_index):
        node = self.current_node() # This gets the formatted node
        if not node or node.get("type") != "choice":
            return

        # Log based on the choice made
        self.log_history(node, choice_index)

        # Move to next node
        # Note: We must look up the raw node to get the 'next' pointer reliably
        raw_node = self.flow["nodes"][self.current]
        next_node = raw_node["choices"][choice_index]["next"]
        self.current = next_node

    def advance_info(self):
        node = self.current_node()
        if not node or node.get("type") != "info":
            return
        
        # Determine next node
        raw_node = self.flow["nodes"][self.current]
        self.current = raw_node.get("next")

    def submit_input(self, value):
        raw_node = self.flow["nodes"][self.current]
        if not raw_node or raw_node.get("type") != "input":
            return

        # 1. Save input to session context
        variable_name = raw_node.get("variable", "generic_input")
        if "flow_context" not in session:
            session["flow_context"] = {}
        
        session["flow_context"][variable_name] = value
        session.modified = True

        # 2. Log history (pass value so it can be logged)
        self.log_history(self.current_node(), input_value=value)

        # 3. Advance
        self.current = raw_node.get("next")

    def log_history(self, node, choice_index=None, input_value=None):
        if "history" not in session:
            session["history"] = []

        # 1. Determine the main log message
        # Use the 'log' field from JSON if available, otherwise use Title
        custom_log = node.get("log")
        if custom_log:
            log_message = self._get_formatted_text(custom_log)
        else:
            log_message = node.get("title", "")

        # 2. Check if this is a TnC node to capture the full text
        # Heuristic: check if title contains "TnC" or description is long
        extended_text = None
        if "TnC" in node.get("title", "") or "Terms" in node.get("title", ""):
            extended_text = node.get("description") # Already formatted by current_node()

        entry = {
            "node": log_message,      # Now storing the 'log' variable here
            "label": None,
            "resolution": None,
            "input": input_value,
            "extended_text": extended_text # New field for full TnC
        }

        # Handle Choice Labels
        if node.get("type") == "choice" and choice_index is not None:
            # We don't necessarily need the label if we have a custom log, 
            # but we keep it for context if the log doesn't cover it.
            entry["label"] = node["choices"][choice_index]["label"]

        elif node.get("type") in ["info", "resolution"]:
            entry["resolution"] = log_message

        history = session["history"]
        history.append(entry)
        session["history"] = history
