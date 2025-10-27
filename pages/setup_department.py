"""User onboarding page to select department.

Prefills the user's email (read-only) and lets them pick a department
from a fixed list. On submit, writes to the Firestore users collection
in the `creative-studio-budget-allocation` database.
"""

import mesop as me  # type: ignore
from google.api_core.exceptions import PermissionDenied  # type: ignore
from components.dialog import dialog, dialog_actions  # use shared dialog component

from components.header import header
from components.page_scaffold import page_frame, page_scaffold
from models import budget as budget_service
from config.default import Default
from state.state import AppState


DEPARTMENTS = ["Marketing", "Sales", "Development"]


@me.stateclass
class PageState:
    selected_department: str | None = None
    error_dialog_open: bool = False
    error_message: str = ""


def on_click_save(e: me.ClickEvent):  # pylint: disable=unused-argument
    """Persist the selected department and navigate to home."""
    app = me.state(AppState)
    st = me.state(PageState)
    try:
        if not st.selected_department:
            st.error_message = "Please select a department."
            st.error_dialog_open = True
            yield
            return
        budget_service.upsert_user_department(app.user_email, st.selected_department)
        # Immediately verify budget and redirect accordingly
        status = budget_service.evaluate_budget(app.user_email)
        if status.error in ("missing_budget",) or (status.within_budget is False):
            me.navigate("/budget_exceeded")
        else:
            me.navigate("/home")
        yield
    except PermissionDenied as ex:
        cfg = Default()
        st.error_message = (
            "Failed to save department: 403 Missing or insufficient permissions.\n\n"
            "What to do:\n"
            f"- Ensure Firestore is enabled in project: {cfg.PROJECT_ID}\n"
            f"- Ensure the database exists: {cfg.BUDGET_DB_ID}\n"
            "- Grant 'Cloud Datastore User' (roles/datastore.user) to the runtime principal (Cloud Run service account or your ADC account).\n"
            "- If running locally, run 'gcloud auth application-default login' and set the correct project."
        )
        st.error_dialog_open = True
        yield
    except Exception as ex:  # noqa: BLE001
        st.error_message = f"Failed to save department: {ex}"
        st.error_dialog_open = True
        yield


def setup_department_content():
    app = me.state(AppState)
    st = me.state(PageState)
    with page_frame():  # pylint: disable=E1129:not-context-manager
        header("Complete Your Setup", "account_circle")

        with me.box(style=me.Style(display="flex", flex_direction="column", gap=16, max_width="640px")):
            me.text("We couldn't find your department. Please complete your profile to continue.")

            me.text("Email", type="subtitle-2")
            me.text(app.user_email)

            me.text("Department", type="subtitle-2")
            me.select(
                label="Select department",
                options=[me.SelectOption(label=k, value=k) for k in DEPARTMENTS],
                value=st.selected_department or "",
                on_selection_change=_on_dept_change,
            )

            with me.box(style=me.Style(display="flex", gap=12)):
                me.button("Save", on_click=on_click_save)
                # No cancel/back: setup is required before accessing other pages

        if st.error_dialog_open:
            with dialog(is_open=st.error_dialog_open):  # pylint: disable=E1129:not-context-manager
                me.text("Error", type="headline-6", style=me.Style(color=me.theme_var("error")))
                me.text(st.error_message, style=me.Style(margin=me.Margin(top=12)))
                with dialog_actions():  # pylint: disable=E1129:not-context-manager
                    me.button("Close", on_click=_close_error_dialog, type="flat")


def _on_dept_change(e: me.SelectSelectionChangeEvent):
    st = me.state(PageState)
    st.selected_department = e.value
    yield


def _navigate_home(e: me.ClickEvent):  # pylint: disable=unused-argument
    me.navigate("/home")
    yield


def _close_error_dialog(e: me.ClickEvent):  # pylint: disable=unused-argument
    st = me.state(PageState)
    st.error_dialog_open = False
    yield


@me.page(
    path="/setup_department",
    title="Setup Department - GenMedia Creative Studio",
)
def page():
    with page_scaffold(page_name="setup_department"):  # pylint: disable=E1129:not-context-manager
        setup_department_content()
