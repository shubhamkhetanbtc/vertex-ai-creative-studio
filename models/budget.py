"""Budget and access control service.

Encapsulates Firestore lookups for user departments and budgets,
and BigQuery queries for monthly cloud cost. Designed to be used
by FastAPI middleware and Mesop pages.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional

from google.cloud import bigquery  # type: ignore
from google.cloud import firestore  # type: ignore

from config.default import Default
from config.firebase_config import FirebaseClient


cfg = Default()


@dataclass(frozen=True)
class BudgetStatus:
    email: str
    department: Optional[str]
    budget: Optional[float]
    monthly_cost: Optional[float]
    within_budget: Optional[bool]
    error: Optional[str] = None


def _budget_db() -> firestore.Client:
    """Returns a Firestore client for the budget database (separate DB)."""
    return FirebaseClient(cfg.BUDGET_DB_ID).get_client()


def get_user_department(email: str) -> Optional[str]:
    """Fetches the department for a user email from the users collection.

    Collection: users (in database `creative-studio-budget-allocation` by default)
    Document ID: email
    Field: department (str)
    """
    db = _budget_db()
    doc = db.collection(cfg.BUDGET_USERS_COLLECTION).document(email).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    dept = data.get("department")
    if isinstance(dept, str) and dept:
        return dept
    return None


def upsert_user_department(email: str, department: str) -> None:
    """Creates or updates a user's department in the users collection."""
    db = _budget_db()
    db.collection(cfg.BUDGET_USERS_COLLECTION).document(email).set(
        {"department": department}, merge=True
    )


def get_department_budget(department: str) -> Optional[float]:
    """Reads the numeric monthly budget for a department.

    Collection: budgets
    Document ID: department
    Field: amount (number)
    """
    db = _budget_db()
    doc = db.collection(cfg.BUDGETS_COLLECTION).document(department).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    amount = data.get("amount")
    try:
        return float(amount) if amount is not None else None
    except (TypeError, ValueError):
        return None


def set_department_budget(department: str, amount: float) -> None:
    """Sets the monthly budget for a department."""
    db = _budget_db()
    db.collection(cfg.BUDGETS_COLLECTION).document(department).set(
        {"amount": float(amount)}, merge=True
    )


def get_monthly_cloud_cost(project_id: Optional[str] = None) -> Optional[float]:
    """Returns this month's total cloud cost for the configured project.

    Requires a BigQuery billing export table configured via environment:
    - BILLING_PROJECT_ID (defaults to PROJECT_ID)
    - BILLING_DATASET
    - BILLING_TABLE

    Returns None if not configured or on query errors.
    """
    billing_dataset = cfg.BILLING_DATASET
    billing_table = cfg.BILLING_TABLE
    billing_project = cfg.BILLING_PROJECT_ID or cfg.PROJECT_ID
    target_project = project_id or cfg.PROJECT_ID

    if not (billing_project and billing_dataset and billing_table and target_project):
        return None

    client = bigquery.Client(project=billing_project)

    start = datetime.date.today().replace(day=1)
    end = datetime.date.today() + datetime.timedelta(days=1)

    table_fqn = f"`{billing_project}.{billing_dataset}.{billing_table}`"

    # The official export has usage_start_time; fall back to invoice.month if present.
    query = f"""
        SELECT
          SUM(CAST(cost AS NUMERIC)) AS total_cost
        FROM {table_fqn}
        WHERE project.id = @project_id
          AND DATE(usage_start_time) >= @start_date
          AND DATE(usage_start_time) < @end_date
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("project_id", "STRING", target_project),
            bigquery.ScalarQueryParameter("start_date", "DATE", start),
            bigquery.ScalarQueryParameter("end_date", "DATE", end),
        ]
    )

    try:
        result = client.query(query, job_config=job_config).result()
        row = next(iter(result), None)
        if not row:
            return 0.0
        total = row["total_cost"]
        return float(total) if total is not None else 0.0
    except Exception:
        # Try a fallback using invoice.month if the first query fails due to schema
        try:
            ym = datetime.date.today().strftime("%Y%m")
            fallback_query = f"""
                SELECT SUM(CAST(cost AS NUMERIC)) AS total_cost
                FROM {table_fqn}
                WHERE project.id = @project_id AND invoice.month = @ym
            """
            fallback_cfg = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("project_id", "STRING", target_project),
                    bigquery.ScalarQueryParameter("ym", "STRING", ym),
                ]
            )
            result = client.query(fallback_query, job_config=fallback_cfg).result()
            row = next(iter(result), None)
            if not row:
                return 0.0
            total = row["total_cost"]
            return float(total) if total is not None else 0.0
        except Exception:
            return None


def evaluate_budget(email: str) -> BudgetStatus:
    """Computes the budget status for the given user email.

    - Finds user's department.
    - Reads department budget.
    - Computes current month cost.
    """
    dept = get_user_department(email)
    if not dept:
        return BudgetStatus(email=email, department=None, budget=None, monthly_cost=None, within_budget=None, error="missing_user")

    budget = get_department_budget(dept)
    if budget is None:
        return BudgetStatus(email=email, department=dept, budget=None, monthly_cost=None, within_budget=None, error="missing_budget")

    cost = get_monthly_cloud_cost()
    if cost is None:
        return BudgetStatus(email=email, department=dept, budget=budget, monthly_cost=None, within_budget=None, error="cost_unavailable")

    return BudgetStatus(
        email=email,
        department=dept,
        budget=budget,
        monthly_cost=cost,
        within_budget=(cost <= budget),
    )
