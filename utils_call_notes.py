def generate_call_note(session):
    lines = []

    lines.append("TalkMobile Customer Care Call Summary")
    lines.append("------------------------------------")
    lines.append(f"Caller type: {session.get('caller_type')}")
    lines.append(f"Calling from: {session.get('calling_number')}")
    lines.append(f"Number discussed: {session.get('issue_number')}")
    lines.append(f"Customer Name: {session.get('customer_name')}")
    lines.append("")

    # ---------------- AUTHENTICATION ----------------
    lines.append("Authentication:")
    
    auth_checks = session.get("auth_checks", [])
    if auth_checks:
        for check in auth_checks:
            lines.append(f"- {check.replace('_', ' ').title()}: Passed")
    else:
        lines.append("- Not completed")

    failure_reason = session.get("auth_failure_reason")
    if failure_reason:
        lines.append("")
        lines.append("Authentication Failure Reason:")
        lines.append(f"- {failure_reason}")

    # ---------------- ACTIONS ----------------
    lines.append("")
    lines.append("Actions & Flow History:")

    for h in session.get("history", []):
        # 'node' now contains the formatted 'log' string from JSON if it existed
        log_message = h.get("node")
        label = h.get("label")
        inp = h.get("input")
        extended_text = h.get("extended_text")

        # Formatting logic
        if inp:
            # Input nodes: "30 Day Plan Price: 12"
            lines.append(f"- {log_message}: {inp}")
        elif label:
             # Choice nodes: "Checked contract eligibility: Yes"
            lines.append(f"- {log_message}: {label}")
        else:
            # Info/Resolution nodes
            lines.append(f"- {log_message}")

        # If we captured full TnC text, add it as a block
        if extended_text:
            lines.append("  [AGREEMENT SCRIPT READ]:")
            lines.append(f"  \"{extended_text}\"")

    lines.append("")
    lines.append("Call completed.")

    return "\n".join(lines)
