"""
Stripe -> Supabase plan sync webhook.

Deploy this separately from Streamlit, for example on Render.

Required Render environment variables:
- STRIPE_SECRET_KEY
- STRIPE_WEBHOOK_SECRET
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY

Important:
Your Streamlit upgrade buttons must append:
client_reference_id=<supabase_user_id>

Webhook endpoint:
https://your-render-service.onrender.com/stripe/webhook

Stripe events required:
- checkout.session.completed
"""

import os
import logging
from typing import Any, Optional

import stripe
from fastapi import FastAPI, Request, HTTPException
from supabase import create_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stripe_webhook")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

supabase_admin = None
if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

app = FastAPI(title="Stripe Supabase Plan Webhook")


# ============================================================
# PLAN MAPPING
# ============================================================
# Use real Stripe Price IDs where possible.
# Find them in Stripe Dashboard -> Products -> Product -> Pricing.
# They start with price_
#
# Your current known Pro Price ID is already added.
# Replace YOUR_PREMIUM_PRICE_ID_HERE with the real Premium price_... ID.
PRICE_ID_TO_PLAN = {
    "price_1TfM24J7gq8yd4kGVqZVkokN": "pro",
    "YOUR_PREMIUM_PRICE_ID_HERE": "premium",
}

# Optional Payment Link URL fallback.
# This is not always enough because Stripe often sends payment_link as plink_...
PAYMENT_LINK_URL_TO_PLAN = {
    "https://buy.stripe.com/test_6oU7sM5sucQjh152Sc4Vy02": "pro",
    "https://buy.stripe.com/test_9B6fZi8EG4jN4ej3Wg4Vy03": "premium",
}

# Practical fallback for your current test prices.
# Amount is in pence/cents. GBP £19 = 1900, £39 = 3900.
AMOUNT_TO_PLAN = {
    1900: "pro",
    3900: "premium",
}


# ============================================================
# SAFE STRIPE OBJECT ACCESS
# ============================================================

def stripe_get(obj: Any, key: str, default: Any = None) -> Any:
    """Safely read values from dicts and StripeObject instances."""
    if obj is None:
        return default

    if isinstance(obj, dict):
        return obj.get(key, default)

    try:
        value = getattr(obj, key)
        return value if value is not None else default
    except Exception:
        return default


def nested_get(obj: Any, path: list[str], default: Any = None) -> Any:
    current = obj
    for key in path:
        current = stripe_get(current, key, default=None)
        if current is None:
            return default
    return current


def require_config() -> None:
    missing = []
    if not STRIPE_SECRET_KEY:
        missing.append("STRIPE_SECRET_KEY")
    if not STRIPE_WEBHOOK_SECRET:
        missing.append("STRIPE_WEBHOOK_SECRET")
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if supabase_admin is None:
        missing.append("Supabase client")

    if missing:
        raise RuntimeError(f"Missing webhook configuration: {', '.join(missing)}")


def normalise_plan(plan: Optional[str]) -> str:
    plan = (plan or "starter").strip().lower()
    return plan if plan in {"starter", "pro", "premium"} else "starter"


def update_profile_plan(user_id: str, plan: str) -> bool:
    """Update Supabase profiles.plan using the Supabase Auth user id."""
    if not user_id:
        logger.warning("No user_id supplied; cannot update profile plan.")
        return False

    plan = normalise_plan(plan)

    try:
        result = (
            supabase_admin
            .table("profiles")
            .update({"plan": plan})
            .eq("id", user_id)
            .execute()
        )

        updated_rows = result.data or []
        logger.info("Supabase update result for user_id=%s plan=%s data=%s", user_id, plan, updated_rows)

        if not updated_rows:
            logger.warning(
                "No Supabase profile row was updated. Check profiles.id matches client_reference_id: %s",
                user_id,
            )

        return True

    except Exception as exc:
        logger.exception("Failed to update Supabase profile %s -> %s: %s", user_id, plan, exc)
        return False


def price_id_to_plan(price_id: Optional[str]) -> Optional[str]:
    if not price_id:
        return None

    plan = PRICE_ID_TO_PLAN.get(price_id)
    if plan:
        return normalise_plan(plan)

    logger.warning("Unknown Stripe price id: %s", price_id)
    return None


def payment_link_to_plan(payment_link_value: Optional[str]) -> Optional[str]:
    if not payment_link_value:
        return None

    plan = PAYMENT_LINK_URL_TO_PLAN.get(payment_link_value)
    if plan:
        return normalise_plan(plan)

    logger.warning("Payment link not mapped or Stripe sent plink id instead of URL: %s", payment_link_value)
    return None


