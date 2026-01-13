from flask import Flask, render_template, request, redirect, session, url_for
from decision_engine import DecisionEngine
from utils_call_notes import generate_call_note

app = Flask(__name__)
app.secret_key = "dev-secret-key"

# Initialize the decision engine
engine = DecisionEngine(base_path="decision_trees")


# -------------------------------
# HOME ROUTE
# -------------------------------
@app.route("/")
def home():
    session.clear()
    return render_template("home.html")


# -------------------------------
# EXISTING CUSTOMER
# -------------------------------
@app.route("/existing", methods=["GET", "POST"])
def existing_customer():
    if request.method == "POST":
        # Safely get form data
        calling_number = request.form.get("calling_number")
        issue_number = request.form.get("issue_number")
        customer_name = request.form.get("customer_name")
        caller_type = request.form.get("caller_type")

        if not all([calling_number, issue_number, customer_name, caller_type]):
            return "Please fill all fields", 400

        session["calling_number"] = calling_number
        session["issue_number"] = issue_number
        session["customer_name"] = customer_name
        session["caller_type"] = caller_type
        session["history"] = []  # initialize session history

        if caller_type == "other_user":
            return redirect(url_for("dashboard_other"))
        return redirect(url_for("authenticate"))

    return render_template("existing.html")


# -------------------------------
# MODULAR AUTHENTICATION
# -------------------------------
@app.route("/authenticate", methods=["GET", "POST"])
def authenticate():
    caller_type = session.get("caller_type")
    if not caller_type:
        return redirect(url_for("existing_customer"))

    # ---------------- ACCOUNT HOLDER ----------------
    if caller_type == "account_holder":
        if request.method == "POST":
            # store all submitted auth checks
            session["auth_checks"] = request.form.to_dict(flat=True)

            # mandatory verification logic
            name_ok = "name_check" in request.form

            address_ok = (
                "address_check" in request.form or
                "addr_otac" in request.form or
                "addr_2slq" in request.form or
                "addr_5slq" in request.form or
                "addr_egain" in request.form
            )

            dob_ok = (
                "dob_check" in request.form or
                "dob_call_validate" in request.form or
                "dob_egain" in request.form
            )

            if name_ok and address_ok and dob_ok:
                return redirect(url_for("dashboard"))

            # failed name verification → must refer back office
            if not name_ok:
                session["auth_failure_reason"] = "First and Last Name verification failed"
                return redirect(url_for("auth_failure_note"))

            session["auth_failure_reason"] = "Authentication failed"
            return redirect(url_for("auth_failure_note"))

        return render_template("auth_account_holder.html")

    # ---------------- AUTHORIZED USER ----------------
    elif caller_type == "authorized_user":
        if request.method == "POST":
            result = request.form.get("verification_result")
            if result == "confirmed":
                session["authorized_verified"] = True
                return redirect(url_for("dashboard_authorized"))
            else:
                session["authorized_verified"] = False
                return redirect(url_for("access_denied"))
        return render_template("auth_authorized.html")

    # ---------------- OTHER USER ----------------
    else:
        return redirect(url_for("dashboard_other"))


# -------------------------------
# ACCESS DENIED
# -------------------------------
@app.route("/access_denied")
def access_denied():
    return render_template("access_denied.html")


# -------------------------------
# DASHBOARDS
# -------------------------------
@app.route("/dashboard")
def dashboard():
    # Account Holder Dashboard
    return render_template(
        "dashboard.html",
        calling_number=session.get("calling_number"),
        issue_number=session.get("issue_number"),
        customer_name=session.get("customer_name"),
        caller=session.get("caller_type"),
        session_history=session.get("history", [])
    )


@app.route("/dashboard_authorized")
def dashboard_authorized():
    # Authorized User Dashboard
    if not session.get("authorized_verified"):
        return redirect(url_for("access_denied"))

    return render_template(
        "dashboard.html",
        calling_number=session.get("calling_number"),
        issue_number=session.get("issue_number"),
        customer_name=session.get("customer_name"),
        caller=session.get("caller_type"),
        session_history=session.get("history", []),
        restricted=True  # hide STAC/PAC codes
    )


