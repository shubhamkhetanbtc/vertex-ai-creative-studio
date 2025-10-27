"""Budget exceeded page with option to edit department budgets.

Accessible when a user's department monthly cost exceeds allocated budget.
Allows selecting a department and updating its budget.
"""

import mesop as me  # type: ignore
from components.dialog import dialog, dialog_actions  # use shared dialog component

from components.header import header
from components.page_scaffold import page_frame, page_scaffold
from models import budget as budget_service
from state.state import AppState


DEPARTMENTS = ["Marketing", "Sales", "Development"]


@me.stateclass
class PageState:
    selected_department: str | None = None
    new_budget_input: str = ""
    info_message: str = ""
    error_dialog_open: bool = False
    error_message: str = ""
    current_budget: float | None = None


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
            me.navigate("/home")
        else:
            st.info_message = f"Budget for {st.selected_department} set to €{amount:,.2f}."
            st.current_budget = amount
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


def on_department_change(e: me.SelectSelectionChangeEvent):
    st = me.state(PageState)
    st.selected_department = e.value
    try:
        st.current_budget = budget_service.get_department_budget(st.selected_department)
    except Exception:
        st.current_budget = None
    yield


def budget_exceeded_content():
    app = me.state(AppState)
    st = me.state(PageState)
    # If user has no department, bounce them to setup immediately
    try:
        dept = budget_service.get_user_department(app.user_email)
    except Exception:
        dept = None
    if not dept:
        me.navigate("/setup_department")
        return
    # Default to user's department and load its current budget on first render
    if not st.selected_department:
        st.selected_department = dept
        try:
            st.current_budget = budget_service.get_department_budget(st.selected_department)
        except Exception:
            st.current_budget = None
    with page_frame():  # pylint: disable=E1129:not-context-manager
        header("Budget Exceeded", "warning")

        with me.box(style=me.Style(display="flex", flex_direction="column", gap=16, max_width="720px")):
            me.text("Access is temporarily blocked because monthly costs exceed the allocated budget for your department.")
            me.text(f"Signed in as: {app.user_email}")

            me.divider()
            me.text("Edit Department Budget", type="headline-5")
            # Ensure user's department appears in the options
            _options = DEPARTMENTS if dept in DEPARTMENTS else (DEPARTMENTS + [dept])
            me.select(
                label="Department",
                options=[me.SelectOption(label=k, value=k) for k in _options],
                value=st.selected_department or "",
                on_selection_change=on_department_change,
            )
            # Show current budget or a helpful message
            if st.selected_department:
                if st.current_budget is not None:
                    me.text(
                        f"Current budget for {st.selected_department}: €{st.current_budget:,.2f}",
                        style=me.Style(margin=me.Margin(top=8)),
                    )
                else:
                    me.text(
                        "No budget exists for the selected department, please set a new budget.",
                        style=me.Style(margin=me.Margin(top=8)),
                    )
            me.textarea(
                label="New monthly budget (EUR)",
                value=st.new_budget_input,
                rows=1,
                on_blur=on_budget_input,
                style=me.Style(width="320px"),
            )
            with me.box(style=me.Style(display="flex", gap=12)):
                me.button("Update Budget", on_click=on_click_update_budget)
                me.button("Back to Home", on_click=_go_home, type="flat")

            if st.info_message:
                me.text(st.info_message, style=me.Style(color=me.theme_var("on-tertiary-container")))

        if st.error_dialog_open:
            with dialog(is_open=st.error_dialog_open):  # pylint: disable=E1129:not-context-manager
                me.text("Error", type="headline-6", style=me.Style(color=me.theme_var("error")))
                me.text(st.error_message, style=me.Style(margin=me.Margin(top=12)))
                with dialog_actions():  # pylint: disable=E1129:not-context-manager
                    me.button("Close", on_click=_close_error_dialog, type="flat")


def _go_home(e: me.ClickEvent):  # pylint: disable=unused-argument
    me.navigate("/home")
    yield


def _close_error_dialog(e: me.ClickEvent):  # pylint: disable=unused-argument
    st = me.state(PageState)
    st.error_dialog_open = False
    yield


@me.page(
    path="/budget_exceeded",
    title="Budget Exceeded - GenMedia Creative Studio",
)
def page():
    with page_scaffold(page_name="budget_exceeded"):  # pylint: disable=E1129:not-context-manager
        budget_exceeded_content()
