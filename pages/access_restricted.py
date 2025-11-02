"""Access restricted page for budget issues (exceeded or not set).

Accessible when a user's department monthly cost exceeds allocated budget or no budget is set.
Allows selecting a department and updating its budget.
"""

import mesop as me  # type: ignore
from components.dialog import dialog, dialog_actions  # use shared dialog component

from components.header import header
from components.page_scaffold import page_frame, page_scaffold
from config.default import Default
from models import budget as budget_service
from state.state import AppState

@me.stateclass
class PageState:
    selected_department: str | None = None
    new_budget_input: str = ""
    info_message: str = ""
    error_dialog_open: bool = False
    error_message: str = ""
    current_budget: float | None = None
    current_cost: float | None = None
    edit_dialog_open: bool = False

def on_click_update_budget(e: me.ClickEvent):  # pylint: disable=unused-argument
    st = me.state(PageState)
    app = me.state(AppState)
    try:
        if not st.selected_department:
            st.error_message = "Please choose a department."
            st.error_dialog_open = True
            yield
            return
        amount = float(st.new_budget_input)
        if amount <= 0:
            raise ValueError("Budget must be greater than 0")
        budget_service.set_department_budget(st.selected_department, amount)
        # Re-check budget for the current user; if within budget, go home
        status = budget_service.evaluate_budget(app.user_email)
        if status.within_budget:
            st.edit_dialog_open = False
            st.new_budget_input = ""
            me.navigate("/welcome")
        else:
            st.current_budget = amount
            st.current_cost = status.monthly_cost
            st.edit_dialog_open = False
            st.new_budget_input = ""
        yield
    except Exception as ex:  # noqa: BLE001
        st.error_message = f"Failed to update budget: {ex}"
        st.error_dialog_open = True
        yield

def on_budget_input(e):
    st = me.state(PageState)
    try:
        # textarea on_blur provides .value
        st.new_budget_input = (e.value or "").strip()
    except Exception:
        # Fallback: ignore if structure differs
        pass
    yield

