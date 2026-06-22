"""
Stripe -> Supabase plan sync webhook.

Deploy this separately from Streamlit, for example on Render.

Required environment variables:
- STRIPE_SECRET_KEY
- STRIPE_WEBHOOK_SECRET
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY

Recommended Stripe setup:
1. Use Stripe Payment Links or Checkout.
2. Your Streamlit upgrade buttons must append client_reference_id=<supabase_user_id>.
3. Use real Stripe Price IDs in PRICE_ID_TO_PLAN.
4. Optional fallback: use Payment Link URLs in PAYMENT_LINK_URL_TO_PLAN.
5. Add webhook endpoint:
   https://sales-intelligence-webhook.onrender.com/stripe/webhook
6. Subscribe to:
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
# BEST OPTION:
# Replace these with real Stripe Price IDs from Stripe Product Catalog.
# They look like: price_1Txxxxx...
#
# IMPORTANT:
# The values below are currently your Payment Link URLs, not Price IDs.
# Because of that, keep them in PAYMENT_LINK_URL_TO_PLAN for now.
# Later, replace PRICE_ID_TO_PLAN with real price_... IDs.
PRICE_ID_TO_PLAN = {
    "price_1TfM24J7gq8yd4kGVqZVkokN": "pro",
     "your_premium_price_id": "premium",
}
    # Example:
    # "price_123": "pro",
    # "price_456": "premium",


# FALLBACK OPTION:
# This lets the webhook still work if Stripe gives us the Payment Link URL/id.
PAYMENT_LINK_URL_TO_PLAN = {
    "https://buy.stripe.com/test_6oU7sM5sucQjh152Sc4Vy02": "pro",
    "https://buy.stripe.com/test_9B6fZi8EG4jN4ej3Wg4Vy03": "premium",
}


# ============================================================
# SAFE STRIPE OBJECT ACCESS
# ============================================================

def stripe_get(obj: Any, key: str, default: Any = None) -> Any:
    """
    Stripe objects are not always normal Python dicts.
    This function safely reads values from dicts and StripeObject instances.
    """
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
        logger.info("Updated Supabase profile %s -> %s. Result: %s", user_id, plan, result)
        return True
    except Exception as exc:
        logger.exception("Failed to update Supabase profile %s -> %s: %s", user_id, plan, exc)
        return False


def price_id_to_plan(price_id: Optional[str]) -> str:
    if not price_id:
        return "starter"

    plan = PRICE_ID_TO_PLAN.get(price_id)
    if plan:
        return normalise_plan(plan)

    logger.warning("Unknown Stripe price id: %s. Falling back to starter.", price_id)
    return "starter"


def payment_link_to_plan(payment_link_value: Optional[str]) -> Optional[str]:
    if not payment_link_value:
        return None

    # Stripe may send payment_link as plink_xxx, not the buy.stripe.com URL.
    # URL mapping works only if the event contains the URL or you add metadata.
    return PAYMENT_LINK_URL_TO_PLAN.get(payment_link_value)


def plan_from_subscription(subscription: Any) -> str:
    """Find plan from a Stripe Subscription object."""
    try:
        price_id = nested_get(subscription, ["items", "data"], default=[])

        if price_id and isinstance(price_id, list):
            first_item = price_id[0]
            actual_price_id = nested_get(first_item, ["price", "id"])
            return price_id_to_plan(actual_price_id)

        return "starter"
    except Exception as exc:
        logger.warning("Could not determine plan from subscription: %s", exc)
        return "starter"


def plan_from_checkout_session(session: Any) -> str:
    """
    Find plan from a Checkout Session.
    Works for subscription mode and Payment Link flows.
    """
    # 1. Best case: subscription checkout.
    subscription_id = stripe_get(session, "subscription")
    if subscription_id:
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return plan_from_subscription(subscription)
        except Exception as exc:
            logger.warning("Could not retrieve subscription %s: %s", subscription_id, exc)

    # 2. Fallback: inspect Checkout Session line items.
    session_id = stripe_get(session, "id")
    if session_id:
        try:
            line_items = stripe.checkout.Session.list_line_items(session_id, limit=10)
            items = stripe_get(line_items, "data", [])

            for item in items:
                price_id = nested_get(item, ["price", "id"])
                if price_id:
                    plan = PRICE_ID_TO_PLAN.get(price_id)
                    if plan:
                        return normalise_plan(plan)

                    logger.warning("Line item price id not mapped: %s", price_id)

        except Exception as exc:
            logger.warning("Could not list line items for session %s: %s", session_id, exc)

    # 3. Fallback: session metadata plan.
    metadata = stripe_get(session, "metadata", {}) or {}
    metadata_plan = metadata.get("plan") if isinstance(metadata, dict) else None
    if metadata_plan:
        return normalise_plan(metadata_plan)

    # 4. Fallback: payment link mapping.
    payment_link = stripe_get(session, "payment_link")
    mapped_payment_link_plan = payment_link_to_plan(payment_link)
    if mapped_payment_link_plan:
        return normalise_plan(mapped_payment_link_plan)

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

    if event_type == "customer.subscription.updated":
        status = stripe_get(obj, "status")
        plan = plan_from_subscription(obj)

        if status not in {"active", "trialing"}:
            plan = "starter"

        logger.info(
            "Subscription updated. Calculated plan=%s status=%s. "
            "Automatic user lookup requires storing stripe_customer_id in profiles.",
            plan,
            status,
        )
        return {"status": "received", "event_type": event_type}

    if event_type in {"customer.subscription.deleted", "invoice.payment_failed"}:
        logger.info(
            "%s received. Automatic downgrade requires storing stripe_customer_id in profiles.",
            event_type,
        )
        return {"status": "received", "event_type": event_type}

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