def amount_to_plan(amount: Optional[int]) -> Optional[str]:
    if amount is None:
        return None

    plan = AMOUNT_TO_PLAN.get(int(amount))
    if plan:
        return normalise_plan(plan)

    logger.warning("Amount not mapped to plan: %s", amount)
    return None


def plan_from_subscription(subscription: Any) -> Optional[str]:
    """Find plan from a Stripe Subscription object."""
    try:
        items = nested_get(subscription, ["items", "data"], default=[])

        if items and isinstance(items, list):
            first_item = items[0]
            actual_price_id = nested_get(first_item, ["price", "id"])
            plan = price_id_to_plan(actual_price_id)
            if plan:
                return plan

        return None
    except Exception as exc:
        logger.warning("Could not determine plan from subscription: %s", exc)
        return None


def plan_from_checkout_session(session: Any) -> str:
    """
    Find plan from a Checkout Session.

    Priority:
    1. Subscription price ID
    2. Checkout line item price ID
    3. Metadata plan
    4. Payment link mapping
    5. Amount fallback: £19 -> pro, £39 -> premium
    """

    # 1. Subscription checkout.
    subscription_id = stripe_get(session, "subscription")
    if subscription_id:
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            plan = plan_from_subscription(subscription)
            if plan:
                return plan
        except Exception as exc:
            logger.warning("Could not retrieve subscription %s: %s", subscription_id, exc)

    # 2. Checkout Session line items.
    session_id = stripe_get(session, "id")
    if session_id:
        try:
            line_items = stripe.checkout.Session.list_line_items(session_id, limit=10)
            items = stripe_get(line_items, "data", [])

            for item in items:
                price_id = nested_get(item, ["price", "id"])
                plan = price_id_to_plan(price_id)
                if plan:
                    return plan

                amount_subtotal = stripe_get(item, "amount_subtotal")
                plan = amount_to_plan(amount_subtotal)
                if plan:
                    return plan

        except Exception as exc:
            logger.warning("Could not list line items for session %s: %s", session_id, exc)

    # 3. Metadata plan.
    metadata = stripe_get(session, "metadata", {}) or {}
    metadata_plan = metadata.get("plan") if isinstance(metadata, dict) else None
    if metadata_plan:
        return normalise_plan(metadata_plan)

    # 4. Payment link mapping.
    payment_link = stripe_get(session, "payment_link")
    mapped_payment_link_plan = payment_link_to_plan(payment_link)
    if mapped_payment_link_plan:
        return mapped_payment_link_plan

    # 5. Amount fallback from Checkout Session.
    amount_total = stripe_get(session, "amount_total")
    mapped_amount_plan = amount_to_plan(amount_total)
    if mapped_amount_plan:
        return mapped_amount_plan

    logger.warning("Could not determine plan from checkout session. Falling back to starter.")
    return "starter"


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    try:
        require_config()
    except RuntimeError as exc:
        logger.error(str(exc))
        raise HTTPException(status_code=500, detail="Webhook is not configured correctly.")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = stripe_get(event, "type")
    data = stripe_get(event, "data", {})
    obj = stripe_get(data, "object", {})

    logger.info("Received Stripe event: %s", event_type)

    if event_type == "checkout.session.completed":
        user_id = stripe_get(obj, "client_reference_id")
        plan = plan_from_checkout_session(obj)

        logger.info("Checkout completed. user_id=%s plan=%s", user_id, plan)

        if not user_id:
            logger.warning(
                "checkout.session.completed has no client_reference_id. "
                "Check your Streamlit upgrade links."
            )
            return {"status": "ignored", "reason": "missing client_reference_id"}

        updated = update_profile_plan(user_id, plan)
        return {"status": "ok" if updated else "failed", "plan": plan, "user_id": user_id}

    return {"status": "ignored", "event_type": event_type}


@app.get("/healthz")
async def healthz():
    configured = bool(
        STRIPE_SECRET_KEY
        and STRIPE_WEBHOOK_SECRET
        and SUPABASE_URL
        and SUPABASE_SERVICE_ROLE_KEY
        and supabase_admin is not None
    )
    return {"status": "ok", "configured": configured}


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "Stripe Supabase Plan Webhook",
        "health": "/healthz",
        "webhook": "/stripe/webhook",
    }