def access_restricted_content():
    app = me.state(AppState)
    st = me.state(PageState)
    cfg = Default()
    # If user has no department, bounce them to setup immediately
    dept: str | None = None
    if cfg.BUDGET_SCOPE != "project":
        try:
            dept = budget_service.get_user_department(app.user_email)
        except Exception:
            dept = None
        if not dept:
            me.navigate("/setup_profile")
            return
    # Default to user's department and load its current budget on first render
    if not st.selected_department:
        st.selected_department = dept
        try:
            if cfg.BUDGET_SCOPE == "project":
                st.current_budget = budget_service.get_project_budget()
            else:
                st.current_budget = budget_service.get_department_budget(st.selected_department)
        except Exception:
            st.current_budget = None
        # Load current monthly cloud cost
        try:
            st.current_cost = budget_service.get_monthly_cloud_cost()
        except Exception:
            st.current_cost = None
    # Determine user role for permissions
    role = None
    try:
        role = budget_service.get_user_role(app.user_email)
    except Exception:
        role = None
    # Check if budget is missing for department
    budget_missing = st.current_budget is None
    with page_frame():  # pylint: disable=E1129:not-context-manager
        # Big centered title row with warning icon
        with me.box(style=me.Style(display="flex", justify_content="center", margin=me.Margin(top=24))):
            with me.box(style=me.Style(display="flex", align_items="center", gap=12)):
                me.text("⚠", type="headline-4", style=me.Style(color=me.theme_var("error")))
                if budget_missing:
                    me.text(
                        "Budget Not Set",
                        type="headline-4",
                        style=me.Style(color=me.theme_var("error"), font_family="Google Sans"),
                    )
                else:
                    me.text(
                        "Budget Exceeded",
                        type="headline-4",
                        style=me.Style(color=me.theme_var("error"), font_family="Google Sans"),
                    )
        with me.box(style=me.Style(display="flex", justify_content="center", margin=me.Margin(top=12))):
            if budget_missing:
                me.text(
                    (
                        "Access is blocked because no budget is set for the project. "
                        "Please contact an admin to set a budget."
                    ) if cfg.BUDGET_SCOPE == "project" else (
                        "Access is blocked because no budget is set for your department. "
                        "Please contact an admin to set a budget."
                    ),
                    type="body-1",
                    style=me.Style(color=me.theme_var("error")),
                )
            else:
                me.text(
                    (
                        "Access is temporarily blocked because monthly costs exceed the project’s budget."
                    ) if cfg.BUDGET_SCOPE == "project" else (
                        "Access is temporarily blocked because monthly costs exceed your department’s budget."
                    ),
                    type="body-1",
                    style=me.Style(color=me.theme_var("error")),
                )
        with me.box(style=me.Style(display="flex", justify_content="center", margin=me.Margin(top=24))):
            with me.box(
                style=me.Style(
                    background=me.theme_var("surface"),
                    border_radius=16,
                    box_shadow=me.theme_var("shadow_elevation_2"),
                    padding=me.Padding.all(24),
                    width="min(720px, 100%)",
                    display="flex",
                    flex_direction="column",
                    gap=16,
                )
            ):
                # Simple 4-row table: label left, value right (use dividers between rows)
                def _row(label: str, value: str):
                    with me.box(
                        style=me.Style(
                            display="flex",
                            justify_content="space-between",
                            align_items="center",
                            padding=me.Padding(top=8, bottom=8),
                        )
                    ):
                        me.text(label, type="subtitle-2", style=me.Style(color=me.theme_var("error")))
                        me.text(value, type="body-1", style=me.Style(color=me.theme_var("error")))
                dept_label = st.selected_department or dept or ("Project" if cfg.BUDGET_SCOPE == "project" else "—")
                cost_label = (
                    f"€{st.current_cost:,.2f}" if st.current_cost is not None else "Unavailable"
                )
                budget_label = (
                    f"€{st.current_budget:,.2f}" if st.current_budget is not None else "Not set"
                )
                _row("User email", app.user_email)
                me.divider()
                if cfg.BUDGET_SCOPE == "project":
                    _row("Scope", "Project")
                    me.divider()
                else:
                    _row("Department", dept_label)
                    me.divider()
                _row("Current monthly cost", cost_label)
                me.divider()
                _row("Budget", budget_label)
                with me.box(style=me.Style(display="flex", justify_content="flex-end", margin=me.Margin(top=8))):
                    # Hide update button entirely in project mode per requirement
                    if role == "admin" and cfg.BUDGET_SCOPE != "project":
                        me.button(
                            "Update Budget",
                            on_click=_open_edit_dialog,
                            style=me.Style(
                                background=me.theme_var("primary"),
                                color=me.theme_var("on-primary"),
                                padding=me.Padding(top=10, bottom=10, left=16, right=16),
                                border_radius=24,
                                font_weight="600",
                            ),
                        )
        if st.error_dialog_open:
            with dialog(is_open=st.error_dialog_open):  # pylint: disable=E1129:not-context-manager
                me.text("Error", type="headline-6", style=me.Style(color=me.theme_var("error"), font_family="Google Sans"))
                me.text(st.error_message, style=me.Style(margin=me.Margin(top=12)))
                with dialog_actions():  # pylint: disable=E1129:not-context-manager
                    me.button("Close", on_click=_close_error_dialog, type="flat")
    # Update Budget modal (disabled in project scope)
    if st.edit_dialog_open and Default().BUDGET_SCOPE != "project":
            with dialog(is_open=st.edit_dialog_open):  # pylint: disable=E1129:not-context-manager
                me.text("Update Budget", type="headline-6", style=me.Style(font_family="Google Sans"))
                with me.box(style=me.Style(display="flex", flex_direction="column", gap=12, margin=me.Margin(top=12))):
                    me.text("Department", type="subtitle-2", style=me.Style(color=me.theme_var("on-tertiary-container")))
                    me.text(st.selected_department or dept or "—")
                    me.text("New monthly budget (EUR)", type="subtitle-2", style=me.Style(color=me.theme_var("on-tertiary-container")))
                    me.textarea(
                        label="Enter amount",
                        value=st.new_budget_input,
                        rows=1,
                        on_blur=on_budget_input,
                        style=me.Style(width="320px"),
                    )
                with dialog_actions():  # pylint: disable=E1129:not-context-manager
                    me.button("Cancel", on_click=_close_edit_dialog)
                    me.button("Save", on_click=on_click_update_budget, type="flat")

def _close_error_dialog(e: me.ClickEvent):  # pylint: disable=unused-argument
    st = me.state(PageState)
    st.error_dialog_open = False
    yield

def _open_edit_dialog(e: me.ClickEvent):  # pylint: disable=unused-argument
    st = me.state(PageState)
    # Pre-fill with current budget if available
    st.new_budget_input = "" if st.current_budget is None else f"{st.current_budget:.2f}"
    st.edit_dialog_open = True
    yield

def _close_edit_dialog(e: me.ClickEvent):  # pylint: disable=unused-argument
    st = me.state(PageState)
    st.edit_dialog_open = False
    yield

@me.page(
    path="/access_restricted",
    title="Access Restricted - GenMedia Creative Studio",
)
def page():
    with page_scaffold(page_name="access_restricted"):  # pylint: disable=E1129:not-context-manager
        access_restricted_content()