@app.route("/dashboard_other")
def dashboard_other():
    # Other User Dashboard (restricted)
    return render_template(
        "dashboard_other.html",
        calling_number=session.get("calling_number"),
        issue_number=session.get("issue_number"),
        customer_name=session.get("customer_name"),
        caller=session.get("caller_type"),
        session_history=session.get("history", []),
        restricted=True  # only allow payment
    )


# -------------------------------
# START FLOW
# -------------------------------
@app.route("/flow/<category>/<flow_name>")
def start_flow(category, flow_name):
    caller = session["caller_type"]
    engine.start_flow(caller, category, flow_name)
    return redirect(url_for("flow_step"))


# -------------------------------
# FLOW STEP (DO NOT MODIFY)
# -------------------------------
@app.route("/flow/step", methods=["GET", "POST"])
def flow_step():
    node = engine.current_node()

    if request.method == "POST":
        # Advance info node
        if "advance_info" in request.form:
            engine.log_history(node)
            engine.advance_info()
            return redirect(url_for("flow_step"))

        if "finish" in request.form:
            engine.log_history(node)

            caller_type = session.get("caller_type")

            if caller_type == "authorized_user":
                return redirect(url_for("dashboard_authorized"))
            elif caller_type == "other_user":
                return redirect(url_for("dashboard_other"))
            else:
                return redirect(url_for("dashboard"))

        # Choice node
        choice = request.form.get("choice")
        if choice is not None:
            choice = int(choice)
            engine.advance(choice)
            return redirect(url_for("flow_step"))

        if "flow_input" in request.form:
            value = request.form.get("flow_input")
            engine.submit_input(value)
            return redirect(url_for("flow_step"))

    # Log info nodes immediately on GET
    if node["type"] == "info":
        engine.log_history(node)

    return render_template("flow.html", node=node)


# -------------------------------
# ABORT FLOW AND RETURN TO DASHBOARD
# -------------------------------
@app.route("/flow/abort", methods=["POST"])
def abort_flow():
    # Clear flow-specific state only
    engine.flow = None
    engine.current = None

    # Do NOT touch history (no logging should happen)
    # Do NOT clear session (customer context must remain)

    caller_type = session.get("caller_type")

    if caller_type == "authorized_user":
        return redirect(url_for("dashboard_authorized"))
    elif caller_type == "other_user":
        return redirect(url_for("dashboard_other"))
    else:
        return redirect(url_for("dashboard"))


# -------------------------------
# CALL NOTE
# -------------------------------
@app.route("/call_note")
def call_note():
    note = generate_call_note(session)
    return note, 200, {"Content-Type": "text/plain"}


# -------------------------------
# AUTH FAILURE CALL NOTE (TEXT ONLY)
# -------------------------------
@app.route("/auth_failure_note")
def auth_failure_note():
    lines = []

    lines.append("TalkMobile Customer Care Call Summary")
    lines.append("------------------------------------")
    lines.append(f"Caller type: {session.get('caller_type')}")
    lines.append(f"Calling from: {session.get('calling_number')}")
    lines.append(f"Number discussed: {session.get('issue_number')}")
    lines.append(f"Customer Name: {session.get('customer_name')}")
    lines.append("")

    lines.append("Authentication:")
    lines.append("Authentication FAILED")
    lines.append(
        f"Failure Reason: {session.get('auth_failure_reason', 'Authentication failed')}"
    )
    lines.append("")

    lines.append("Outcome:")
    lines.append("Customer advised to verify details and call back.")
    lines.append("No account actions performed.")

    return "\n".join(lines), 200, {"Content-Type": "text/plain"}


# -------------------------------
# RESTART SESSION
# -------------------------------
@app.route("/restart", methods=["POST"])
def restart_session():
    session.clear()
    return redirect(url_for("home"))


# -------------------------------
# END SESSION
# -------------------------------
@app.route("/end_session")
def end_session():
    session.clear()
    return redirect(url_for("home"))


# -------------------------------
# RUN APP
# -------------------------------
if __name__ == "__main__":
    app.run(debug=True)

